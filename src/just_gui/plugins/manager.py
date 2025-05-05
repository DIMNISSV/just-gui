# src/just_gui/plugins/manager.py
import importlib
import logging
import sys
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Tuple
from importlib.metadata import version as get_version, PackageNotFoundError

from ..utils.config_loader import load_toml, ConfigError
from .base import BasePlugin, PluginContext
from .validator import validate_plugin_ast, PluginValidationError
from ..security.sandbox import Sandbox

if TYPE_CHECKING:
    from ..state.manager import StateManager
    from ..events.bus import EventBus
    from ..core.app import AppCore

logger = logging.getLogger(__name__)


class PluginLoadError(Exception): pass


class PluginManager:
    def __init__(self, app_core: 'AppCore', state_manager: 'StateManager', event_bus: 'EventBus'):
        self._app_core = app_core
        self._state_manager = state_manager
        self._event_bus = event_bus
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_configs: Dict[str, Dict[str, Any]] = {}
        self._dependency_versions: Dict[str, str] = {}

    @property
    def loaded_plugins(self) -> Dict[str, BasePlugin]:
        return self._plugins.copy()

    async def load_profile(self, profile_path: str):
        logger.info(f"Loading profile: {profile_path}")
        profile_p = Path(profile_path)
        try:
            profile_data = load_toml(profile_p)
        except (FileNotFoundError, ConfigError) as e:
            logger.error(f"Failed to load profile: {e}", exc_info=True)
            return

        self._plugin_configs = profile_data.get("plugin_configs", {})
        plugins_section = profile_data.get("plugins", {})
        self._dependency_versions = plugins_section.get("dependencies", {})

        plugin_load_queue: List[Tuple[str, Path, Dict]] = []
        plugin_metadata_map: Dict[str, Dict] = {}
        profile_dir = profile_p.parent

        for local_path_str in plugins_section.get("local", []):
            local_path = Path(local_path_str)
            if not local_path.is_absolute(): local_path = (profile_dir / local_path).resolve()
            if local_path.is_dir():
                logger.info(f"Discovered local plugin: {local_path}")
                try:
                    meta = self._read_plugin_metadata(local_path)
                    if meta:
                        plugin_name = meta['name']
                        if plugin_name not in plugin_metadata_map:
                            plugin_metadata_map[plugin_name] = meta
                            plugin_load_queue.append((plugin_name, local_path, meta))
                        else:
                            logger.warning(f"Duplicate plugin '{plugin_name}' found at {local_path}.")
                except (PluginLoadError, ConfigError) as e:
                    logger.error(f"Metadata error at {local_path}: {e}")
            else:
                logger.warning(f"Not a directory: {local_path}")

        # TODO: Load from Git

        # TODO: Topological sort
        logger.debug(f"Load order: {[name for name, _, _ in plugin_load_queue]}")
        sorted_load_order = plugin_load_queue

        for plugin_name, plugin_path, plugin_meta in sorted_load_order:
            try:
                self._load_from_dir(plugin_path, plugin_meta)
            except (PluginLoadError, PluginValidationError, ConfigError, ImportError) as e:
                logger.error(f"Error loading '{plugin_name}': {e}", exc_info=False)

        logger.info(f"Profile loading finished. Plugins loaded: {len(self._plugins)}")

    def _read_plugin_metadata(self, plugin_dir: Path) -> Optional[Dict]:
        """Reads and validates metadata from plugin.toml, including new fields."""
        plugin_toml_path = plugin_dir / "plugin.toml"
        if not plugin_toml_path.is_file():
            raise PluginLoadError(f"'plugin.toml' not found in: {plugin_dir}")

        plugin_data = load_toml(plugin_toml_path)
        plugin_meta = plugin_data.get("metadata", {})
        plugin_name = plugin_meta.get("name")
        entry_point_str = plugin_meta.get("entry_point")

        if not plugin_name or not entry_point_str:
            raise PluginLoadError(f"'name' or 'entry_point' missing in [metadata] ({plugin_dir})")

        plugin_meta["version"] = plugin_meta.get("version", "0.0.0")
        plugin_meta["title"] = plugin_meta.get("title")
        plugin_meta["author"] = plugin_meta.get("author")
        plugin_meta["description"] = plugin_meta.get("description")

        plugin_meta["dependencies"] = plugin_data.get("dependencies", {})
        plugin_meta["permissions"] = plugin_data.get("permissions", {})

        return plugin_meta

    def _load_from_dir(self, plugin_dir: Path, plugin_meta: Dict):
        """Loads a plugin from a directory using metadata."""
        plugin_name = plugin_meta['name']
        version = plugin_meta['version']
        entry_point_str = plugin_meta['entry_point']
        dependencies = plugin_meta['dependencies']
        permissions = plugin_meta['permissions']
        plugin_title = plugin_meta.get('title')
        plugin_author = plugin_meta.get('author')
        plugin_description = plugin_meta.get('description')

        if plugin_name in self._plugins: logger.warning(f"Plugin '{plugin_name}' is already loaded."); return
        display_name = plugin_title if plugin_title else plugin_name
        logger.info(f"Loading plugin '{display_name}' v{version} from {plugin_dir}...")

        try:
            self._check_dependencies(plugin_name, dependencies)
        except PluginLoadError as e:
            logger.error(f"Dependency error for '{plugin_name}': {e}")
            raise

        try:
            module_path_str, class_name = entry_point_str.split(":")
        except ValueError:
            raise PluginLoadError(f"Invalid entry_point format '{entry_point_str}' for '{plugin_name}'")

        entry_point_file = plugin_dir / module_path_str.replace(".", "/")
        if not entry_point_file.suffix: entry_point_file = entry_point_file.with_suffix(".py")
        if not entry_point_file.is_file(): raise PluginLoadError(
            f"Entry point file '{entry_point_file}' not found for '{plugin_name}'")

        try:
            with open(entry_point_file, 'r', encoding='utf-8') as f:
                plugin_code = f.read()
            logger.warning(f"[STUB] AST validation for '{plugin_name}' skipped.")
            # if not validate_plugin_ast(plugin_code): raise PluginValidationError(...)
        except SyntaxError as e:
            raise PluginLoadError(f"Syntax error in '{plugin_name}': {e}") from e
        except IOError as e:
            raise PluginLoadError(f"Error reading '{entry_point_file}': {e}") from e

        plugin_dir_str = str(plugin_dir.resolve())
        added_to_path = False
        if plugin_dir_str not in sys.path: sys.path.insert(0, plugin_dir_str); added_to_path = True

        try:
            module_name = module_path_str
            logger.debug(f"Importing module '{module_name}' for '{plugin_name}'")
            if module_name in sys.modules: logger.debug(f"Reloading module '{module_name}'"); del sys.modules[
                module_name]
            plugin_module = importlib.import_module(module_name)

            plugin_class: Type[BasePlugin] = getattr(plugin_module, class_name)
            if not issubclass(plugin_class, BasePlugin): raise PluginLoadError(
                f"'{class_name}' does not inherit from BasePlugin")

            plugin_specific_config = self._plugin_configs.get(plugin_name, {})
            context = PluginContext(
                plugin_name=plugin_name,
                plugin_version=version,
                plugin_title=plugin_title,
                plugin_author=plugin_author,
                plugin_description=plugin_description,
                plugin_config=plugin_specific_config,
                plugin_permissions=permissions,
                state_manager=self._state_manager,
                event_bus=self._event_bus,
                app_core=self._app_core
            )

            logger.warning(f"[STUB] Initializing '{plugin_name}' OUTSIDE sandbox.")
            # with Sandbox(plugin_name):
            plugin_instance = plugin_class(context)

            try:
                plugin_instance.on_load()
            except Exception as load_exc:
                raise PluginLoadError(f"Error in on_load() for '{plugin_name}'") from load_exc

            self._plugins[plugin_name] = plugin_instance
            logger.info(f"Plugin '{display_name}' v{version} successfully loaded.")

        except (AttributeError, ImportError, TypeError) as e:
            raise PluginLoadError(f"Import/instantiation error for '{plugin_name}': {e}") from e
        except Exception as e:
            if not isinstance(e, (PluginLoadError, PluginValidationError)):
                raise PluginLoadError(f"Loading error for '{plugin_name}': {e}") from e
            else:
                raise
        finally:
            if added_to_path and plugin_dir_str in sys.path:
                try:
                    sys.path.remove(plugin_dir_str)
                except ValueError:
                    pass

    def _check_dependencies(self, plugin_name: str, dependencies: Dict[str, str]):
        if not dependencies: return
        logger.debug(f"Checking dependencies for '{plugin_name}': {dependencies}")
        for dep_name, req_version_spec in dependencies.items():
            target_req_spec = self._dependency_versions.get(dep_name, req_version_spec)
            if target_req_spec != req_version_spec: logger.warning(
                f"'{plugin_name}': Profile is overriding version for '{dep_name}' to '{target_req_spec}'.")
            try:
                installed_version_str = get_version(dep_name)
                logger.debug(f"Found dependency: {dep_name} v{installed_version_str}")
                logger.warning(
                    f"[STUB] Version compatibility check for '{dep_name}' (required: '{target_req_spec}') NOT IMPLEMENTED.")
                # if not check_semver(installed_version_str, target_req_spec): raise PluginLoadError(...)
            except PackageNotFoundError:
                raise PluginLoadError(f"Missing dependency '{dep_name}' (required: {target_req_spec})")
            except Exception as e:
                raise PluginLoadError(f"Error checking '{dep_name}'") from e

    def unload_all(self):
        logger.info("Unloading all plugins...")
        plugin_names = list(self._plugins.keys())
        for name in reversed(plugin_names):
            if name in self._plugins:
                plugin = self._plugins.pop(name)
                display_name = plugin.title
                try:
                    logger.debug(f"Calling on_unload() for '{display_name}'")
                    # with Sandbox(name):
                    plugin.on_unload()
                except Exception as e:
                    logger.error(f"Error unloading '{display_name}': {e}", exc_info=True)
        logger.info("All plugins unloaded.")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)
