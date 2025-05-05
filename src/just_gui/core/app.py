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
    The main class of the just-gui application.
    Orchestrates interaction between managers.
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
        self.view_manager._add_menu_actions()
        self.plugin_manager = PluginManager(
            app_core=self, state_manager=self.state_manager, event_bus=self.event_bus
        )

        theme = self.config.get("theme", "light")
        apply_theme(self, theme)
        profile_title = self.profile_metadata.get("title", self.profile_name)
        self.setWindowTitle(f"just-gui: {profile_title}")
        logger.debug(f"AppCore ({self.profile_name}): __init__ complete.")

    async def initialize(self):
        """Asynchronous initialization."""
        logger.info(f"AppCore ({self.profile_name}): Starting async initialization...")
        critical_error = None
        try:
            await self.plugin_manager.load_profile(str(self.profile_path))
        except Exception as e:
            logger.error(f"Critical error loading profile '{self.profile_name}': {e}", exc_info=True)
            critical_error = e

        try:
            self.view_manager.update_view_menu()
            view_loaded = self.view_manager.load_view_state()

            if not view_loaded:
                logger.info("Saved view not found or empty. Opening all available views by default...")
                self.view_manager.open_all_declared_views()

        except Exception as e:
            logger.error(f"Error updating/loading view: {e}", exc_info=True)
            if not critical_error:
                QMessageBox.warning(self, "View Error", f"Failed to update or load view state:\n{e}")

        logger.info(f"AppCore ({self.profile_name}): Async initialization complete.")
        if critical_error:
            QMessageBox.critical(self, "Profile Loading Error",
                                 f"A critical error occurred while loading plugins:\n{critical_error}\n\n"
                                 "Some functionality may be unavailable.")

        if self.view_manager.tab_widget and self.view_manager.tab_widget.count() == 0:
            self.update_status("Plugins loaded, but no views available or failed to open.", 5000)
        elif not critical_error:
            self.update_status("Ready", 3000)

    def _load_app_config(self):
        logger.debug(f"Loading application configuration from {self.profile_path}")
        try:
            if not self.profile_path.is_file():
                logger.warning(f"Profile file not found: {self.profile_path}.")
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
                logger.info(f"'just_gui' logging level: {log_level_str}")
            except AttributeError:
                logger.warning(f"Invalid logging level '{log_level_str}'.")
                logging.getLogger(
                    'just_gui').setLevel(logging.INFO)
        except ConfigError as e:
            logger.warning(f"Config loading error: {e}.")
            self.config = {}
        except Exception as e:
            logger.error(f"Unexpected config loading error: {e}", exc_info=True)
            self.config = {}

    def closeEvent(self, event):
        logger.info(f"AppCore ({self.profile_name}): Received close event.")
        if hasattr(self, 'view_manager') and self.view_manager:
            self.view_manager.save_view_state()
        else:
            logger.warning("ViewManager not found on close.")
        if hasattr(self, 'plugin_manager') and self.plugin_manager:
            try:
                self.plugin_manager.unload_all()
            except Exception as e:
                logger.error(f"Error unloading plugins: {e}", exc_info=True)
        else:
            logger.warning("PluginManager not found on close.")
        event.accept()
        logger.info(f"AppCore ({self.profile_name}): Application is shutting down.")

    def update_status(self, message: str, timeout: int = 0):
        """
        Updates the status bar message.
        """
        if hasattr(self, 'ui_manager') and self.ui_manager:
            self.ui_manager.update_status(message, timeout)

    def declare_view(self, plugin_name: str, view_id: str, name: str, factory: 'ViewFactory'):
        """
        Declares a view provided by a plugin.
        """
        if hasattr(self, 'view_manager') and self.view_manager:
            self.view_manager.declare_view(plugin_name, view_id, name, factory)
        else:
            logger.error("ViewManager is not initialized.")

    def register_menu_action(self, plugin_name: str, menu_path: str, action: 'QAction'):
        """
        Registers a QAction under a specific menu path.
        """
        if hasattr(self, 'ui_manager') and self.ui_manager:
            self.ui_manager.register_menu_action(plugin_name, menu_path, action)
        else:
            logger.error("UIManager is not initialized.")

    def register_toolbar_widget(self, section_path: str, widget: 'QWidget'):
        """
        Registers a QWidget in a specific toolbar section.
        """
        if hasattr(self, 'ui_manager') and self.ui_manager:
            self.ui_manager.register_toolbar_widget(section_path, widget)
        else:
            logger.error("UIManager is not initialized.")

    @property
    def view_state_file(self) -> Path:
        """
        Provides the path to the file where the view state for the current profile is saved.
        """
        config_dir = Path(platformdirs.user_config_dir(self.APP_NAME, self.APP_AUTHOR))
        profile_view_dir = config_dir / "profiles" / self.profile_name
        profile_view_dir.mkdir(parents=True, exist_ok=True)
        return profile_view_dir / "view_state.json"