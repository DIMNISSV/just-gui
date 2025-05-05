# src/just_gui/core/view_manager.py
import json
import logging
from functools import partial
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from PySide6.QtCore import Slot, QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QWidget, QTabWidget, QMessageBox

from ..plugins.base import ViewFactory

if TYPE_CHECKING:
    from .app import AppCore
    from .ui_manager import UIManager

logger = logging.getLogger(__name__)


class ViewManager(QObject):
    """Управляет объявлениями, открытием и состоянием представлений (вкладок)."""

    def __init__(self, app_core: 'AppCore', ui_manager: 'UIManager', parent: Optional[QObject] = None):
        super().__init__(parent)
        self.app_core = app_core
        self.ui_manager = ui_manager
        self.tab_widget: Optional[QTabWidget] = ui_manager.tab_widget

        self._declared_views: Dict[str, Dict[str, Tuple[str, ViewFactory]]] = {}
        self._open_view_widgets: Dict[QWidget, Tuple[str, str]] = {}

        if self.tab_widget:
            self.tab_widget.tabCloseRequested.connect(self._handle_tab_close_request)
        else:
            logger.error("ViewManager: TabWidget не был предоставлен UIManager!")

        # Статические действия меню добавляются из AppCore._add_menu_actions()

    def _add_menu_actions(self):
        """Добавляет статические действия в меню 'Файл' и 'Вид'."""
        file_menu = self.ui_manager.find_or_create_menu("Файл")
        if file_menu and not any(a.text() == "Сохранить &вид" for a in file_menu.actions()):
            save_view_action = QAction(QIcon.fromTheme("document-save"), "Сохранить &вид", self.app_core)
            save_view_action.triggered.connect(self.save_view_state)
            target_action = next((act for act in reversed(file_menu.actions()) if not act.isSeparator()), None)
            if target_action:
                file_menu.insertSeparator(target_action)
                file_menu.insertAction(target_action, save_view_action)
            else:
                file_menu.addSeparator()
                file_menu.addAction(save_view_action)

        view_menu = self.ui_manager.find_or_create_menu("Вид")
        if view_menu and not any(a.text() == "&Сбросить вид" for a in view_menu.actions()):
            separator = next((act for act in view_menu.actions() if act.isSeparator()),
                             None) or view_menu.addSeparator()
            reset_view_action = QAction(QIcon.fromTheme("view-refresh"), "&Сбросить вид", self.app_core)
            reset_view_action.triggered.connect(self.reset_view_state)
            view_menu.addAction(reset_view_action)  # Добавляем в конец

    def declare_view(self, plugin_name: str, view_id: str, name: str, factory: ViewFactory):

        if plugin_name not in self._declared_views: self._declared_views[plugin_name] = {}
        if view_id in self._declared_views[plugin_name]: logger.warning(
            f"Плагин '{plugin_name}' повторно объявляет '{view_id}'.")
        self._declared_views[plugin_name][view_id] = (name, factory)

    def update_view_menu(self):

        view_menu = self.ui_manager.get_view_menu()
        if not view_menu:
            logger.error("Меню 'Вид' не найдено!")
            return
        logger.debug("ViewManager: Обновление меню 'Вид'...")
        separator = None
        actions_to_remove = []
        for action in view_menu.actions():
            if action.isSeparator():
                separator = action
                break
            else:
                actions_to_remove.append(action)
        for action in actions_to_remove:
            view_menu.removeAction(action)
            action.deleteLater()
        if separator is None:
            logger.error("Разделитель в меню 'Вид' не найден!")
            return

        added_items = False
        sorted_plugins = sorted(self._declared_views.keys())
        actions_to_insert = []
        for plugin_name in sorted_plugins:
            plugin_views = self._declared_views.get(plugin_name, {})
            if not plugin_views: continue
            plugin_menu_path = f"Вид/{plugin_name}"
            submenu = self.ui_manager.find_or_create_menu(plugin_menu_path)
            if not submenu:
                logger.error(f"Не удалось создать подменю '{plugin_name}' в 'Вид'.")
                continue
            submenu_action = submenu.menuAction()
            if submenu_action and submenu_action not in actions_to_insert:
                is_already_in_view_menu = any(a == submenu_action for a in view_menu.actions())
                if not is_already_in_view_menu: actions_to_insert.append(submenu_action)
            submenu.clear()
            sorted_view_ids = sorted(plugin_views.keys())
            for view_id in sorted_view_ids:
                view_name, _ = plugin_views[view_id]
                action = QAction(view_name, self.app_core)
                action.triggered.connect(partial(self.open_view_by_id, plugin_name, view_id))
                submenu.addAction(action)
                added_items = True
        if actions_to_insert:
            for action_to_insert in reversed(actions_to_insert): view_menu.insertAction(separator, action_to_insert)
        elif not any(not a.isSeparator() and not a.text().endswith("Сбросить вид") for a in view_menu.actions()):
            no_views_action = QAction("Нет доступных представлений", self.app_core)
            no_views_action.setEnabled(False)
            view_menu.insertAction(separator, no_views_action)
        logger.debug("ViewManager: Меню 'Вид' обновлено.")

    @Slot(str, str)
    def open_view_by_id(self, plugin_name: str, view_id: str):

        if not self.tab_widget:
            logger.error("TabWidget не инициализирован!")
            return
        logger.info(f"Запрос на открытие: plugin='{plugin_name}', view_id='{view_id}'")
        try:
            view_name, factory = self._declared_views[plugin_name][view_id]
            logger.debug(f"Вызов фабрики для '{view_name}'...")
            widget = factory()
            if not isinstance(widget, QWidget): raise TypeError("Фабрика должна возвращать QWidget")
            index = self.tab_widget.addTab(widget, view_name)
            self.tab_widget.setTabToolTip(index, f"{view_name} (Плагин: {plugin_name})")
            self.tab_widget.setCurrentIndex(index)
            self._open_view_widgets[widget] = (plugin_name, view_id)
            logger.info(f"Представление '{view_name}' открыто.")
        except KeyError:
            msg = f"Не найдено объявленное представление: plugin='{plugin_name}', view_id='{view_id}'"
            logger.error(
                msg)
            QMessageBox.warning(self.app_core, "Ошибка открытия", msg)
        except Exception as e:
            msg = f"Ошибка открытия '{plugin_name}/{view_id}': {e}"
            logger.error(msg,
                         exc_info=True)
            QMessageBox.critical(
                self.app_core, "Критическая ошибка", msg)

    def open_all_declared_views(self):
        """Открывает все объявленные представления по умолчанию."""
        logger.debug("Открытие всех объявленных представлений...")
        opened_count = 0
        for plugin_name, views in self._declared_views.items():
            for view_id, (view_name, factory) in views.items():
                # Проверяем, не открыта ли уже вкладка (на всякий случай)
                is_open = any(p == plugin_name and v == view_id for p, v in self._open_view_widgets.values())
                if not is_open:
                    logger.debug(f"Открытие вида по умолчанию: {plugin_name}/{view_id}")
                    self.open_view_by_id(plugin_name, view_id)
                    opened_count += 1
                else:
                    logger.debug(f"Вид {plugin_name}/{view_id} уже был открыт, пропуск.")
        logger.info(f"Открыто представлений по умолчанию: {opened_count}")
        # Можно установить активной первую вкладку, если они были открыты
        if self.tab_widget and self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)

    @Slot(int)
    def _handle_tab_close_request(self, index: int):

        if not self.tab_widget: return
        widget = self.tab_widget.widget(index)
        if widget:
            tab_name = self.tab_widget.tabText(index)
            logger.debug(f"Запрос на закрытие вкладки '{tab_name}'")
            unsubscribe_callback = widget.property("unsubscribe_callback")
            if callable(unsubscribe_callback):
                try:
                    logger.debug(f"Вызов отписки для '{tab_name}'...")
                    unsubscribe_callback()
                except Exception as e:
                    logger.error(f"Ошибка отписки '{tab_name}': {e}", exc_info=True)
            self.tab_widget.removeTab(index)
            if widget in self._open_view_widgets:
                plugin_name, view_id = self._open_view_widgets.pop(widget)
                logger.info(f"Вкладка '{tab_name}' ({plugin_name}/{view_id}) закрыта.")
            widget.deleteLater()

    def close_all_tabs(self, force=False):

        if not self.tab_widget: return
        logger.debug(f"Закрытие всех вкладок (force={force})")
        while self.tab_widget.count() > 0: self._handle_tab_close_request(0)
        if self._open_view_widgets:
            logger.warning(f"_open_view_widgets не пуст: {self._open_view_widgets}")
            self._open_view_widgets.clear()
        logger.info("Все вкладки закрыты.")

    def load_view_state(self) -> bool:
        """Загружает состояние вида из файла. Возвращает True, если вид был успешно загружен и не пуст."""
        if not self.tab_widget: return False
        state_file = self.app_core.view_state_file
        if not state_file.exists():
            logger.info(f"Файл состояния вида не найден ({state_file}).")
            return False

        logger.info(f"Загрузка состояния вида из: {state_file}")
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            open_tabs_info = state_data.get("open_tabs", [])
            if not open_tabs_info:
                logger.info("Сохраненный вид пуст.")
                return False  # Считаем, что вид не загружен, если он пуст

            logger.debug(f"Восстановление вкладок: {open_tabs_info}")
            self.close_all_tabs(force=True)
            opened_count = 0
            for tab_info in open_tabs_info:
                p_name, v_id = tab_info.get("plugin"), tab_info.get("view_id")
                if p_name and v_id and p_name in self._declared_views and v_id in self._declared_views[p_name]:
                    self.open_view_by_id(p_name, v_id)
                    opened_count += 1
                else:
                    logger.warning(f"Сохраненное '{p_name}/{v_id}' не найдено.")

            idx = state_data.get("current_index", -1)
            if 0 <= idx < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(idx)
            elif self.tab_widget.count() > 0:
                self.tab_widget.setCurrentIndex(0)

            logger.info(f"Вид загружен ({opened_count} вкладок).")
            return True  # Вид успешно загружен и не пуст
        except Exception as e:
            msg = f"Ошибка загрузки или применения состояния вида из {state_file}: {e}"
            logger.error(msg, exc_info=True)
            QMessageBox.warning(self.app_core, "Ошибка загрузки вида", f"{msg}\nБудет использован вид по умолчанию.")
            self.close_all_tabs(force=True)
            return False  # Не удалось загрузить

    @Slot()
    def save_view_state(self):

        state_file = self.app_core.view_state_file
        logger.info(f"Сохранение вида в: {state_file}")
        open_tabs_info = []
        if self.tab_widget:
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if widget in self._open_view_widgets:
                    p_name, v_id = self._open_view_widgets[widget]
                    open_tabs_info.append({"plugin": p_name, "view_id": v_id})
            state_data = {"open_tabs": open_tabs_info, "current_index": self.tab_widget.currentIndex()}
            try:
                state_file.parent.mkdir(parents=True, exist_ok=True)
                with open(state_file, 'w', encoding='utf-8') as f:
                    json.dump(state_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Вид сохранен ({len(open_tabs_info)} вкладок).")
                self.ui_manager.update_status("Вид сохранен.", 3000)
            except IOError as e:
                msg = f"Ошибка записи файла вида {state_file}: {e}"
                logger.error(msg,
                             exc_info=True)
                QMessageBox.critical(
                    self.app_core, "Ошибка сохранения вида", msg)
            except Exception as e:
                msg = f"Непредвиденная ошибка сохранения вида: {e}"
                logger.error(msg,
                             exc_info=True)
                QMessageBox.critical(
                    self.app_core, "Ошибка сохранения вида", msg)
        else:
            logger.error("Не могу сохранить вид: TabWidget не существует.")

    @Slot()
    def reset_view_state(self):
        """Сбрасывает вид и открывает все вкладки по умолчанию."""
        reply = QMessageBox.question(self.app_core, "Сброс вида",
                                     "Вы уверены, что хотите закрыть все вкладки и сбросить сохраненный вид?\n(Все доступные представления будут открыты заново)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Сброс вида...")
            self.close_all_tabs(force=True)
            state_file = self.app_core.view_state_file
            try:
                if state_file.exists():
                    state_file.unlink()
                    logger.info(f"Файл вида удален: {state_file}")
            except OSError as e:
                msg = f"Не удалось удалить файл сохраненного вида {state_file}: {e}"
                logger.error(msg, exc_info=True)
                QMessageBox.warning(self.app_core, "Ошибка сброса вида", msg)

            logger.info("Открытие представлений по умолчанию после сброса...")
            self.open_all_declared_views()
            self.ui_manager.update_status("Вид сброшен и восстановлен по умолчанию.", 3000)
