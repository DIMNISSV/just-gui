# src/just_gui/plugins/manager.py
import importlib
import logging
import sys
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Tuple
from importlib.metadata import version as get_version, PackageNotFoundError

from ..core.i18n import unload_plugin_translation, load_plugin_translation
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
        """
        Загружает профиль приложения, плагины и их переводы.
        """
        logger.info(f"Загрузка профиля приложения из: {profile_path}")
        profile_p = Path(profile_path)
        try:
            profile_data = load_toml(profile_p)
        except (FileNotFoundError, ConfigError) as e:
            logger.error(f"Не удалось загрузить профиль: {e}", exc_info=True)
            # В реальном приложении здесь может быть показано сообщение пользователю
            return  # Прекращаем загрузку, если профиль невалиден

        # 1. Чтение конфигурации из профиля
        self._plugin_configs = profile_data.get("plugin_configs", {})
        plugins_section = profile_data.get("plugins", {})
        self._dependency_versions = plugins_section.get("dependencies", {})
        profile_dir = profile_p.parent

        # 2. Сбор информации о плагинах (локальные, git и т.д.)
        plugin_load_queue: List[Tuple[str, Path, Dict]] = []  # (name, path, metadata)
        plugin_metadata_map: Dict[str, Dict] = {}  # name -> metadata

        # Обработка локальных плагинов
        for local_path_str in plugins_section.get("local", []):
            local_path = Path(local_path_str)
            if not local_path.is_absolute():
                local_path = (profile_dir / local_path).resolve()

            if local_path.is_dir():
                logger.info(f"Обнаружен локальный плагин в директории: {local_path}")
                try:
                    meta = self._read_plugin_metadata(local_path)
                    if meta:
                        plugin_name = meta['name']
                        if plugin_name not in plugin_metadata_map:
                            plugin_metadata_map[plugin_name] = meta
                            plugin_load_queue.append((plugin_name, local_path, meta))
                            logger.debug(f"Добавлен в очередь на загрузку: {plugin_name}")
                        else:
                            logger.warning(
                                f"Обнаружен дубликат плагина '{plugin_name}' в {local_path}. Используется первый найденный.")
                except (PluginLoadError, ConfigError) as e:
                    logger.error(f"Ошибка чтения метаданных плагина из {local_path}: {e}")
            else:
                logger.warning(
                    f"Указанный путь к локальному плагину не найден или не является директорией: {local_path}")

        # TODO: Обработка плагинов из Git (асинхронное клонирование и чтение меты)
        git_plugins = plugins_section.get("git", [])
        if git_plugins:
            logger.warning("[PLUGIN MANAGER] Загрузка плагинов из Git пока не реализована.")
            # Здесь будет логика асинхронной загрузки и добавления в plugin_load_queue

        # 3. Топологическая сортировка плагинов (ЗАГЛУШКА)
        # На основе поля [dependencies] в метаданных (plugin_metadata_map)
        # TODO: Реализовать сортировку
        logger.debug(f"Порядок загрузки плагинов (без сортировки): {[name for name, _, _ in plugin_load_queue]}")
        sorted_load_order = plugin_load_queue  # Пока используем исходный порядок

        # 4. Получение текущего языка для загрузки переводов
        current_language = getattr(self._app_core, 'current_language', 'en')  # Fallback на 'en'
        logger.debug(f"Текущий язык для загрузки переводов плагинов: {current_language}")

        # 5. Последовательная загрузка и инициализация плагинов
        loaded_count = 0
        for plugin_name, plugin_path, plugin_meta in sorted_load_order:
            logger.debug(f"Начало обработки плагина '{plugin_name}' из {plugin_path}")
            try:
                # Загрузка перевода ДО загрузки самого кода плагина
                translation_loaded = load_plugin_translation(plugin_name, plugin_path, current_language)
                if translation_loaded:
                    logger.debug(f"Перевод для '{plugin_name}' ({current_language}) загружен.")

                # Загрузка и инициализация кода плагина
                self._load_from_dir(plugin_path, plugin_meta)
                loaded_count += 1

            except (PluginLoadError, PluginValidationError, ConfigError, ImportError) as e:
                # Логируем ошибку, но продолжаем загрузку других плагинов
                logger.error(f"Ошибка при загрузке плагина '{plugin_name}' из {plugin_path}: {e}",
                             exc_info=False)  # exc_info=False для краткости лога
                # Важно выгрузить перевод, если он был загружен, а плагин упал
                unload_plugin_translation(plugin_name)
            except Exception as e:
                # Ловим непредвиденные ошибки
                logger.error(f"Непредвиденная ошибка при обработке плагина '{plugin_name}': {e}", exc_info=True)
                unload_plugin_translation(plugin_name)

        logger.info(
            f"Загрузка профиля '{profile_path}' завершена. Успешно загружено плагинов: {loaded_count} из {len(plugin_load_queue)}")

    def _read_plugin_metadata(self, plugin_dir: Path) -> Optional[Dict]:
        plugin_toml_path = plugin_dir / "plugin.toml"
        if not plugin_toml_path.is_file(): raise PluginLoadError(f"'plugin.toml' не найден в: {plugin_dir}")
        plugin_data = load_toml(plugin_toml_path)
        plugin_meta = plugin_data.get("metadata", {})
        plugin_name = plugin_meta.get("name")
        entry_point_str = plugin_meta.get("entry_point")
        if not plugin_name or not entry_point_str: raise PluginLoadError(
            f"'name'/'entry_point' отсутствуют в [metadata] ({plugin_dir})")
        plugin_meta["version"] = plugin_meta.get("version", "0.0.0")
        plugin_meta["title"] = plugin_meta.get("title")
        plugin_meta["author"] = plugin_meta.get("author")
        plugin_meta["description"] = plugin_meta.get("description")
        plugin_meta["dependencies"] = plugin_data.get("dependencies", {})
        plugin_meta["permissions"] = plugin_data.get("permissions", {})
        return plugin_meta

    def _load_from_dir(self, plugin_dir: Path, plugin_meta: Dict):
        plugin_name = plugin_meta['name']
        version = plugin_meta['version']
        entry_point_str = plugin_meta['entry_point']
        dependencies = plugin_meta['dependencies']
        permissions = plugin_meta['permissions']
        plugin_title = plugin_meta.get('title')
        plugin_author = plugin_meta.get('author')
        plugin_description = plugin_meta.get('description')
        if plugin_name in self._plugins: logger.warning(f"Плагин '{plugin_name}' уже загружен."); return
        display_name = plugin_title if plugin_title else plugin_name
        logger.info(f"Загрузка '{display_name}' v{version} из {plugin_dir}...")
        try:
            self._check_dependencies(plugin_name, dependencies)
        except PluginLoadError as e:
            logger.error(f"Зависимости '{plugin_name}': {e}")
            raise
        try:
            module_path_str, class_name = entry_point_str.split(":")
        except ValueError:
            raise PluginLoadError(f"Некорректный entry_point '{entry_point_str}' для '{plugin_name}'")
        entry_point_file = plugin_dir / module_path_str.replace(".", "/");  # ... (suffix .py) ...
        if not entry_point_file.suffix: entry_point_file = entry_point_file.with_suffix(".py");  # ...
        if not entry_point_file.is_file(): raise PluginLoadError(
            f"Файл '{entry_point_file}' не найден для '{plugin_name}'")
        try:
            with open(entry_point_file, 'r', encoding='utf-8') as f:
                plugin_code = f.read()
            logger.warning(f"[STUB] AST валидация '{plugin_name}' пропущена.")
        except SyntaxError as e:
            raise PluginLoadError(f"Синтаксис '{plugin_name}': {e}") from e
        except IOError as e:
            raise PluginLoadError(f"Чтение '{entry_point_file}': {e}") from e
        plugin_dir_str = str(plugin_dir.resolve())
        added_to_path = False
        if plugin_dir_str not in sys.path: sys.path.insert(0, plugin_dir_str); added_to_path = True
        try:
            module_name = module_path_str
            logger.debug(f"Импорт '{module_name}' для '{plugin_name}'")
            if module_name in sys.modules: logger.debug(f"Перезагрузка '{module_name}'"); del sys.modules[module_name]
            plugin_module = importlib.import_module(module_name)
            plugin_class: Type[BasePlugin] = getattr(plugin_module, class_name)
            if not issubclass(plugin_class, BasePlugin): raise PluginLoadError(f"'{class_name}' не BasePlugin")
            plugin_specific_config = self._plugin_configs.get(plugin_name, {})
            context = PluginContext(plugin_name=plugin_name, plugin_version=version, plugin_title=plugin_title,
                                    plugin_author=plugin_author,
                                    plugin_description=plugin_description, plugin_config=plugin_specific_config,
                                    plugin_permissions=permissions,
                                    state_manager=self._state_manager, event_bus=self._event_bus,
                                    app_core=self._app_core)
            logger.warning(f"[STUB] Инициализация '{plugin_name}' ВНЕ песочницы.")
            plugin_instance = plugin_class(context)
            try:
                plugin_instance.on_load()
            except Exception as load_exc:
                raise PluginLoadError(f"Ошибка on_load() '{plugin_name}'") from load_exc
            self._plugins[plugin_name] = plugin_instance
            logger.info(f"Плагин '{display_name}' v{version} загружен.")
        except (AttributeError, ImportError, TypeError) as e:
            raise PluginLoadError(f"Ошибка импорта/инстанса '{plugin_name}': {e}") from e
        except Exception as e:
            if not isinstance(e, (PluginLoadError, PluginValidationError)):
                raise PluginLoadError(f"Ошибка загрузки '{plugin_name}': {e}") from e
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
        logger.debug(f"Проверка зависимостей для '{plugin_name}': {dependencies}")
        for dep_name, req_version_spec in dependencies.items():
            target_req_spec = self._dependency_versions.get(dep_name, req_version_spec)
            if target_req_spec != req_version_spec: logger.warning(
                f"'{plugin_name}': Для '{dep_name}' используется версия '{target_req_spec}' из профиля.")
            try:
                installed_version_str = get_version(dep_name)
                logger.debug(f"Найдена зависимость: {dep_name} v{installed_version_str}")
                
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
                display_name = plugin.title
                try:
                    logger.debug(f"Вызов on_unload() для '{display_name}'")
                    plugin.on_unload()
                    unload_plugin_translation(name)
                except Exception as e:
                    logger.error(f"Ошибка выгрузки '{display_name}': {e}", exc_info=True)
        logger.info("Все плагины выгружены.")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)
