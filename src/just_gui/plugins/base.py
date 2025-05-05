# src/just_gui/plugins/base.py
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Callable  # Добавили Callable

# Импортируем QWidget для type hinting фабрики
from PySide6.QtWidgets import QWidget

# Предотвращение циклических импортов с помощью TYPE_CHECKING
if TYPE_CHECKING:
    from ..state.manager import StateManager
    from ..events.bus import EventBus
    from ..core.app import AppCore

logger = logging.getLogger(__name__)

# --- Новый тип: Фабричный метод для создания виджета представления ---
ViewFactory = Callable[[], QWidget]


@dataclass
class PluginContext:
    """Контекст, передаваемый плагину при инициализации."""
    plugin_name: str
    plugin_version: str
    plugin_config: Dict[str, Any]  # Конфигурация из app_profile[plugin_configs]
    state_manager: 'StateManager'
    event_bus: 'EventBus'
    app_core: 'AppCore'  # Доступ к ядру для регистрации UI и других действий
    plugin_permissions: Dict[str, Any] = field(default_factory=dict)  # Разрешения из plugin.toml[permissions]

    def get_config(self, key: str, default: Any = None) -> Any:
        """Удобный метод для получения конфигурации плагина."""
        keys = key.split('.')
        value = self.plugin_config
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value[k]
                else:
                    logger.debug(
                        f"Ключ '{k}' не найден или не является словарем в конфигурации плагина '{self.plugin_name}' при поиске '{key}'")
                    return default
            return value
        except KeyError:
            logger.debug(f"Ключ '{keys[-1]}' не найден в конфигурации плагина '{self.plugin_name}' при поиске '{key}'")
            return default
        except Exception as e:
            logger.warning(
                f"Неожиданная ошибка при получении конфигурации '{key}' для плагина '{self.plugin_name}': {e}")
            return default

    def has_permission(self, *permission_parts: str) -> bool:
        """
        Проверяет, имеет ли плагин указанное разрешение.
        ПОКА ЗАГЛУШКА. В будущем будет проверять self.plugin_permissions.
        Пример: context.has_permission("filesystem", "read", "/data/images")
        """
        permission_key = ".".join(permission_parts)
        logger.warning(
            f"[SECURITY STUB] Проверка разрешения '{permission_key}' для плагина '{self.plugin_name}' всегда возвращает True.")
        # Реальная логика будет сложнее, должна парсить self.plugin_permissions
        # и сравнивать запрошенное разрешение с выданными.
        # current_perms = self.plugin_permissions
        # try:
        #     for part in permission_parts[:-1]:
        #         current_perms = current_perms[part]
        #     last_part = permission_parts[-1]
        #     # Логика проверки значения (может быть bool, список путей, и т.д.)
        #     # return last_part in current_perms # Очень упрощенно
        # except (KeyError, TypeError):
        #      return False
        return True  # ЗАГЛУШКА

    # TODO: Добавить метод для доступа к ресурсам плагина (get_resource)


class BasePlugin(ABC):
    """Абстрактный базовый класс для всех плагинов."""

    def __init__(self, context: PluginContext):
        self.context = context
        self.name = context.plugin_name
        self.version = context.plugin_version
        self._state = context.state_manager  # Удобный доступ
        self._bus = context.event_bus  # Удобный доступ
        self._app = context.app_core  # Удобный доступ
        self._config = context.plugin_config  # Удобный доступ
        self._permissions = context.plugin_permissions  # Удобный доступ
        logger.info(f"Инициализирован плагин: {self.name} v{self.version}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Получает параметр конфигурации плагина."""
        return self.context.get_config(key, default)

    def has_permission(self, *permission_parts: str) -> bool:
        """Проверяет, имеет ли плагин запрошенное разрешение."""
        return self.context.has_permission(*permission_parts)

    # --- Методы жизненного цикла ---
    @abstractmethod
    def on_load(self):
        """
        Вызывается после успешной загрузки плагина.
        Здесь следует выполнять инициализацию, подписку на события,
        объявление представлений и регистрацию действий в меню/тулбаре.
        """
        logger.debug(f"Плагин '{self.name}': Вызван on_load()")
        pass

    def on_unload(self):
        """
        Вызывается перед выгрузкой плагина.
        Здесь следует выполнять очистку ресурсов, отписку от событий.
        Виджеты представлений будут удалены AppCore.
        """
        logger.debug(f"Плагин '{self.name}': Вызван on_unload()")
        pass

    # --- НОВЫЙ МЕТОД: Объявление представления ---
    def declare_view(self, view_id: str, name: str, factory: ViewFactory):
        """
        Объявляет представление (виджет), которое может быть открыто пользователем
        (например, как вкладка или док-виджет).

        Args:
            view_id: Уникальный идентификатор представления в рамках плагина (e.g., "main_editor").
            name: Имя, отображаемое пользователю (e.g., "Редактор").
            factory: Функция (без аргументов), которая создает и возвращает
                     новый экземпляр QWidget для этого представления.
        """
        logger.debug(f"Плагин '{self.name}': Объявление представления view_id='{view_id}', name='{name}'")
        self._app.declare_view(self.name, view_id, name, factory)

    # --- Старые методы регистрации UI (теперь для действий, а не представлений) ---
    def register_menu_action(self, menu_path: str, action):  # action - это QAction
        """Регистрирует действие плагина в главном меню."""
        logger.debug(f"Плагин '{self.name}': Регистрация действия меню '{menu_path}'")
        # Проверка типа action для предотвращения ошибок
        if not hasattr(action, 'triggered'):  # Простая проверка на QAction-подобный объект
            logger.error(
                f"Плагин '{self.name}': Попытка зарегистрировать не QAction в меню '{menu_path}'. Тип: {type(action)}")
            return
        self._app.register_menu_action(self.name, menu_path, action)

    def register_toolbar_widget(self, widget, section: Optional[str] = None):  # widget - QWidget
        """Регистрирует виджет на панели инструментов."""
        section_name = section or "Default"
        logger.debug(f"Плагин '{self.name}': Регистрация виджета тулбара в секции '{section_name}'")
        # Добавляем имя плагина как префикс к секции для избежания конфликтов
        full_section = f"{self.name}/{section_name}"
        self._app.register_toolbar_widget(full_section, widget)

    def update_status(self, message: str, timeout: int = 0):
        """Обновляет сообщение в строке состояния."""
        # logger.debug(f"Плагин '{self.name}': Обновление статуса: '{message}'")
        self._app.update_status(f"[{self.name}] {message}", timeout)

    # Добавить другие методы регистрации по необходимости (док-виджеты, и т.д.)
