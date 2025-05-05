# src/just_gui/plugins/base.py
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Callable

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from ..state.manager import StateManager
    from ..events.bus import EventBus
    from ..core.app import AppCore

logger = logging.getLogger(__name__)

ViewFactory = Callable[[], QWidget]


@dataclass
class PluginContext:
    """Context passed to the plugin upon initialization."""
    plugin_name: str
    plugin_version: str
    plugin_config: Dict[str, Any]
    state_manager: 'StateManager'
    event_bus: 'EventBus'
    app_core: 'AppCore'
    plugin_permissions: Dict[str, Any] = field(default_factory=dict)
    plugin_title: Optional[str] = None
    plugin_author: Optional[str] = None
    plugin_description: Optional[str] = None

    def get_config(self, key: str, default: Any = None) -> Any:
        """Convenience method for getting plugin configuration."""
        keys = key.split('.')
        value = self.plugin_config
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value[k]
                else:
                    logger.debug(
                        f"Key '{k}' not found or is not a dictionary in plugin '{self.plugin_name}' configuration when searching for '{key}'")
                    return default
            return value
        except KeyError:
            logger.debug(
                f"Key '{keys[-1]}' not found in plugin '{self.plugin_name}' configuration when searching for '{key}'")
            return default
        except Exception as e:
            logger.warning(
                f"Unexpected error getting configuration '{key}' for plugin '{self.plugin_name}': {e}")
            return default

    def has_permission(self, *permission_parts: str) -> bool:
        """
        Checks if the plugin has the specified permission.
        CURRENTLY A STUB. Will check self.plugin_permissions in the future.
        Example: context.has_permission("filesystem", "read", "/data/images")
        """
        permission_key = ".".join(permission_parts)
        logger.warning(
            f"[SECURITY STUB] Permission check '{permission_key}' for plugin '{self.plugin_name}' always returns True.")

        return True

    # TODO: Add a method for accessing plugin resources (get_resource)


class BasePlugin(ABC):
    """Abstract base class for all plugins."""

    def __init__(self, context: PluginContext):
        self.context = context
        self.name = context.plugin_name
        self.version = context.plugin_version
        self._state = context.state_manager
        self._bus = context.event_bus
        self._app = context.app_core
        self._config = context.plugin_config
        self._permissions = context.plugin_permissions
        self.title = context.plugin_title if context.plugin_title else self.name
        self.author = context.plugin_author
        self.description = context.plugin_description

        logger.info(f"Plugin initialized: {self.name} v{self.version}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Gets a plugin configuration parameter."""
        return self.context.get_config(key, default)

    def has_permission(self, *permission_parts: str) -> bool:
        """Checks if the plugin has the requested permission."""
        return self.context.has_permission(*permission_parts)

    # --- Lifecycle Methods ---
    @abstractmethod
    def on_load(self):
        """
        Called after the plugin is successfully loaded.
        Initialization, event subscription, view declaration,
        and menu/toolbar action registration should be done here.
        """
        logger.debug(f"Plugin '{self.name}': on_load() called")
        pass

    def on_unload(self):
        """
        Called before the plugin is unloaded.
        Resource cleanup and event unsubscription should be done here.
        View widgets will be removed by AppCore.
        """
        logger.debug(f"Plugin '{self.name}': on_unload() called")
        pass

    def declare_view(self, view_id: str, name: str, factory: ViewFactory):
        """
        Declares a view (widget) that can be opened by the user
        (e.g., as a tab or a dock widget).

        Args:
            view_id: A unique identifier for the view within the plugin (e.g., "main_editor").
            name: The name displayed to the user (e.g., "Editor").
            factory: A function (no arguments) that creates and returns
                     a new QWidget instance for this view.
        """
        logger.debug(f"Plugin '{self.name}': Declaring view view_id='{view_id}', name='{name}'")
        self._app.declare_view(self.name, view_id, name, factory)

    def register_menu_action(self, menu_path: str, action):
        """Registers a plugin action in the main menu."""
        logger.debug(f"Plugin '{self.name}': Registering menu action '{menu_path}'")
        if not hasattr(action, 'triggered'):
            logger.error(
                f"Plugin '{self.name}': Attempting to register non-QAction in menu '{menu_path}'. Type: {type(action)}")
            return
        self._app.register_menu_action(self.name, menu_path, action)

    def register_toolbar_widget(self, widget, section: Optional[str] = None):
        """Registers a widget on the toolbar."""
        section_name = section or "Default"
        logger.debug(f"Plugin '{self.name}': Registering toolbar widget in section '{section_name}'")
        full_section = f"{self.name}/{section_name}"
        self._app.register_toolbar_widget(full_section, widget)

    def update_status(self, message: str, timeout: int = 0):
        """Updates the message in the status bar."""
        self._app.update_status(f"[{self.name}] {message}", timeout)
