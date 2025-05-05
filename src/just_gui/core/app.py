# src/just_gui/core/app.py
import logging
import sys
from typing import Dict, Optional, Tuple
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QToolBar, QStatusBar,
    QMenuBar, QMessageBox, QMenu  # Добавил QMenu
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QSize

from ..plugins.manager import PluginManager, PluginLoadError
from ..state.manager import StateManager
from ..events.bus import EventBus
from ..utils.config_loader import load_toml, ConfigError
from pathlib import Path
import asyncio  # Keep asyncio import for the method signature

logger = logging.getLogger(__name__)


class AppCore(QMainWindow):
    """
    Главный класс приложения just-gui.
    Управляет основным окном, плагинами, состоянием и событиями.
    """

    def __init__(self, profile_path: str):
        super().__init__()
        self.profile_path = profile_path
        self.config: Dict = {}  # Конфигурация из профиля [config]

        logger.debug("AppCore: Initializing core components...")
        # Инициализация основных компонентов
        self.event_bus = EventBus()
        self.state_manager = StateManager()  # HistoryManager создается внутри по умолчанию
        # Передаем ссылки на основные компоненты в PluginManager
        self.plugin_manager = PluginManager(
            app_core=self,
            state_manager=self.state_manager,
            event_bus=self.event_bus
        )

        # Загрузка конфигурации приложения (тема, уровень логгирования и т.д.)
        # Выполняется синхронно, т.к. это быстрая операция
        self._load_app_config()

        # Настройка основного окна (синхронно)
        self._init_ui()

        self.setWindowTitle("just-gui Application")
        logger.debug("AppCore: __init__ complete.")
        # --- ПЛАГИНЫ БОЛЬШЕ НЕ ЗАГРУЖАЮТСЯ ЗДЕСЬ ---

    async def initialize(self):
        """Асинхронная инициализация: загрузка плагинов и интеграция UI."""
        logger.info("AppCore: Starting asynchronous initialization...")
        try:
            # Загрузка плагинов асинхронно
            await self.plugin_manager.load_profile(self.profile_path)
        except Exception as e:
            logger.error(f"Критическая ошибка при асинхронной загрузке профиля: {e}", exc_info=True)
            # Показываем ошибку пользователю
            # Важно: QMessageBox нужно вызывать из GUI потока, что здесь может быть небезопасно.
            # Лучше просто пробросить исключение наверх в cli.py
            raise  # Перевыбрасываем исключение, чтобы его поймали в cli.py

        # Интеграция загруженных плагинов в UI (уже после await)
        self._integrate_plugins_ui()
        logger.info("AppCore: Asynchronous initialization complete.")

    def _load_app_config(self):
        """Загружает секцию [config] из файла профиля."""
        logger.debug(f"Загрузка конфигурации приложения из {self.profile_path}")
        try:
            profile_data = load_toml(Path(self.profile_path))
            self.config = profile_data.get("config", {})
            logger.info(f"Загружена конфигурация приложения: {self.config}")

            log_level_str = self.config.get("log_level", "INFO").upper()
            try:
                log_level = getattr(logging, log_level_str, logging.INFO)
                # Устанавливаем уровень только для логгеров нашего приложения
                package_logger = logging.getLogger('just_gui')
                package_logger.setLevel(log_level)
                # Убедимся, что есть обработчик, иначе логи не будут выводиться
                if not package_logger.handlers:
                    # Добавим базовый обработчик, если его нет
                    handler = logging.StreamHandler(sys.stdout)
                    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    handler.setFormatter(formatter)
                    package_logger.addHandler(handler)
                    package_logger.propagate = False  # Не передавать сообщения корневому логгеру

                logger.info(f"Уровень логирования для 'just_gui' установлен на: {log_level_str}")
            except AttributeError:
                logger.warning(f"Неверный уровень логирования '{log_level_str}' в профиле. Используется INFO.")
                logging.getLogger('just_gui').setLevel(logging.INFO)


        except (FileNotFoundError, ConfigError) as e:
            logger.warning(f"Не удалось загрузить конфигурацию из профиля: {e}. Используются значения по умолчанию.")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при загрузке конфигурации: {e}", exc_info=True)

    def _init_ui(self):
        """Инициализирует основные элементы UI главного окна."""
        logger.debug("Инициализация UI главного окна...")

        # Меню
        self.menu_bar = self.menuBar()
        self._menus: Dict[str, QMenu] = {}  # Кэш для созданных меню

        # Тулбар
        self.tool_bar = QToolBar("Main Toolbar")
        self.tool_bar.setIconSize(QSize(24, 24))  # Размер иконок
        self.addToolBar(self.tool_bar)
        self._toolbars: Dict[str, QToolBar] = {"Main Toolbar": self.tool_bar}  # Для добавления секций

        # Центральный виджет (вкладки)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)  # Возможность закрывать вкладки
        self.tab_widget.tabCloseRequested.connect(self.close_tab)  # Обработчик закрытия
        self.setCentralWidget(self.tab_widget)

        # Строка состояния
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Инициализация...", 0)  # Сообщение по умолчанию

        # Применить тему (светлая/темная) из self.config
        theme = self.config.get("theme", "light")
        self.apply_theme(theme)

        self._setup_default_menus()  # Добавим стандартные меню (Файл, Помощь)

        logger.debug("UI главного окна инициализирован.")

    def _setup_default_menus(self):
        """Создает базовые пункты меню (Файл, Помощь)."""
        # Меню Файл
        file_menu = self.menu_bar.addMenu("&Файл")
        self._menus["Файл"] = file_menu  # Сохраняем в кэш
        # Используем стандартные иконки темы, если возможно
        exit_icon = QIcon.fromTheme("application-exit", QIcon(
            ":/qt-project.org/styles/commonstyle/images/standardbutton-close-16.png"))  # Запасная иконка
        exit_action = QAction(exit_icon, "&Выход", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Выйти из приложения")
        exit_action.triggered.connect(self.close)  # Стандартный слот закрытия QMainWindow
        file_menu.addAction(exit_action)

        # Меню Помощь
        help_menu = self.menu_bar.addMenu("&Помощь")
        self._menus["Помощь"] = help_menu  # Сохраняем в кэш
        about_icon = QIcon.fromTheme("help-about", QIcon(
            ":/qt-project.org/styles/commonstyle/images/standardbutton-help-16.png"))  # Запасная иконка
        about_action = QAction(about_icon, "&О программе", self)
        about_action.setStatusTip("Показать информацию о программе")
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        # Добавим стандартное меню "Инструменты", если его нет, для плагинов
        if "Инструменты" not in self._menus:
            tools_menu = self.menu_bar.addMenu("&Инструменты")
            self._menus["Инструменты"] = tools_menu

    def show_about_dialog(self):
        """Показывает диалог 'О программе'."""
        try:
            from .. import __version__
        except ImportError:
            __version__ = "N/A"
        QMessageBox.about(self, "О программе just-gui",
                          f"<b>just-gui</b><br>"
                          f"Версия: {__version__}<br><br>"
                          "Модульная платформа для GUI приложений.<br>"
                          "(c) 2024")  # Заменить на актуальный год

    def apply_theme(self, theme_name: str):
        """Применяет цветовую тему (пока очень базовая)."""
        logger.info(f"Применение темы: {theme_name}")
        # TODO: Реализовать загрузку стилей из файлов qss
        if theme_name.lower() == "dark":
            # Пример темного стиля (очень упрощенно)
            try:
                # Попробуем использовать готовую темную тему, если доступна
                import qdarktheme
                self.setStyleSheet(qdarktheme.load_stylesheet())
                logger.info("Применена тема qdarktheme.")
            except ImportError:
                logger.warning("Библиотека qdarktheme не найдена, применяется базовый темный стиль.")
                self.setStyleSheet("""
                    QWidget { background-color: #2d2d2d; color: #f0f0f0; }
                    QMainWindow { background-color: #2d2d2d; } /* Добавляем фон для окна */
                    QMenuBar { background-color: #3c3c3c; color: #f0f0f0; }
                    QMenuBar::item:selected { background-color: #555; }
                    QMenu { background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555; }
                    QMenu::item:selected { background-color: #555; }
                    QToolBar { background-color: #3c3c3c; border: none; }
                    QStatusBar { background-color: #3c3c3c; color: #f0f0f0; }
                    QTabWidget::pane { border: 1px solid #444; } /* Слегка изменим цвет */
                    QTabBar::tab { background: #3c3c3c; color: #f0f0f0; padding: 5px; border: 1px solid #444; border-bottom: none; }
                    QTabBar::tab:selected { background: #555; }
                    QTabBar::tab:!selected { color: #a0a0a0; background: #2d2d2d;} /* Улучшим вид неактивных вкладок */
                    QPushButton { background-color: #555; color: #f0f0f0; border: 1px solid #666; padding: 5px; min-width: 60px;} /* Добавим min-width */
                    QPushButton:hover { background-color: #666; }
                    QPushButton:pressed { background-color: #444; }
                    QLabel { color: #f0f0f0; } /* Цвет для QLabel */
                    /* Добавьте стили для других виджетов по мере необходимости */
                """)
        else:
            # Сброс к стилю по умолчанию (или загрузка светлого qss)
            self.setStyleSheet("")  # Используем стиль ОС/светлый qdarktheme, если он был
            try:
                import qdarktheme
                qdarktheme.setup(theme='light')  # Попробуем сбросить qdarktheme на светлый
                logger.info("Сброс на светлую тему (qdarktheme light).")
            except ImportError:
                logger.info("Сброс на системную тему.")

    def _integrate_plugins_ui(self):
        """Интегрирует UI компоненты загруженных плагинов."""
        # Этот метод вызывается ПОСЛЕ загрузки плагинов
        # Основная регистрация происходит в on_load плагинов
        # Здесь можно выполнить пост-обработку, если нужно
        logger.info("Интеграция UI плагинов завершена (пост-обработка).")
        self.status_bar.showMessage("Готово", 3000)  # Обновляем статус после загрузки

    # --- Методы API для плагинов (вызываются из BasePlugin) ---

    def _find_or_create_menu(self, menu_path: str) -> Optional[QMenu]:
        """Находит или создает меню/подменю по пути 'Menu/SubMenu/...'."""
        parts = menu_path.strip('/').split('/')
        if not parts:
            return None

        # Ищем корневое меню в кэше или менюбаре
        root_menu_name = parts[0]
        if root_menu_name in self._menus:
            current_menu = self._menus[root_menu_name]
        else:
            # Ищем в менюбаре по тексту (без '&')
            found_root = None
            for action in self.menu_bar.actions():
                if action.menu() and action.text().replace('&', '') == root_menu_name:
                    found_root = action.menu()
                    break
            if found_root:
                current_menu = found_root
                self._menus[root_menu_name] = current_menu  # Добавляем в кэш
            else:
                # Если не нашли, создаем новое корневое меню
                logger.debug(f"Создание нового корневого меню: '{root_menu_name}'")
                current_menu = self.menu_bar.addMenu(f"&{root_menu_name}")  # Добавляем '&' для акселератора
                self._menus[root_menu_name] = current_menu

        # Проходим по остальным частям пути
        for i in range(1, len(parts)):
            part = parts[i]
            found = False
            # Ищем существующее подменю
            for action in current_menu.actions():
                if action.menu() and action.text().replace('&', '') == part:
                    current_menu = action.menu()
                    found = True
                    break
            if not found:
                # Если не найдено, создаем подменю
                logger.debug(f"Создание подменю '{part}' в '{current_menu.title()}'")
                # Используем '&' только если его нет в названии
                menu_text = f"&{part}" if '&' not in part else part
                new_menu = current_menu.addMenu(menu_text)
                current_menu = new_menu
                # Не добавляем подменю в кэш _menus, только корневые

        return current_menu

    def register_menu_action(self, plugin_name: str, menu_path: str, action: QAction):
        """Регистрирует QAction плагина в главном меню."""
        path_parts = menu_path.strip('/').split('/')
        if len(path_parts) < 1:
            logger.error(f"Плагин '{plugin_name}': Некорректный путь меню '{menu_path}'")
            return

        target_menu = self._find_or_create_menu("/".join(path_parts))  # Передаем полный путь

        if target_menu:
            # TODO: Проверка на дубликаты действий?
            action_text = action.text().replace('&', '')
            logger.debug(f"Добавление действия '{action_text}' в меню '{target_menu.title()}'")
            target_menu.addAction(action)
        else:
            logger.error(f"Плагин '{plugin_name}': Не удалось найти или создать меню для '{menu_path}'")

    def register_toolbar_widget(self, section_path: str, widget: QWidget):
        """Регистрирует виджет (часто QAction) на панели инструментов."""
        # TODO: Реализовать создание отдельных QToolBar для разных секций?
        target_toolbar = self.tool_bar  # Пока добавляем всё в главный тулбар
        widget_text = getattr(widget, 'text', type(widget).__name__)
        # Убираем '&' из текста для лога
        widget_text = widget_text().replace('&', '') if callable(widget_text) else str(widget_text).replace('&', '')

        logger.debug(f"Добавление виджета '{widget_text}' в тулбар (секция '{section_path}')")

        if isinstance(widget, QAction):
            target_toolbar.addAction(widget)
        else:
            target_toolbar.addWidget(widget)

    def register_tab(self, plugin_name: str, tab_name: str, widget: QWidget):
        """Регистрирует виджет как новую вкладку в центральной области."""
        full_tab_name = f"{tab_name}"  # Имя плагина в скобках может быть излишним
        # Проверим, нет ли уже вкладки с таким именем (или от этого плагина?)
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == full_tab_name:
                logger.warning(
                    f"Плагин '{plugin_name}': Вкладка с именем '{full_tab_name}' уже существует. Новая вкладка не добавлена.")
                # Может, переключиться на существующую?
                # self.tab_widget.setCurrentIndex(i)
                return

        logger.debug(f"Добавление вкладки '{full_tab_name}' от плагина '{plugin_name}'")
        index = self.tab_widget.addTab(widget, full_tab_name)
        self.tab_widget.setTabToolTip(index, f"Вкладка от плагина '{plugin_name}'")  # Добавим подсказку
        self.tab_widget.setCurrentIndex(index)

    def close_tab(self, index: int):
        """Закрывает вкладку по индексу."""
        widget = self.tab_widget.widget(index)
        tab_name = self.tab_widget.tabText(index)
        logger.debug(f"Запрос на закрытие вкладки '{tab_name}' (индекс {index})")
        # TODO: Спросить у виджета, можно ли его закрыть (сохранить изменения?)
        # if hasattr(widget, 'can_close') and not widget.can_close():
        #    return # Виджет не разрешает закрытие
        self.tab_widget.removeTab(index)
        # Явно удаляем виджет, чтобы вызвать его деструктор и очистить ресурсы
        widget.deleteLater()
        logger.debug(f"Вкладка '{tab_name}' удалена.")

    def update_status(self, message: str, timeout: int = 0):
        """Обновляет сообщение в строке состояния."""
        if timeout > 0:
            self.status_bar.showMessage(message, timeout)
        else:
            self.status_bar.showMessage(message)  # Постоянное сообщение

    def closeEvent(self, event):
        """Переопределяем событие закрытия окна для выгрузки плагинов."""
        logger.info("Получено событие закрытия окна.")
        # TODO: Спросить подтверждение, если есть несохраненные данные

        # Выгрузка плагинов
        try:
            self.plugin_manager.unload_all()
        except Exception as e:
            logger.error(f"Ошибка при выгрузке плагинов: {e}", exc_info=True)
            # Продолжить закрытие несмотря на ошибку? Или спросить пользователя?

        # Принять событие закрытия
        event.accept()
        logger.info("Приложение завершает работу.")
