# src/just_gui/core/ui_manager.py
import logging
from typing import Dict, Optional, TYPE_CHECKING, cast
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QToolBar, QStatusBar,
    QMenuBar, QMessageBox, QMenu
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QSize

from typing import cast

if TYPE_CHECKING:
    from .app import AppCore

logger = logging.getLogger(__name__)


class UIManager:
    """Manages core UI elements, menus, and toolbars."""

    def __init__(self, main_window: QMainWindow):
        self.main_window = main_window
        self.menu_bar: Optional[QMenuBar] = None
        self.tool_bar: Optional[QToolBar] = None
        self.tab_widget: Optional[QTabWidget] = None
        self.status_bar: Optional[QStatusBar] = None
        self._all_menus_cache: Dict[str, QMenu] = {}
        self._toolbars: Dict[str, QToolBar] = {}
        self._view_menu: Optional[QMenu] = None

    def initialize_ui(self):
        """Initializes the main UI elements of the main window."""
        logger.debug("UIManager: Initializing UI...")
        if not isinstance(self.main_window, QMainWindow):
            logger.error("UIManager expects a QMainWindow!")
            return

        self.menu_bar = self.main_window.menuBar()
        if not self.menu_bar:
            logger.error("Failed to get QMenuBar!")
            return

        self.tool_bar = QToolBar("Main Toolbar", self.main_window)
        self.tool_bar.setIconSize(QSize(24, 24))
        self.main_window.addToolBar(self.tool_bar)
        self._toolbars["Main Toolbar"] = self.tool_bar

        self.tab_widget = QTabWidget(self.main_window)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.main_window.setCentralWidget(self.tab_widget)

        self.status_bar = QStatusBar(self.main_window)
        self.main_window.setStatusBar(self.status_bar)
        self.update_status("Initializing...", 0)

        self._setup_default_menus()
        logger.debug("UIManager: UI initialized.")

    def _setup_default_menus(self):
        """Creates basic menu items and caches them."""
        assert self.menu_bar is not None

        file_menu = self.menu_bar.addMenu("&File")
        self._all_menus_cache["Файл"] = file_menu
        exit_icon = QIcon.fromTheme("application-exit")
        exit_action = QAction(exit_icon, "&Exit", self.main_window)
        exit_action.triggered.connect(self.main_window.close)
        file_menu.addAction(exit_action)  # Add Exit to the end

        self._view_menu = self.menu_bar.addMenu("&View")
        self._all_menus_cache["Вид"] = self._view_menu

        tools_menu = self.menu_bar.addMenu("&Tools")
        self._all_menus_cache["Инструменты"] = tools_menu

        help_menu = self.menu_bar.addMenu("&Help")
        self._all_menus_cache["Помощь"] = help_menu
        about_icon = QIcon.fromTheme("help-about")
        about_action = QAction(about_icon, "&About", self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def get_view_menu(self) -> Optional[QMenu]:
        """Returns a reference to the 'View' menu."""
        return self._view_menu

    def find_or_create_menu(self, menu_path: str) -> Optional[QMenu]:
        """Finds or creates a menu/submenu."""
        full_path = menu_path.strip('/')
        if not full_path:
            logger.error("Empty menu path.")
            return None

        if full_path in self._all_menus_cache:
            cached_menu = self._all_menus_cache[full_path]
            try:
                _ = cached_menu.title()
                logger.debug(f"Cache hit: '{full_path}'")
                return cached_menu
            except RuntimeError:
                logger.warning(f"Cache '{full_path}' removed.")
                del self._all_menus_cache[full_path]

        parts = full_path.split('/')
        current_menu_obj: Optional[QMenu] = None
        current_path_part = ""
        root_name = parts[0]
        current_path_part = root_name
        if current_path_part in self._all_menus_cache:
            cached_root = self._all_menus_cache[current_path_part]
            try:
                _ = cached_root.title()
                current_menu_obj = cached_root
            except RuntimeError:
                del self._all_menus_cache[current_path_part]
                current_menu_obj = None

        if current_menu_obj is None:
            if not self.menu_bar:
                logger.error("MenuBar not initialized.")
                return None
            found_root = None
            for action in self.menu_bar.actions():
                menu = action.menu()
                if menu and menu.title().replace('&', '') == root_name:
                    found_root = menu
                    break
            if found_root:
                current_menu_obj = found_root
            else:
                menu_text = f"&{root_name}" if '&' not in root_name else root_name
                current_menu_obj = self.menu_bar.addMenu(menu_text)
            if current_menu_obj:
                self._all_menus_cache[current_path_part] = current_menu_obj
            else:
                logger.error(f"Failed to create root menu '{root_name}'")
                return None

        for i in range(1, len(parts)):
            part_name = parts[i]
            current_path_part += f"/{part_name}"
            next_menu_obj: Optional[QMenu] = None
            if current_path_part in self._all_menus_cache:
                cached_submenu = self._all_menus_cache[current_path_part]
                try:
                    _ = cached_submenu.title()
                    next_menu_obj = cached_submenu
                except RuntimeError:
                    del self._all_menus_cache[current_path_part]
                    next_menu_obj = None
            if next_menu_obj is None:
                found_submenu = None
                for action in current_menu_obj.actions():
                    submenu = action.menu()
                    if submenu and submenu.title().replace('&', '') == part_name:
                        try:
                            _ = submenu.title()
                            found_submenu = submenu
                            break
                        except RuntimeError:
                            logger.warning(f"Removed submenu '{part_name}'.")
                            current_menu_obj.removeAction(action)
                            action.deleteLater()
                if found_submenu:
                    next_menu_obj = found_submenu
                else:
                    menu_text = f"&{part_name}" if '&' not in part_name else part_name
                    next_menu_obj = current_menu_obj.addMenu(menu_text)
                if next_menu_obj:
                    self._all_menus_cache[current_path_part] = next_menu_obj
                else:
                    logger.error(f"Failed to create submenu '{part_name}'")
                    return None
            current_menu_obj = next_menu_obj
        return current_menu_obj

    # --- API for plugins ---
    def register_menu_action(self, plugin_name: str, menu_path: str, action: QAction):
        target_menu = self.find_or_create_menu(menu_path)
        if target_menu:
            action_text = action.text().replace('&', '')
            logger.debug(
                f"Adding action '{action_text}' to menu '{target_menu.title().replace('&', '')}' (plugin: {plugin_name})")
            for existing_action in target_menu.actions():
                if existing_action.text() == action.text():
                    logger.warning(
                        f"Action '{action_text}' already exists in menu '{target_menu.title().replace('&', '')}'. Skipping.")
                    return
            target_menu.addAction(action)
        else:
            logger.error(f"Plugin '{plugin_name}': Failed to find/create menu '{menu_path}' for action.")

    def register_toolbar_widget(self, section_path: str, widget: QWidget):
        target_toolbar = self.tool_bar
        if not target_toolbar:
            logger.error("Toolbar not initialized.")
            return
        widget_text = getattr(widget, 'text', type(widget).__name__)
        widget_text = widget_text().replace('&', '') if callable(widget_text) else str(widget_text).replace('&', '')
        logger.debug(f"Adding widget '{widget_text}' to toolbar (section '{section_path}')")
        if isinstance(widget, QAction):
            target_toolbar.addAction(widget)
        else:
            target_toolbar.addWidget(widget)

    def update_status(self, message: str, timeout: int = 0):
        if self.status_bar:
            if timeout > 0:
                self.status_bar.showMessage(message, timeout)
            else:
                self.status_bar.showMessage(message)
        else:
            logger.warning("StatusBar not initialized.")

    def show_about_dialog(self):
        """Shows the 'About' dialog with profile and plugin information."""
        try:
            app_core = cast('AppCore', self.main_window)
            profile_meta = app_core.profile_metadata
            # --- CHANGED: Use title and author from profile metadata ---
            profile_title = profile_meta.get("title", app_core.profile_name)  # Fallback to file name
            profile_author = profile_meta.get("author", app_core.APP_AUTHOR)  # Fallback to constant
            profile_version = profile_meta.get("version", "N/A")
            # --- END CHANGE ---

            plugin_manager: Optional['PluginManager'] = getattr(app_core, 'plugin_manager', None)
            loaded_plugins = plugin_manager.loaded_plugins if plugin_manager else {}
            from .. import __version__ as lib_version
        except (ImportError, AttributeError, NameError) as e:
            logger.error(f"Error getting data for 'About': {e}")
            lib_version = "N/A";
            profile_title = "N/A";
            profile_author = "Unknown";
            profile_version = "N/A";
            loaded_plugins = {}

        about_text_lines = [
            f"<b>just-gui Library</b>",
            f"Version: {lib_version}",
            f"(c) 2025",
            "<hr>",
            f"<b>Profile: {profile_title}</b>",
            f"Version: {profile_version}",
            f"Author: {profile_author}",
            f"<br>",
            f"<b>Loaded Plugins ({len(loaded_plugins)}):</b>"
        ]

        if loaded_plugins:
            plugin_list_lines = []
            sorted_plugins = sorted(loaded_plugins.values(), key=lambda p: p.title.lower())
            for plugin in sorted_plugins:
                author_info = f" (Author: {plugin.author})" if plugin.author else ""
                plugin_list_lines.append(f"<li><b>{plugin.title}</b> (v{plugin.version}){author_info}</li>")
            about_text_lines.append(f"<ul>{''.join(plugin_list_lines)}</ul>")
        else:
            about_text_lines.append("No plugins loaded.")

        full_about_text = "<br>".join(about_text_lines)
        QMessageBox.about(self.main_window, f"About: {profile_title}", full_about_text)
