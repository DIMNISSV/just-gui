# src/just_gui/plugins/manager.py
import importlib
import logging
import sys
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Tuple
from importlib.metadata import version as get_version, PackageNotFoundError

from ..utils.config_loader import load_toml, ConfigError
# Обновленный импорт PluginContext и BasePlugin
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
        logger.info(f"Загрузка профиля: {profile_path}")
        profile_p = Path(profile_path)
        try:
            profile_data = load_toml(profile_p)
        except (FileNotFoundError, ConfigError) as e:
            logger.error(f"Не удалось загрузить профиль: {e}", exc_info=True);
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
                logger.info(f"Обнаружен локальный плагин: {local_path}")
                try:
                    meta = self._read_plugin_metadata(local_path)
                    if meta:
                        plugin_name = meta['name']
                        if plugin_name not in plugin_metadata_map:
                            plugin_metadata_map[plugin_name] = meta
                            plugin_load_queue.append((plugin_name, local_path, meta))
                        else:
                            logger.warning(f"Дубликат плагина '{plugin_name}' в {local_path}.")
                except (PluginLoadError, ConfigError) as e:
                    logger.error(f"Ошибка метаданных {local_path}: {e}")
            else:
                logger.warning(f"Не директория: {local_path}")

        # TODO: Загрузка из Git

        # TODO: Топологическая сортировка
        logger.debug(f"Порядок загрузки: {[name for name, _, _ in plugin_load_queue]}")
        sorted_load_order = plugin_load_queue

        for plugin_name, plugin_path, plugin_meta in sorted_load_order:
            try:
                self._load_from_dir(plugin_path, plugin_meta)
            except (PluginLoadError, PluginValidationError, ConfigError, ImportError) as e:
                logger.error(f"Ошибка загрузки '{plugin_name}': {e}", exc_info=False)  # Меньше шума в логах

        logger.info(f"Загрузка профиля завершена. Плагинов загружено: {len(self._plugins)}")

    def _read_plugin_metadata(self, plugin_dir: Path) -> Optional[Dict]:
        """Читает и валидирует метаданные из plugin.toml, включая новые поля."""
        plugin_toml_path = plugin_dir / "plugin.toml"
        if not plugin_toml_path.is_file():
            raise PluginLoadError(f"'plugin.toml' не найден в: {plugin_dir}")

        plugin_data = load_toml(plugin_toml_path)
        plugin_meta = plugin_data.get("metadata", {})
        plugin_name = plugin_meta.get("name")
        entry_point_str = plugin_meta.get("entry_point")

        if not plugin_name or not entry_point_str:
            raise PluginLoadError(f"'name' или 'entry_point' отсутствуют в [metadata] ({plugin_dir})")

        # --- ИЗМЕНЕНО: Читаем новые поля ---
        plugin_meta["version"] = plugin_meta.get("version", "0.0.0")
        plugin_meta["title"] = plugin_meta.get("title")  # Будет None если нет
        plugin_meta["author"] = plugin_meta.get("author")  # Будет None если нет
        plugin_meta["description"] = plugin_meta.get("description")  # Будет None если нет
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        plugin_meta["dependencies"] = plugin_data.get("dependencies", {})
        plugin_meta["permissions"] = plugin_data.get("permissions", {})

        return plugin_meta

    def _load_from_dir(self, plugin_dir: Path, plugin_meta: Dict):
        """Загружает плагин из директории, используя метаданные."""
        plugin_name = plugin_meta['name']
        version = plugin_meta['version']
        entry_point_str = plugin_meta['entry_point']
        dependencies = plugin_meta['dependencies']
        permissions = plugin_meta['permissions']
        # --- ИЗМЕНЕНО: Получаем доп. метаданные ---
        plugin_title = plugin_meta.get('title')
        plugin_author = plugin_meta.get('author')
        plugin_description = plugin_meta.get('description')
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        if plugin_name in self._plugins: logger.warning(f"Плагин '{plugin_name}' уже загружен."); return
        # Используем title в логах, если есть, иначе name
        display_name = plugin_title if plugin_title else plugin_name
        logger.info(f"Загрузка плагина '{display_name}' v{version} из {plugin_dir}...")

        try:
            self._check_dependencies(plugin_name, dependencies)
        except PluginLoadError as e:
            logger.error(f"Ошибка зависимостей '{plugin_name}': {e}"); raise

        try:
            module_path_str, class_name = entry_point_str.split(":")
        except ValueError:
            raise PluginLoadError(f"Некорректный entry_point '{entry_point_str}' для '{plugin_name}'")

        entry_point_file = plugin_dir / module_path_str.replace(".", "/")
        if not entry_point_file.suffix: entry_point_file = entry_point_file.with_suffix(".py")
        if not entry_point_file.is_file(): raise PluginLoadError(
            f"Файл точки входа '{entry_point_file}' не найден для '{plugin_name}'")

        try:
            with open(entry_point_file, 'r', encoding='utf-8') as f:
                plugin_code = f.read()
            # --- ЗАГЛУШКА БЕЗОПАСНОСТИ ---
            logger.warning(f"[STUB] AST валидация для '{plugin_name}' пропущена.")
            # if not validate_plugin_ast(plugin_code): raise PluginValidationError(...)
        except SyntaxError as e:
            raise PluginLoadError(f"Синтаксическая ошибка '{plugin_name}': {e}") from e
        except IOError as e:
            raise PluginLoadError(f"Ошибка чтения '{entry_point_file}': {e}") from e

        plugin_dir_str = str(plugin_dir.resolve());
        added_to_path = False
        if plugin_dir_str not in sys.path: sys.path.insert(0, plugin_dir_str); added_to_path = True

        try:
            module_name = module_path_str
            logger.debug(f"Импорт модуля '{module_name}' для '{plugin_name}'")
            if module_name in sys.modules: logger.debug(f"Перезагрузка модуля '{module_name}'"); del sys.modules[
                module_name]
            plugin_module = importlib.import_module(module_name)

            plugin_class: Type[BasePlugin] = getattr(plugin_module, class_name)
            if not issubclass(plugin_class, BasePlugin): raise PluginLoadError(
                f"'{class_name}' не наследует BasePlugin")

            # --- ИЗМЕНЕНО: Передаем расширенные метаданные в контекст ---
            plugin_specific_config = self._plugin_configs.get(plugin_name, {})
            context = PluginContext(
                plugin_name=plugin_name,
                plugin_version=version,
                plugin_title=plugin_title,  # Новое
                plugin_author=plugin_author,  # Новое
                plugin_description=plugin_description,  # Новое
                plugin_config=plugin_specific_config,
                plugin_permissions=permissions,
                state_manager=self._state_manager,
                event_bus=self._event_bus,
                app_core=self._app_core
            )
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

            # --- ЗАГЛУШКА БЕЗОПАСНОСТИ ---
            logger.warning(f"[STUB] Инициализация '{plugin_name}' ВНЕ песочницы.")
            # with Sandbox(plugin_name):
            plugin_instance = plugin_class(context)  # Инициализация с новым контекстом

            try:
                plugin_instance.on_load()
            except Exception as load_exc:
                raise PluginLoadError(f"Ошибка в on_load() '{plugin_name}'") from load_exc

            self._plugins[plugin_name] = plugin_instance
            logger.info(f"Плагин '{display_name}' v{version} успешно загружен.")

        except (AttributeError, ImportError, TypeError) as e:
            raise PluginLoadError(f"Ошибка импорта/инстанцирования '{plugin_name}': {e}") from e
        except Exception as e:
            if not isinstance(e, (PluginLoadError, PluginValidationError)):
                raise PluginLoadError(f"Ошибка загрузки '{plugin_name}': {e}") from e
            else:
                raise  # Перевыбрасываем ожидаемые ошибки
        finally:
            if added_to_path and plugin_dir_str in sys.path:
                try:
                    sys.path.remove(plugin_dir_str)
                except ValueError:
                    pass

    def _check_dependencies(self, plugin_name: str, dependencies: Dict[str, str]):
        if not dependencies: return
        logger.debug(f"Проверка зависимостей для '{plugin_name}': {dependencies}")
        for dep_name, req_version_spec in dependencies.items():
            target_req_spec = self._dependency_versions.get(dep_name, req_version_spec)
            if target_req_spec != req_version_spec: logger.warning(
                f"'{plugin_name}': Для '{dep_name}' используется версия '{target_req_spec}' из профиля.")
            try:
                installed_version_str = get_version(dep_name)
                logger.debug(f"Найдена зависимость: {dep_name} v{installed_version_str}")
                # --- ЗАГЛУШКА: Проверка SemVer ---
                logger.warning(
                    f"[STUB] Проверка совместимости версий для '{dep_name}' (требуется: '{target_req_spec}') НЕ РЕАЛИЗОВАНА.")
                # if not check_semver(installed_version_str, target_req_spec): raise PluginLoadError(...)
            except PackageNotFoundError:
                raise PluginLoadError(f"Отсутствует зависимость '{dep_name}' (требуется: {target_req_spec})")
            except Exception as e:
                raise PluginLoadError(f"Ошибка проверки '{dep_name}'") from e

    def unload_all(self):
        logger.info("Выгрузка всех плагинов...")
        plugin_names = list(self._plugins.keys())
        for name in reversed(plugin_names):
            if name in self._plugins:
                plugin = self._plugins.pop(name)
                display_name = plugin.title  # Используем title для лога
                try:
                    logger.debug(f"Вызов on_unload() для '{display_name}'")
                    # --- ЗАГЛУШКА БЕЗОПАСНОСТИ ---
                    # with Sandbox(name):
                    plugin.on_unload()
                except Exception as e:
                    logger.error(f"Ошибка выгрузки '{display_name}': {e}", exc_info=True)
        logger.info("Все плагины выгружены.")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)
