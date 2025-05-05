# src/just_gui/plugins/manager.py
import importlib
import logging
import sys
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Tuple
# Используем importlib.metadata вместо pkg_resources
from importlib.metadata import version as get_version, PackageNotFoundError

# TODO: Для сравнения версий SemVer понадобится внешняя библиотека
# from semantic_version import Version, Spec

from ..utils.config_loader import load_toml, ConfigError
from .base import BasePlugin, PluginContext
from .validator import validate_plugin_ast, PluginValidationError
from ..security.sandbox import Sandbox # Пока заглушка

# Предотвращение циклических импортов
if TYPE_CHECKING:
    from ..state.manager import StateManager
    from ..events.bus import EventBus
    from ..core.app import AppCore

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    """Ошибка при загрузке плагина."""
    pass


class PluginManager:
    """Управляет загрузкой, инициализацией и выгрузкой плагинов."""

    def __init__(self, app_core: 'AppCore', state_manager: 'StateManager', event_bus: 'EventBus'):
        self._app_core = app_core
        self._state_manager = state_manager
        self._event_bus = event_bus
        self._plugins: Dict[str, BasePlugin] = {} # Словарь загруженных плагинов: name -> instance
        self._plugin_configs: Dict[str, Dict[str, Any]] = {} # Общая конфигурация из профиля
        self._dependency_versions: Dict[str, str] = {} # Заданные в профиле версии зависимостей

    @property
    def loaded_plugins(self) -> Dict[str, BasePlugin]:
        return self._plugins.copy()

    async def load_profile(self, profile_path: str):
        """Загружает профиль приложения и все указанные в нем плагины."""
        logger.info(f"Загрузка профиля приложения из: {profile_path}")
        try:
            profile_data = load_toml(Path(profile_path))
        except (FileNotFoundError, ConfigError) as e:
            logger.error(f"Не удалось загрузить профиль: {e}", exc_info=True)
            # TODO: Сообщить пользователю в GUI
            return # Прекратить загрузку, если профиль не найден/невалиден

        # Сохраняем общие конфиги и зависимости
        self._plugin_configs = profile_data.get("plugin_configs", {})
        # Зависимости теперь в [plugins.dependencies], а не [dependencies]
        plugins_section = profile_data.get("plugins", {})
        self._dependency_versions = plugins_section.get("dependencies", {})

        # TODO: Реализовать топологическую сортировку на основе зависимостей плагинов

        # Загрузка плагинов
        plugin_sources = profile_data.get("plugins", {})
        load_tasks = []

        # --- Сбор информации о плагинах перед загрузкой ---
        plugin_load_queue: List[Tuple[str, Path, Dict]] = [] # (name, path, metadata)
        plugin_metadata_map: Dict[str, Dict] = {} # name -> metadata

        # Локальные плагины
        for local_path_str in plugin_sources.get("local", []):
            local_path = Path(local_path_str)
             # TODO: Обработать относительные пути относительно профиля
            if not local_path.is_absolute():
                 profile_dir = Path(profile_path).parent
                 local_path = (profile_dir / local_path).resolve()

            if local_path.is_dir():
                logger.info(f"Обнаружен локальный плагин в: {local_path}")
                try:
                    meta = self._read_plugin_metadata(local_path)
                    if meta:
                         plugin_name = meta['name']
                         if plugin_name in plugin_metadata_map:
                             logger.warning(f"Дубликат плагина '{plugin_name}' найден в {local_path}. Используется первый найденный.")
                         else:
                             plugin_metadata_map[plugin_name] = meta
                             plugin_load_queue.append((plugin_name, local_path, meta))
                except (PluginLoadError, ConfigError) as e:
                    logger.error(f"Ошибка чтения метаданных локального плагина из {local_path}: {e}")
            else:
                logger.warning(f"Путь к локальному плагину не найден или не является директорией: {local_path}")

        # Плагины из Git (пока заглушка)
        git_plugins = plugin_sources.get("git", [])
        if git_plugins:
            logger.warning("[PLUGIN MANAGER STUB] Загрузка плагинов из Git пока не реализована.")
            # TODO: В будущем здесь будет асинхронное клонирование и чтение метаданных

        # --- Топологическая сортировка (ЗАГЛУШКА) ---
        # TODO: Реализовать реальную сортировку на основе поля [dependencies] в plugin.toml
        # Пока просто используем порядок из plugin_load_queue
        logger.debug(f"Порядок загрузки плагинов (без сортировки): {[name for name, _, _ in plugin_load_queue]}")
        sorted_load_order = plugin_load_queue # Заглушка

        # --- Последовательная загрузка в отсортированном порядке ---
        for plugin_name, plugin_path, plugin_meta in sorted_load_order:
             try:
                 # Загрузка пока синхронная для простоты
                 self._load_from_dir(plugin_path, plugin_meta)
             except (PluginLoadError, PluginValidationError, ConfigError, ImportError) as e:
                 logger.error(f"Ошибка загрузки плагина '{plugin_name}' из {plugin_path}: {e}", exc_info=True)
                 # TODO: Сообщить пользователю. Возможно, прервать загрузку зависимых плагинов?

        # --- Обработка асинхронных загрузок из Git (в будущем) ---
        if load_tasks:
            results = await asyncio.gather(*load_tasks, return_exceptions=True)
            # ... обработка результатов ...

        logger.info(f"Загрузка профиля завершена. Загружено плагинов: {len(self._plugins)}")

    def _read_plugin_metadata(self, plugin_dir: Path) -> Optional[Dict]:
        """Читает и валидирует метаданные из plugin.toml."""
        plugin_toml_path = plugin_dir / "plugin.toml"
        if not plugin_toml_path.is_file():
            raise PluginLoadError(f"Файл 'plugin.toml' не найден в директории: {plugin_dir}")

        plugin_data = load_toml(plugin_toml_path)
        plugin_meta = plugin_data.get("metadata", {})
        plugin_name = plugin_meta.get("name")
        entry_point_str = plugin_meta.get("entry_point")

        if not plugin_name or not entry_point_str:
            raise PluginLoadError(f"В 'plugin.toml' ({plugin_dir}) отсутствуют обязательные поля 'name' или 'entry_point' в секции [metadata]")

        # Добавляем другие поля для удобства (версия, зависимости)
        plugin_meta["version"] = plugin_meta.get("version", "0.0.0")
        plugin_meta["dependencies"] = plugin_data.get("dependencies", {}) # Зависимости самого плагина
        plugin_meta["permissions"] = plugin_data.get("permissions", {}) # Разрешения

        return plugin_meta

    def _load_from_dir(self, plugin_dir: Path, plugin_meta: Dict):
        """Загружает, валидирует и инициализирует плагин из директории, используя прочитанные метаданные."""
        plugin_name = plugin_meta['name']
        version = plugin_meta['version']
        entry_point_str = plugin_meta['entry_point']
        dependencies = plugin_meta['dependencies']
        permissions = plugin_meta['permissions'] # Пока не используется

        if plugin_name in self._plugins:
             logger.warning(f"Плагин с именем '{plugin_name}' уже загружен. Пропуск дубликата из {plugin_dir}.")
             return

        logger.info(f"Загрузка плагина '{plugin_name}' v{version} из {plugin_dir}...")

        # 2. Проверка зависимостей (используя importlib.metadata)
        try:
            self._check_dependencies(plugin_name, dependencies)
        except PluginLoadError as e:
             logger.error(f"Ошибка зависимостей для плагина '{plugin_name}': {e}")
             raise # Прерываем загрузку этого плагина

        # 3. Валидация кода (AST) - пока базовая
        try:
            module_path_str, class_name = entry_point_str.split(":")
        except ValueError:
            raise PluginLoadError(f"Некорректный формат 'entry_point' ({entry_point_str}) в plugin.toml для '{plugin_name}'. Ожидается 'module.path:ClassName'")

        entry_point_file = plugin_dir / module_path_str.replace(".", "/")
        if not entry_point_file.suffix:
             entry_point_file = entry_point_file.with_suffix(".py")

        if not entry_point_file.is_file():
             raise PluginLoadError(f"Файл точки входа '{entry_point_file}' не найден для плагина '{plugin_name}'")

        try:
             with open(entry_point_file, 'r', encoding='utf-8') as f:
                 plugin_code = f.read()
             # ЗАГЛУШКА БЕЗОПАСНОСТИ: Валидация AST пока отключена/пропущена
             # if not validate_plugin_ast(plugin_code):
             #     # Логгирование ошибки происходит внутри validate_plugin_ast
             #     raise PluginValidationError(f"AST валидация плагина '{plugin_name}' не пройдена.")
             logger.warning(f"[SECURITY STUB] AST валидация для плагина '{plugin_name}' пропущена.")
        except SyntaxError as e:
             raise PluginLoadError(f"Синтаксическая ошибка в коде плагина '{plugin_name}': {e}") from e
        except IOError as e:
             raise PluginLoadError(f"Ошибка чтения файла точки входа '{entry_point_file}': {e}") from e

        # 4. Динамический импорт и инстанцирование
        plugin_dir_str = str(plugin_dir.resolve())
        added_to_path = False
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)
            added_to_path = True

        try:
            module_name = module_path_str
            logger.debug(f"Импорт модуля '{module_name}' для плагина '{plugin_name}'")
            # Удаляем модуль из кэша, если он был импортирован ранее (например, другим плагином)
            # Это позволяет перезагружать код плагина при перезапуске профиля, но может быть рискованно.
            if module_name in sys.modules:
                 logger.debug(f"Удаление существующего модуля '{module_name}' из sys.modules перед импортом")
                 del sys.modules[module_name]

            plugin_module = importlib.import_module(module_name)

            plugin_class: Type[BasePlugin] = getattr(plugin_module, class_name)
            if not issubclass(plugin_class, BasePlugin):
                raise PluginLoadError(f"Класс '{class_name}' в плагине '{plugin_name}' не наследует BasePlugin")

            # 5. Создание контекста и инстанцирование
            plugin_specific_config = self._plugin_configs.get(plugin_name, {})
            context = PluginContext(
                plugin_name=plugin_name,
                plugin_version=version,
                plugin_config=plugin_specific_config,
                state_manager=self._state_manager,
                event_bus=self._event_bus,
                app_core=self._app_core,
                plugin_permissions=permissions # Передаем разрешения в контекст
            )

            # 6. ЗАПУСК В ПЕСОЧНИЦЕ (ЗАГЛУШКА)
            logger.warning(f"[PLUGIN MANAGER STUB] Запуск инициализации плагина '{plugin_name}' ВНЕ песочницы.")
            # with Sandbox(plugin_name, mode='soft'): # Запуск в песочнице в будущем
            plugin_instance = plugin_class(context)

            # 7. Вызов on_load()
            try:
                 plugin_instance.on_load()
            except Exception as load_exc:
                 logger.error(f"Ошибка при вызове on_load() плагина '{plugin_name}': {load_exc}", exc_info=True)
                 # Считаем плагин не загруженным, если on_load упал
                 raise PluginLoadError(f"Ошибка в on_load() плагина '{plugin_name}'") from load_exc

            self._plugins[plugin_name] = plugin_instance
            logger.info(f"Плагин '{plugin_name}' v{version} успешно загружен и инициализирован.")

        except (AttributeError, ImportError, TypeError) as e:
             raise PluginLoadError(f"Ошибка при импорте или инстанцировании плагина '{plugin_name}': {e}") from e
        except Exception as e: # Ловим другие возможные ошибки при инициализации
            # Проверяем, не является ли это уже обернутой ошибкой PluginLoadError
            if not isinstance(e, PluginLoadError):
                raise PluginLoadError(f"Непредвиденная ошибка при загрузке плагина '{plugin_name}': {e}") from e
            else:
                raise # Перевыбрасываем уже обернутую ошибку
        finally:
            # Убираем путь из sys.path, если добавляли
            if added_to_path and plugin_dir_str in sys.path:
                try:
                    sys.path.remove(plugin_dir_str)
                except ValueError: pass


    # ЗАГЛУШКА: Метод для загрузки из Git
    async def load_from_git(self, repo_url: str, version_ref: str = "main"):
        """
        Загружает плагин из Git репозитория (асинхронно).
        ПОКА НЕ РЕАЛИЗОВАНО.
        """
        logger.warning(f"[PLUGIN MANAGER STUB] Загрузка из Git ({repo_url} @ {version_ref}) не реализована.")
        # Шаги в будущем:
        # 1. Создать временную директорию.
        # 2. Склонировать репозиторий (используя aiohttp + git CLI или библиотеку типа GitPython).
        # 3. Переключиться на нужную ветку/тег/коммит (`version_ref`).
        # 4. Вызвать `_read_plugin_metadata(temp_dir)`
        # 5. Добавить в очередь на загрузку или загрузить сразу (в зависимости от зависимостей).
        # 6. Очистить временную директорию (даже в случае ошибки).
        raise NotImplementedError("Загрузка плагинов из Git еще не реализована.")

    def _check_dependencies(self, plugin_name: str, dependencies: Dict[str, str]):
        """
        Проверяет наличие и версии зависимостей плагина, используя importlib.metadata.
        """
        if not dependencies:
            return # Нет зависимостей для проверки

        logger.debug(f"Проверка зависимостей для плагина '{plugin_name}': {dependencies}")
        for dep_name, req_version_spec in dependencies.items():
            target_req_spec = req_version_spec # Требование из plugin.toml

            # Проверка версии, заданной в профиле (она имеет приоритет)
            profile_req_version = self._dependency_versions.get(dep_name)
            if profile_req_version:
                 if profile_req_version != req_version_spec:
                      logger.warning(f"Для зависимости '{dep_name}' плагина '{plugin_name}' используется версия '{profile_req_version}' из профиля вместо '{req_version_spec}', указанной в плагине.")
                 target_req_spec = profile_req_version # Используем версию из профиля

            try:
                # Получаем установленную версию
                installed_version_str = get_version(dep_name)
                logger.debug(f"Найдена зависимость: {dep_name} v{installed_version_str}")

                # --- Проверка совместимости версий (ТРЕБУЕТ БИБЛИОТЕКИ SEMVER) ---
                # ЗАГЛУШКА: Пока просто проверяем наличие, без сравнения версий
                logger.warning(f"[DEPENDENCY STUB] Проверка совместимости версий для '{dep_name}' (требуется: '{target_req_spec}', установлено: '{installed_version_str}') НЕ РЕАЛИЗОВАНА.")
                # Пример с библиотекой semantic_version:
                # try:
                #     req_spec = Spec(target_req_spec)
                #     installed_version = Version(installed_version_str)
                #     if installed_version not in req_spec:
                #         raise PluginLoadError(
                #             f"Несовместимая версия зависимости '{dep_name}' для плагина '{plugin_name}'. "
                #             f"Требуется: '{target_req_spec}', установлено: '{installed_version_str}'"
                #         )
                #     else:
                #          logger.debug(f"Версия {dep_name} v{installed_version_str} совместима с '{target_req_spec}'")
                # except ValueError as semver_error:
                #      logger.error(f"Ошибка парсинга SemVer для зависимости '{dep_name}': {semver_error}")
                #      raise PluginLoadError(f"Некорректная спецификация версии для '{dep_name}': {target_req_spec} или {installed_version_str}")


            except PackageNotFoundError:
                 # Зависимость не найдена
                 logger.error(f"Отсутствует обязательная зависимость '{dep_name}' (требуется: '{target_req_spec}') для плагина '{plugin_name}'")
                 raise PluginLoadError(f"Отсутствует зависимость '{dep_name}' (требуется: {target_req_spec})")
            except Exception as e:
                 # Ловим другие возможные ошибки (например, при сравнении версий)
                 logger.error(f"Ошибка при проверке зависимости '{dep_name}' для '{plugin_name}': {e}", exc_info=True)
                 raise PluginLoadError(f"Ошибка проверки зависимости '{dep_name}'") from e


    def unload_all(self):
        """Выгружает все загруженные плагины."""
        logger.info("Выгрузка всех плагинов...")
        # Выгружаем в порядке, обратном загрузке, чтобы учесть зависимости
        plugin_names = list(self._plugins.keys())
        for name in reversed(plugin_names):
            if name in self._plugins: # Проверяем, не был ли уже удален (например, из-за ошибки)
                plugin = self._plugins.pop(name)
                try:
                    logger.debug(f"Вызов on_unload() для плагина '{name}'")
                    # ЗАГЛУШКА: Запуск ВНЕ песочницы
                    # with Sandbox(name, mode='soft'):
                    plugin.on_unload()
                except Exception as e:
                    logger.error(f"Ошибка при выгрузке плагина '{name}': {e}", exc_info=True)
            else:
                 logger.warning(f"Плагин '{name}' не найден в словаре при попытке выгрузки.")
        logger.info("Все плагины выгружены.")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Возвращает загруженный плагин по имени."""
        return self._plugins.get(name)