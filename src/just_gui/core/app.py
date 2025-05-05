# src/just_gui/core/app.py
import logging
import sys
from pathlib import Path
from typing import Dict

import platformdirs
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox, QWidget

from .theme_manager import apply_theme
from .ui_manager import UIManager
from .view_manager import ViewManager
from ..events.bus import EventBus
from ..plugins.base import ViewFactory
from ..plugins.manager import PluginManager
from ..state.manager import StateManager
from ..utils.config_loader import load_toml, ConfigError

APP_NAME = "just-gui"
APP_AUTHOR = "dimnissv"

logger = logging.getLogger(__name__)


class AppCore(QMainWindow):
    """
    Главный класс приложения just-gui.
    Оркестрирует взаимодействие между менеджерами.
    """
    APP_NAME = APP_NAME
    APP_AUTHOR = APP_AUTHOR

    def __init__(self, profile_path: str):
        super().__init__()
        self.profile_path = Path(profile_path)
        self.profile_name = self.profile_path.stem
        self.config: Dict = {}
        self.profile_metadata: Dict = {}

        logger.debug(f"AppCore ({self.profile_name}): Initializing...")

        self._load_app_config()
        self.event_bus = EventBus()
        self.state_manager = StateManager()
        self.ui_manager = UIManager(main_window=self)
        self.ui_manager.initialize_ui()
        self.view_manager = ViewManager(app_core=self, ui_manager=self.ui_manager, parent=self)
        self.view_manager._add_menu_actions()  # Должно быть после инициализации UI
        self.plugin_manager = PluginManager(
            app_core=self, state_manager=self.state_manager, event_bus=self.event_bus
        )

        theme = self.config.get("theme", "light")
        apply_theme(self, theme)
        profile_title = self.profile_metadata.get("title", self.profile_name)
        self.setWindowTitle(f"just-gui: {profile_title}")
        logger.debug(f"AppCore ({self.profile_name}): __init__ complete.")

    async def initialize(self):
        """Асинхронная инициализация."""
        logger.info(f"AppCore ({self.profile_name}): Starting async initialization...")
        critical_error = None
        try:
            await self.plugin_manager.load_profile(str(self.profile_path))
        except Exception as e:
            logger.error(f"Критическая ошибка загрузки профиля '{self.profile_name}': {e}", exc_info=True)
            critical_error = e

        try:
            self.view_manager.update_view_menu()
            # Пытаемся загрузить состояние вида
            view_loaded = self.view_manager.load_view_state()  # Теперь возвращает bool

            # --- ИЗМЕНЕНО: Открываем все вкладки, если вид не был загружен ---
            if not view_loaded:
                logger.info("Сохраненный вид не найден или пуст. Открытие всех доступных представлений по умолчанию...")
                self.view_manager.open_all_declared_views()
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        except Exception as e:
            logger.error(f"Ошибка при обновлении/загрузке вида: {e}", exc_info=True)
            if not critical_error:
                QMessageBox.warning(self, "Ошибка вида", f"Не удалось обновить или загрузить состояние вида:\n{e}")

        logger.info(f"AppCore ({self.profile_name}): Async initialization complete.")
        if critical_error:
            QMessageBox.critical(self, "Ошибка загрузки профиля",
                                 f"Произошла критическая ошибка при загрузке плагинов:\n{critical_error}\n\n"
                                 "Некоторые функции могут быть недоступны.")

        # Обновляем статус, если ни одной вкладки так и не открылось (даже по умолчанию)
        if self.view_manager.tab_widget and self.view_manager.tab_widget.count() == 0:
            self.update_status("Плагины загружены, но доступных представлений нет или их не удалось открыть.", 5000)
        elif not critical_error:  # Если нет крит. ошибок и вкладки открыты
            self.update_status("Готово", 3000)

    def _load_app_config(self):

        logger.debug(f"Загрузка конфигурации приложения из {self.profile_path}")
        try:
            if not self.profile_path.is_file():
                logger.warning(f"Файл профиля не найден: {self.profile_path}.")
                self.config = {}
                return
            profile_data = load_toml(self.profile_path)
            self.config = profile_data.get("config", {})
            self.profile_metadata = profile_data.get("profile_metadata", {})
            log_level_str = self.config.get("log_level", "INFO").upper()
            try:
                log_level = getattr(logging, log_level_str, logging.INFO)
                package_logger = logging.getLogger('just_gui')
                package_logger.setLevel(log_level)
                if not package_logger.handlers:
                    handler = logging.StreamHandler(sys.stdout)
                    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    handler.setFormatter(formatter)
                    package_logger.addHandler(handler)
                    package_logger.propagate = False
                logger.info(f"Уровень логирования 'just_gui': {log_level_str}")
            except AttributeError:
                logger.warning(f"Неверный уровень логирования '{log_level_str}'.")
                logging.getLogger(
                    'just_gui').setLevel(logging.INFO)
        except ConfigError as e:
            logger.warning(f"Ошибка загрузки конфига: {e}.")
            self.config = {}
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки конфига: {e}", exc_info=True)
            self.config = {}

    def closeEvent(self, event):

        logger.info(f"AppCore ({self.profile_name}): Получено событие закрытия.")
        if hasattr(self, 'view_manager') and self.view_manager:
            self.view_manager.save_view_state()
        else:
            logger.warning("ViewManager не найден при закрытии.")
        if hasattr(self, 'plugin_manager') and self.plugin_manager:
            try:
                self.plugin_manager.unload_all()
            except Exception as e:
                logger.error(f"Ошибка выгрузки плагинов: {e}", exc_info=True)
        else:
            logger.warning("PluginManager не найден при закрытии.")
        event.accept()
        logger.info(f"AppCore ({self.profile_name}): Приложение завершает работу.")

    def update_status(self, message: str, timeout: int = 0):

        if hasattr(self, 'ui_manager') and self.ui_manager: self.ui_manager.update_status(message, timeout)

    def declare_view(self, plugin_name: str, view_id: str, name: str, factory: 'ViewFactory'):

        if hasattr(self, 'view_manager') and self.view_manager:
            self.view_manager.declare_view(plugin_name, view_id, name, factory)
        else:
            logger.error("ViewManager не инициализирован.")

    def register_menu_action(self, plugin_name: str, menu_path: str, action: 'QAction'):

        if hasattr(self, 'ui_manager') and self.ui_manager:
            self.ui_manager.register_menu_action(plugin_name, menu_path, action)
        else:
            logger.error("UIManager не инициализирован.")

    def register_toolbar_widget(self, section_path: str, widget: 'QWidget'):

        if hasattr(self, 'ui_manager') and self.ui_manager:
            self.ui_manager.register_toolbar_widget(section_path, widget)
        else:
            logger.error("UIManager не инициализирован.")

    @property
    def view_state_file(self) -> Path:

        config_dir = Path(platformdirs.user_config_dir(self.APP_NAME, self.APP_AUTHOR))
        profile_view_dir = config_dir / "profiles" / self.profile_name
        profile_view_dir.mkdir(parents=True, exist_ok=True)
        return profile_view_dir / "view_state.json"
