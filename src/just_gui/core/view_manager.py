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
    from ..plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class ViewManager(QObject):
    """Manages view declarations, opening, and state (tabs)."""

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
            logger.error("ViewManager: TabWidget was not provided by UIManager!")

        # Static menu actions are added from ViewManager._add_menu_actions()

    def _add_menu_actions(self):
        """Adds static actions to the 'File' and 'View' menus."""
        file_menu = self.ui_manager.find_or_create_menu("Файл")
        if file_menu and not any(a.text() == "Сохранить &вид" for a in file_menu.actions()):
            save_view_action = QAction(QIcon.fromTheme("document-save"), "Save &View", self.app_core)
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
            reset_view_action = QAction(QIcon.fromTheme("view-refresh"), "&Reset View", self.app_core)
            reset_view_action.triggered.connect(self.reset_view_state)
            view_menu.addAction(reset_view_action)

    def declare_view(self, plugin_name: str, view_id: str, name: str, factory: ViewFactory):

        if plugin_name not in self._declared_views: self._declared_views[plugin_name] = {}
        if view_id in self._declared_views[plugin_name]: logger.warning(
            f"Plugin '{plugin_name}' re-declares '{view_id}'.")
        self._declared_views[plugin_name][view_id] = (name, factory)

    def update_view_menu(self):
        """Updates the 'View' menu, using plugin.title for submenus."""
        view_menu = self.ui_manager.get_view_menu()
        if not view_menu: logger.error("'View' menu not found!"); return
        logger.debug("ViewManager: Updating 'View' menu...")

        separator = next((act for act in view_menu.actions() if act.isSeparator()), None)
        if separator is None: logger.error("Separator in 'View' menu not found!"); return

        actions_to_remove = [act for act in view_menu.actions() if act != separator and act.text() != "&Сбросить вид"]
        dynamic_actions = []
        current_action = view_menu.actions()[0] if view_menu.actions() else None
        while current_action and current_action != separator:
            dynamic_actions.append(current_action)
            # More reliable way - get list and find next by index
            all_actions = view_menu.actions()
            try:
                idx = all_actions.index(current_action)
                if idx + 1 < len(all_actions):
                    current_action = all_actions[idx + 1]
                else:
                    current_action = None
            except ValueError:
                current_action = None

        for action in dynamic_actions:
            view_menu.removeAction(action);
            action.deleteLater()

        added_items = False
        actions_to_insert = []
        plugin_manager: Optional['PluginManager'] = getattr(self.app_core, 'plugin_manager', None)
        loaded_plugins_map = plugin_manager.loaded_plugins if plugin_manager else {}

        sorted_plugin_names = sorted(loaded_plugins_map.keys(), key=lambda name: loaded_plugins_map[name].title.lower())

        for plugin_name in sorted_plugin_names:
            # Check if this plugin has declared views
            plugin_views = self._declared_views.get(plugin_name, {})
            if not plugin_views: continue

            plugin = loaded_plugins_map[plugin_name]
            plugin_display_name = plugin.title  # Use title
            plugin_menu_path = f"Вид/{plugin_display_name}"  # Path with display name

            submenu = self.ui_manager.find_or_create_menu(plugin_menu_path)
            if not submenu: logger.error(f"Failed to create submenu '{plugin_display_name}' in 'Вид'."); continue

            submenu_action = submenu.menuAction()
            # Check if the submenu action needs to be added (if it's not already before the separator)
            if submenu_action and not any(
                    a == submenu_action for a in view_menu.actions() if a != separator and a.text() != "&Сбросить вид"):
                actions_to_insert.append(submenu_action)

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
        # Check if only static elements remain
        elif not any(not a.isSeparator() and not a.text().endswith("Сбросить вид") for a in view_menu.actions()):
            no_views_action = QAction("No views available", self.app_core);
            no_views_action.setEnabled(False)
            view_menu.insertAction(separator, no_views_action)

        logger.debug("ViewManager: 'View' menu updated.")

    @Slot(str, str)
    def open_view_by_id(self, plugin_name: str, view_id: str):

        if not self.tab_widget:
            logger.error("TabWidget not initialized!")
            return
        logger.info(f"Request to open: plugin='{plugin_name}', view_id='{view_id}'")
        try:
            view_name, factory = self._declared_views[plugin_name][view_id]
            logger.debug(f"Calling factory for '{view_name}'...")
            widget = factory()
            if not isinstance(widget, QWidget): raise TypeError("Factory must return QWidget")
            index = self.tab_widget.addTab(widget, view_name)
            self.tab_widget.setTabToolTip(index, f"{view_name} (Plugin: {plugin_name})")
            self.tab_widget.setCurrentIndex(index)
            self._open_view_widgets[widget] = (plugin_name, view_id)
            logger.info(f"View '{view_name}' opened.")
        except KeyError:
            msg = f"Declared view not found: plugin='{plugin_name}', view_id='{view_id}'"
            logger.error(
                msg)
            QMessageBox.warning(self.app_core, "Opening Error", msg)
        except Exception as e:
            msg = f"Error opening '{plugin_name}/{view_id}': {e}"
            logger.error(msg,
                         exc_info=True)
            QMessageBox.critical(
                self.app_core, "Critical Error", msg)

    def open_all_declared_views(self):
        """Opens all declared views by default."""
        logger.debug("Opening all declared views...")
        opened_count = 0
        for plugin_name, views in self._declared_views.items():
            for view_id, (view_name, factory) in views.items():
                # Check if the tab is already open (just in case)
                is_open = any(p == plugin_name and v == view_id for p, v in self._open_view_widgets.values())
                if not is_open:
                    logger.debug(f"Opening default view: {plugin_name}/{view_id}")
                    self.open_view_by_id(plugin_name, view_id)
                    opened_count += 1
                else:
                    logger.debug(f"View {plugin_name}/{view_id} was already open, skipping.")
        logger.info(f"Default views opened: {opened_count}")
        # Can set the first tab active if they were opened
        if self.tab_widget and self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)

    @Slot(int)
    def _handle_tab_close_request(self, index: int):

        if not self.tab_widget: return
        widget = self.tab_widget.widget(index)
        if widget:
            tab_name = self.tab_widget.tabText(index)
            logger.debug(f"Tab close request for '{tab_name}'")
            unsubscribe_callback = widget.property("unsubscribe_callback")
            if callable(unsubscribe_callback):
                try:
                    logger.debug(f"Calling unsubscribe for '{tab_name}'...")
                    unsubscribe_callback()
                except Exception as e:
                    logger.error(f"Unsubscribe error for '{tab_name}': {e}", exc_info=True)
            self.tab_widget.removeTab(index)
            if widget in self._open_view_widgets:
                plugin_name, view_id = self._open_view_widgets.pop(widget)
                logger.info(f"Tab '{tab_name}' ({plugin_name}/{view_id}) closed.")
            widget.deleteLater()

    def close_all_tabs(self, force=False):

        if not self.tab_widget: return
        logger.debug(f"Closing all tabs (force={force})")
        while self.tab_widget.count() > 0: self._handle_tab_close_request(0)
        if self._open_view_widgets:
            logger.warning(f"_open_view_widgets is not empty: {self._open_view_widgets}")
            self._open_view_widgets.clear()
        logger.info("All tabs closed.")

    def load_view_state(self) -> bool:
        """Loads the view state from a file. Returns True if the view was successfully loaded and is not empty."""
        if not self.tab_widget: return False
        state_file = self.app_core.view_state_file
        if not state_file.exists():
            logger.info(f"View state file not found ({state_file}).")
            return False

        logger.info(f"Loading view state from: {state_file}")
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            open_tabs_info = state_data.get("open_tabs", [])
            if not open_tabs_info:
                logger.info("Saved view is empty.")
                return False  # Consider the view not loaded if it is empty

            logger.debug(f"Restoring tabs: {open_tabs_info}")
            self.close_all_tabs(force=True)
            opened_count = 0
            for tab_info in open_tabs_info:
                p_name, v_id = tab_info.get("plugin"), tab_info.get("view_id")
                if p_name and v_id and p_name in self._declared_views and v_id in self._declared_views[p_name]:
                    self.open_view_by_id(p_name, v_id)
                    opened_count += 1
                else:
                    logger.warning(f"Saved '{p_name}/{v_id}' not found.")

            idx = state_data.get("current_index", -1)
            if 0 <= idx < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(idx)
            elif self.tab_widget.count() > 0:
                self.tab_widget.setCurrentIndex(0)

            logger.info(f"View loaded ({opened_count} tabs).")
            return True  # View successfully loaded and is not empty
        except Exception as e:
            msg = f"Error loading or applying view state from {state_file}: {e}"
            logger.error(msg, exc_info=True)
            QMessageBox.warning(self.app_core, "View Loading Error", f"{msg}\nDefault view will be used.")
            self.close_all_tabs(force=True)
            return False  # Failed to load

    @Slot()
    def save_view_state(self):

        state_file = self.app_core.view_state_file
        logger.info(f"Saving view to: {state_file}")
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
                logger.info(f"View saved ({len(open_tabs_info)} tabs).")
                self.ui_manager.update_status("View saved.", 3000)
            except IOError as e:
                msg = f"Error writing view file {state_file}: {e}"
                logger.error(msg,
                             exc_info=True)
                QMessageBox.critical(
                    self.app_core, "View Saving Error", msg)
            except Exception as e:
                msg = f"Unexpected error saving view: {e}"
                logger.error(msg,
                             exc_info=True)
                QMessageBox.critical(
                    self.app_core, "View Saving Error", msg)
        else:
            logger.error("Cannot save view: TabWidget does not exist.")

    @Slot()
    def reset_view_state(self):
        """Resets the view and opens all default tabs."""
        reply = QMessageBox.question(self.app_core, "Reset View",
                                     "Are you sure you want to close all tabs and reset the saved view?\n(All available views will be reopened)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Resetting view...")
            self.close_all_tabs(force=True)
            state_file = self.app_core.view_state_file
            try:
                if state_file.exists():
                    state_file.unlink()
                    logger.info(f"View file deleted: {state_file}")
            except OSError as e:
                msg = f"Failed to delete saved view file {state_file}: {e}"
                logger.error(msg, exc_info=True)
                QMessageBox.warning(self.app_core, "View Reset Error", msg)

            logger.info("Opening default views after reset...")
            self.open_all_declared_views()
            self.ui_manager.update_status("View reset and restored to default.", 3000)
