# src/just_gui/core/app.py
import logging
import sys
import json
from functools import partial
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Callable, cast

import platformdirs

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QToolBar, QStatusBar,
    QMenuBar, QMessageBox, QMenu, QFileDialog
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QSize, Qt, Slot

from ..plugins.manager import PluginManager
from ..state.manager import StateManager
from ..events.bus import EventBus
from ..utils.config_loader import load_toml, ConfigError
from ..plugins.base import ViewFactory

logger = logging.getLogger(__name__)

APP_NAME = "just-gui"
APP_AUTHOR = "dimnissv"


class AppCore(QMainWindow):
    """
    Главный класс приложения just-gui.
    """

    def __init__(self, profile_path: str):
        super().__init__()
        self.profile_path = Path(profile_path)
        self.profile_name = self.profile_path.stem
        self.config: Dict = {}

        logger.debug("AppCore: Initializing core components...")
        self.event_bus = EventBus()
        self.state_manager = StateManager()
        self.plugin_manager = PluginManager(
            app_core=self, state_manager=self.state_manager, event_bus=self.event_bus
        )

        # Хранилища для управления видом
        self._declared_views: Dict[str, Dict[str, Tuple[str, ViewFactory]]] = {}
        self._open_view_widgets: Dict[QWidget, Tuple[str, str]] = {}
        self._view_menu: Optional[QMenu] = None
        # --- ИЗМЕНЕНО: Новый кэш для ВСЕХ меню по полному пути ---
        self._all_menus_cache: Dict[str, QMenu] = {}
        # --- Старый кэш self._menus больше не нужен ---

        self._load_app_config()
        self._init_ui()

        self.setWindowTitle(f"just-gui: {self.profile_name}")
        logger.debug("AppCore: __init__ complete.")

    
    @property
    def view_state_file(self) -> Path:
        config_dir = Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))
        profile_view_dir = config_dir / "profiles" / self.profile_name
        profile_view_dir.mkdir(parents=True, exist_ok=True)
        return profile_view_dir / "view_state.json"

    async def initialize(self):
        logger.info("AppCore: Starting asynchronous initialization...")
        try:
            await self.plugin_manager.load_profile(str(self.profile_path))
        except Exception as e:
            logger.error(f"Критическая ошибка при асинхронной загрузке профиля: {e}", exc_info=True)
            raise
        self._update_view_menu()
        self._load_view_state()
        logger.info("AppCore: Asynchronous initialization complete.")
        if self.tab_widget.count() == 0:
            self.update_status("Плагины загружены. Откройте представление из меню 'Вид'.", 5000)

    def _load_app_config(self):
        logger.debug(f"Загрузка конфигурации приложения из {self.profile_path}")
        try:
            if not self.profile_path.is_file():
                logger.warning(f"Файл профиля не найден: {self.profile_path}. Используются значения по умолчанию.")
                return
            profile_data = load_toml(self.profile_path)
            self.config = profile_data.get("config", {})
            logger.info(f"Загружена конфигурация приложения: {self.config}")
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
                logger.info(f"Уровень логирования для 'just_gui' установлен на: {log_level_str}")
            except AttributeError:
                logger.warning(f"Неверный уровень логирования '{log_level_str}' в профиле. Используется INFO.")
                logging.getLogger('just_gui').setLevel(logging.INFO)
        except (ConfigError) as e:
            logger.warning(f"Ошибка загрузки конфигурации из профиля: {e}. Используются значения по умолчанию.")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при загрузке конфигурации: {e}", exc_info=True)

    def _init_ui(self):
        logger.debug("Инициализация UI главного окна...")
        self.menu_bar = self.menuBar()
        # self._menus больше не нужен
        self.tool_bar = QToolBar("Main Toolbar")
        self.tool_bar.setIconSize(QSize(24, 24))
        self.addToolBar(self.tool_bar)
        self._toolbars: Dict[str, QToolBar] = {"Main Toolbar": self.tool_bar}
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._handle_tab_close_request)
        self.tab_widget.setMovable(True)
        self.setCentralWidget(self.tab_widget)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Инициализация...", 0)
        theme = self.config.get("theme", "light")
        self.apply_theme(theme)
        self._setup_default_menus()  # Использует _all_menus_cache
        logger.debug("UI главного окна инициализирован.")

    def _setup_default_menus(self):
        """Создает базовые пункты меню и кэширует их."""
        # Меню Файл
        file_menu = self.menu_bar.addMenu("&Файл")
        # --- ИЗМЕНЕНО: Используем новый кэш ---
        self._all_menus_cache["Файл"] = file_menu
        save_view_action = QAction(QIcon.fromTheme("document-save"), "Сохранить &вид", self)
        save_view_action.triggered.connect(self._save_view_state)
        file_menu.addAction(save_view_action)
        file_menu.addSeparator()
        exit_icon = QIcon.fromTheme("application-exit")
        exit_action = QAction(exit_icon, "&Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню Вид
        self._view_menu = self.menu_bar.addMenu("&Вид")
        # --- ИЗМЕНЕНО: Используем новый кэш ---
        self._all_menus_cache["Вид"] = self._view_menu
        # Действия добавятся позже

        # Меню Инструменты
        tools_menu = self.menu_bar.addMenu("&Инструменты")
        # --- ИЗМЕНЕНО: Используем новый кэш ---
        self._all_menus_cache["Инструменты"] = tools_menu

        # Меню Помощь
        help_menu = self.menu_bar.addMenu("&Помощь")
        # --- ИЗМЕНЕНО: Используем новый кэш ---
        self._all_menus_cache["Помощь"] = help_menu
        about_icon = QIcon.fromTheme("help-about")
        about_action = QAction(about_icon, "&О программе", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    # --- ИЗМЕНЕНО: Полностью переработанный _find_or_create_menu ---
    def _find_or_create_menu(self, menu_path: str) -> Optional[QMenu]:
        """
        Находит или создает меню/подменю по пути 'Root/Sub/...'
        Использует кэш _all_menus_cache и проверяет валидность объектов.
        """
        full_path = menu_path.strip('/')
        if not full_path:
            logger.error("Пустой путь к меню не допускается.")
            return None

        # 1. Проверка кэша для всего пути
        if full_path in self._all_menus_cache:
            cached_menu = self._all_menus_cache[full_path]
            try:
                # Проверяем, жив ли C++ объект
                _ = cached_menu.title()
                logger.debug(f"Cache hit для меню: '{full_path}'")
                return cached_menu
            except RuntimeError:
                logger.warning(f"Объект меню из кэша для '{full_path}' был удален. Попытка пересоздать.")
                del self._all_menus_cache[full_path]
                # Продолжаем выполнение для пересоздания

        # 2. Пошаговый поиск или создание
        parts = full_path.split('/')
        current_menu_obj: Optional[QMenu] = None
        current_path_part = ""

        # Обработка корневого меню
        root_name = parts[0]
        current_path_part = root_name
        if current_path_part in self._all_menus_cache:
            # Проверяем кэш для корня
            cached_root = self._all_menus_cache[current_path_part]
            try:
                _ = cached_root.title(); current_menu_obj = cached_root
            except RuntimeError:
                del self._all_menus_cache[current_path_part]; current_menu_obj = None

        if current_menu_obj is None:
            # Ищем или создаем корневое меню в menu_bar
            found_root = None
            for action in self.menu_bar.actions():
                menu = action.menu()
                # Сравниваем текст без '&'
                if menu and menu.title().replace('&', '') == root_name:
                    found_root = menu
                    break
            if found_root:
                current_menu_obj = found_root
            else:
                # Создаем новое корневое меню
                logger.debug(f"Создание корневого меню: '{root_name}'")
                menu_text = f"&{root_name}" if '&' not in root_name else root_name
                current_menu_obj = self.menu_bar.addMenu(menu_text)

            # Добавляем/обновляем в кэше
            if current_menu_obj:
                self._all_menus_cache[current_path_part] = current_menu_obj
            else:
                logger.error(f"Не удалось найти или создать корневое меню '{root_name}'")
                return None  # Не можем продолжить без корневого меню

        # Обработка подменю
        for i in range(1, len(parts)):
            part_name = parts[i]
            current_path_part += f"/{part_name}"  # Обновляем ключ пути для кэша
            next_menu_obj: Optional[QMenu] = None

            # Проверяем кэш для текущего пути
            if current_path_part in self._all_menus_cache:
                cached_submenu = self._all_menus_cache[current_path_part]
                try:
                    _ = cached_submenu.title(); next_menu_obj = cached_submenu
                except RuntimeError:
                    del self._all_menus_cache[current_path_part]; next_menu_obj = None

            if next_menu_obj is None:
                # Ищем или создаем подменю в current_menu_obj
                found_submenu = None
                for action in current_menu_obj.actions():
                    submenu = action.menu()
                    # Сравниваем текст без '&'
                    if submenu and submenu.title().replace('&', '') == part_name:
                        # Проверяем валидность найденного подменю
                        try:
                            _ = submenu.title(); found_submenu = submenu; break
                        except RuntimeError:
                            # Найденное подменю удалено, удаляем связанный action
                            logger.warning(
                                f"Обнаружено удаленное подменю для '{part_name}'. Удаление связанного действия.")
                            current_menu_obj.removeAction(action)
                            action.deleteLater()
                if found_submenu:
                    next_menu_obj = found_submenu
                else:
                    # Создаем новое подменю
                    logger.debug(f"Создание подменю '{part_name}' в '{current_menu_obj.title().replace('&', '')}'")
                    menu_text = f"&{part_name}" if '&' not in part_name else part_name
                    next_menu_obj = current_menu_obj.addMenu(menu_text)

                # Добавляем/обновляем в кэше
                if next_menu_obj:
                    self._all_menus_cache[current_path_part] = next_menu_obj
                else:
                    logger.error(
                        f"Не удалось найти или создать подменю '{part_name}' в '{current_menu_obj.title().replace('&', '')}'")
                    return None  # Прерываем, если не удалось создать подменю

            # Переходим на следующий уровень
            current_menu_obj = next_menu_obj

        # Возвращаем найденное или созданное меню самого глубокого уровня
        return current_menu_obj

    # --- КОНЕЦ ИЗМЕНЕННОГО _find_or_create_menu ---

    def _update_view_menu(self):
        
        if not self._view_menu: logger.error("Меню 'Вид' не инициализировано!"); return
        logger.debug("Обновление меню 'Вид'...")
        separator = None;
        actions_to_remove = []
        for action in self._view_menu.actions():
            if action.isSeparator():
                separator = action; break
            else:
                actions_to_remove.append(action)
        for action in actions_to_remove: self._view_menu.removeAction(action); action.deleteLater()
        if separator is None:
            separator = self._view_menu.addSeparator()
            reset_view_action = QAction(QIcon.fromTheme("view-refresh"), "&Сбросить вид", self)
            reset_view_action.triggered.connect(self._reset_view_state)
            self._view_menu.addAction(reset_view_action)  # Добавляем ПОСЛЕ разделителя

        added_items = False;
        sorted_plugins = sorted(self._declared_views.keys());
        plugin_menus: Dict[str, QMenu] = {}
        actions_to_insert = []
        for plugin_name in sorted_plugins:
            plugin_views = self._declared_views[plugin_name]
            if not plugin_views: continue
            # --- Используем _find_or_create_menu для получения/создания подменю плагина ---
            plugin_menu_path = f"Вид/{plugin_name}"  # Полный путь к подменю
            submenu = self._find_or_create_menu(plugin_menu_path)
            if not submenu:
                logger.error(f"Не удалось создать подменю для плагина '{plugin_name}' в меню 'Вид'.")
                continue  # Пропускаем этот плагин, если не удалось создать подменю
            # ---

            # Если это подменю еще не было добавлено в actions_to_insert
            if submenu.menuAction() not in actions_to_insert:
                actions_to_insert.append(submenu.menuAction())

            # Очищаем существующие действия в подменю перед добавлением новых
            submenu.clear()

            sorted_view_ids = sorted(plugin_views.keys())
            for view_id in sorted_view_ids:
                view_name, _ = plugin_views[view_id]
                action = QAction(view_name, self)
                action.triggered.connect(partial(self.open_view_by_id, plugin_name, view_id))
                submenu.addAction(action)  # Добавляем действие в подменю
                added_items = True

        # --- ИЗМЕНЕНО: Логика вставки actions_to_insert ---
        # Вставляем действия (подменю плагинов) перед разделителем
        if actions_to_insert:
            for action_to_insert in reversed(
                    actions_to_insert):  # Вставляем в обратном порядке, чтобы сохранить сортировку
                self._view_menu.insertAction(separator, action_to_insert)
        elif not any(not a.isSeparator() and a.text() != "&Сбросить вид" for a in self._view_menu.actions()):
            # Добавляем заглушку, если нет других действий
            no_views_action = QAction("Нет доступных представлений", self)
            no_views_action.setEnabled(False)
            self._view_menu.insertAction(separator, no_views_action)

        logger.debug("Меню 'Вид' обновлено.")

    def declare_view(self, plugin_name: str, view_id: str, name: str, factory: ViewFactory):
        
        if plugin_name not in self._declared_views: self._declared_views[plugin_name] = {}
        if view_id in self._declared_views[plugin_name]: logger.warning(
            f"Плагин '{plugin_name}' повторно объявляет представление '{view_id}'.")
        self._declared_views[plugin_name][view_id] = (name, factory)

    @Slot(str, str)
    def open_view_by_id(self, plugin_name: str, view_id: str):
        
        logger.info(f"Запрос на открытие представления: plugin='{plugin_name}', view_id='{view_id}'")
        try:
            view_name, factory = self._declared_views[plugin_name][view_id]
            logger.debug(f"Вызов фабрики для '{view_name}'...")
            widget = factory();
            assert isinstance(widget, QWidget)
            index = self.tab_widget.addTab(widget, view_name)
            self.tab_widget.setTabToolTip(index, f"{view_name} (Плагин: {plugin_name})")
            self.tab_widget.setCurrentIndex(index)
            self._open_view_widgets[widget] = (plugin_name, view_id)
            logger.info(f"Представление '{view_name}' ({plugin_name}/{view_id}) открыто как вкладка.")
        except KeyError:
            logger.error(
                f"Не найдено объявленное представление: plugin='{plugin_name}', view_id='{view_id}'")  
        except Exception as e:
            logger.error(f"Ошибка при создании/добавлении виджета '{plugin_name}/{view_id}': {e}",
                         exc_info=True)  

    @Slot(int)
    def _handle_tab_close_request(self, index: int):
        
        widget = self.tab_widget.widget(index)
        if widget:
            tab_name = self.tab_widget.tabText(index)
            logger.debug(f"Запрос на закрытие вкладки '{tab_name}' (индекс {index})")
            unsubscribe_callback = widget.property("unsubscribe_callback")
            if callable(unsubscribe_callback):
                try:
                    logger.debug(f"Вызов колбэка отписки для '{tab_name}'..."); unsubscribe_callback()
                except Exception as e:
                    logger.error(f"Ошибка колбэка отписки для '{tab_name}': {e}", exc_info=True)
            self.tab_widget.removeTab(index)
            if widget in self._open_view_widgets:
                plugin_name, view_id = self._open_view_widgets.pop(widget)
                logger.info(f"Вкладка '{tab_name}' ({plugin_name}/{view_id}) закрыта.")
            else:
                logger.warning(f"Закрываемый виджет '{tab_name}' не найден в _open_view_widgets.")
            widget.deleteLater()
        else:
            logger.warning(f"Попытка закрыть вкладку {index}, но виджет не найден.")

    def _load_view_state(self):
        
        state_file = self.view_state_file
        if not state_file.exists(): logger.info(f"Файл состояния вида не найден ({state_file})."); return
        logger.info(f"Загрузка состояния вида из: {state_file}")
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            open_tabs_info = state_data.get("open_tabs", []);
            logger.debug(f"Восстановление вкладок: {open_tabs_info}")
            self._close_all_tabs(force=True)
            opened_count = 0
            for tab_info in open_tabs_info:
                plugin_name, view_id = tab_info.get("plugin"), tab_info.get("view_id")
                if plugin_name and view_id:
                    if plugin_name in self._declared_views and view_id in self._declared_views[plugin_name]:
                        self.open_view_by_id(plugin_name, view_id);
                        opened_count += 1
                    else:
                        logger.warning(f"Сохраненное представление '{plugin_name}/{view_id}' не найдено.")
                else:
                    logger.warning(f"Некорректная запись в state: {tab_info}")
            current_index = state_data.get("current_index", -1)
            if 0 <= current_index < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(current_index)
            elif self.tab_widget.count() > 0:
                self.tab_widget.setCurrentIndex(0)
            logger.info(f"Состояние вида загружено (восстановлено {opened_count} вкладок).")
        except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
            logger.error(f"Ошибка загрузки состояния вида из {state_file}: {e}", exc_info=True)
            # QMessageBox ...
            self._close_all_tabs(force=True)

    def _save_view_state(self):
        
        state_file = self.view_state_file;
        logger.info(f"Сохранение вида в: {state_file}")
        open_tabs_info = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if widget in self._open_view_widgets:
                plugin_name, view_id = self._open_view_widgets[widget]
                open_tabs_info.append({"plugin": plugin_name, "view_id": view_id})
            else:
                logger.warning(f"Виджет вкладки {i} не найден в _open_view_widgets.")
        state_data = {"open_tabs": open_tabs_info, "current_index": self.tab_widget.currentIndex()}
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Вид сохранен ({len(open_tabs_info)} вкладок).")
        except IOError as e:
            logger.error(f"Ошибка записи состояния вида {state_file}: {e}")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка сохранения вида: {e}", exc_info=True)

    def _close_all_tabs(self, force=False):
        
        logger.debug(f"Запрос на закрытие всех вкладок (force={force})")
        while self.tab_widget.count() > 0: self._handle_tab_close_request(0)
        if self._open_view_widgets: logger.warning(
            f"_open_view_widgets не пуст: {self._open_view_widgets}"); self._open_view_widgets.clear()
        logger.info("Все вкладки закрыты.")

    def _reset_view_state(self):
        
        reply = QMessageBox.question(self, "Сброс вида", "...",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Сброс состояния вида...")
            self._close_all_tabs(force=True)
            state_file = self.view_state_file
            try:
                if state_file.exists():
                    state_file.unlink(); logger.info(f"Файл состояния вида удален: {state_file}"); self.update_status(
                        "Вид сброшен.", 3000)
                else:
                    logger.info("Файл состояния вида не найден."); self.update_status("Вид сброшен (файл не найден).",
                                                                                      3000)
            except OSError as e:
                logger.error(f"Не удалось удалить файл состояния вида {state_file}: {e}")  

    def closeEvent(self, event):
        
        logger.info("Получено событие закрытия окна.")
        self._save_view_state()
        try:
            self.plugin_manager.unload_all()
        except Exception as e:
            logger.error(f"Ошибка при выгрузке плагинов: {e}", exc_info=True)
        event.accept();
        logger.info("Приложение завершает работу.")

    def show_about_dialog(self):
        
        try:
            from .. import __version__
        except ImportError:
            __version__ = "N/A"
        QMessageBox.about(self, "О программе just-gui",
                          f"<b>just-gui</b><br>Версия: {__version__}<br>Автор профиля: {APP_AUTHOR}<br>...")

    def apply_theme(self, theme_name: str):
        
        logger.info(f"Применение темы: {theme_name}")
        style = ""
        try:
            import qdarktheme
            style = qdarktheme.load_stylesheet(theme_name.lower());
            logger.info(f"Применена тема qdarktheme '{theme_name}'.")
        except ImportError:
            logger.warning("Библиотека qdarktheme не найдена.");  
        self.setStyleSheet(style)

    # --- Методы API для плагинов, использующие _find_or_create_menu ---
    def register_menu_action(self, plugin_name: str, menu_path: str, action: QAction):
        """Регистрирует QAction плагина в главном меню."""
        # Используем улучшенный _find_or_create_menu
        target_menu = self._find_or_create_menu(menu_path)
        if target_menu:
            action_text = action.text().replace('&', '')
            logger.debug(
                f"Добавление действия '{action_text}' в меню '{target_menu.title().replace('&', '')}' (плагин: {plugin_name})")
            # Проверяем, нет ли уже такого действия
            for existing_action in target_menu.actions():
                if existing_action.text() == action.text():
                    logger.warning(
                        f"Действие '{action_text}' уже существует в меню '{target_menu.title().replace('&', '')}'. Пропуск.")
                    return
            target_menu.addAction(action)
        else:
            logger.error(
                f"Плагин '{plugin_name}': Не удалось найти или создать меню для '{menu_path}' при регистрации действия.")

    def register_toolbar_widget(self, section_path: str, widget: QWidget):
        
        target_toolbar = self.tool_bar
        widget_text = getattr(widget, 'text', type(widget).__name__)
        widget_text = widget_text().replace('&', '') if callable(widget_text) else str(widget_text).replace('&', '')
        logger.debug(f"Добавление виджета '{widget_text}' в тулбар (секция '{section_path}')")
        if isinstance(widget, QAction):
            target_toolbar.addAction(widget)
        else:
            target_toolbar.addWidget(widget)

    def update_status(self, message: str, timeout: int = 0):
        
        if timeout > 0:
            self.status_bar.showMessage(message, timeout)
        else:
            self.status_bar.showMessage(message)
