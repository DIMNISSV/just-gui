# src/just_gui/state/manager.py
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
from collections import defaultdict
import fnmatch  # Для подписки на паттерны

from .history import HistoryManager, Command

logger = logging.getLogger(__name__)


class StateChangeCommand(Command):
    """Команда для изменения состояния, поддерживающая undo."""

    def __init__(self, state_manager: 'StateManager', key: str, new_value: Any, old_value: Any, description: str = ""):
        super().__init__(description or f"Set {key}")
        self.state_manager = state_manager
        self.key = key
        self.new_value = new_value
        self.old_value = old_value

    def execute(self):
        self.state_manager._set_value(self.key, self.new_value, record_history=False)

    def undo(self):
        self.state_manager._set_value(self.key, self.old_value, record_history=False)


class StateManager:
    """
    Управляет состоянием приложения, обеспечивает реактивность и историю изменений.
    Пока без сложной потокобезопасности (RW Lock), используется простой Lock.
    """

    def __init__(self, history_manager: Optional[HistoryManager] = None):
        self._state: Dict[str, Any] = {}
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)
        self._wildcard_subscribers: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)
        self._lock = threading.Lock()  # Простой Lock для начала
        self._history_manager = history_manager or HistoryManager()

    @property
    def history(self) -> HistoryManager:
        return self._history_manager

    def _get_value_by_key(self, data: Dict, key_parts: List[str]) -> Any:
        """Вспомогательная функция для получения вложенного значения."""
        current = data
        for part in key_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise KeyError(f"Ключ '{'.'.join(key_parts)}' не найден (ошибка на '{part}')")
        return current

    def _set_value_by_key(self, data: Dict, key_parts: List[str], value: Any) -> Tuple[Dict, Any]:
        """
        Вспомогательная функция для установки вложенного значения.
        Возвращает измененный корневой словарь и старое значение.
        Создает вложенные словари при необходимости.
        """
        current = data
        old_value = None
        for i, part in enumerate(key_parts[:-1]):
            if part not in current or not isinstance(current[part], dict):
                # Если ключа нет или он не словарь, создаем новый словарь
                # Это изменение! Нужно копировать, если хотим иммутабельности
                # Для простоты пока мутируем на месте
                current[part] = {}
            current = current[part]

        last_key = key_parts[-1]
        old_value = current.get(last_key)  # Получаем старое значение
        current[last_key] = value  # Устанавливаем новое
        return data, old_value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получает значение из состояния по ключу (поддерживает вложенность через '.').
        """
        with self._lock:
            try:
                if '.' not in key:
                    return self._state.get(key, default)
                else:
                    key_parts = key.split('.')
                    return self._get_value_by_key(self._state, key_parts)
            except KeyError:
                return default
            except Exception as e:
                logger.error(f"Ошибка при получении ключа '{key}': {e}", exc_info=True)
                return default

    def set(self, key: str, value: Any, description: Optional[str] = None):
        """
        Устанавливает значение в состояние по ключу (поддерживает вложенность через '.').
        Записывает изменение в историю и уведомляет подписчиков.
        """
        with self._lock:
            self._set_value(key, value, record_history=True, description=description)

    def _set_value(self, key: str, value: Any, record_history: bool, description: Optional[str] = None):
        """Внутренний метод установки значения."""
        old_value = None
        try:
            if '.' not in key:
                old_value = self._state.get(key)
                if old_value == value: return  # Не делать ничего, если значение не изменилось
                self._state[key] = value
            else:
                key_parts = key.split('.')
                # Получаем старое значение перед модификацией
                try:
                    old_value = self._get_value_by_key(self._state, key_parts)
                except KeyError:
                    old_value = None  # Значения раньше не было

                if old_value == value: return  # Значение не изменилось

                # В _set_value_by_key происходит мутация словаря _state
                self._state, _ = self._set_value_by_key(self._state, key_parts, value)

            logger.debug(f"State changed: '{key}' set to '{value}' (was '{old_value}')")

            # Запись в историю (если нужно)
            if record_history and self._history_manager:
                cmd = StateChangeCommand(self, key, value, old_value, description)
                self._history_manager.add_command(cmd)

            # Уведомление подписчиков
            self._notify_subscribers(key, value)

        except Exception as e:
            logger.error(f"Ошибка при установке ключа '{key}': {e}", exc_info=True)

    def subscribe(self, key_pattern: str, handler: Callable[[Any], None]):
        """
        Подписывает обработчик на изменения значения по ключу или паттерну (с '*').
        """
        with self._lock:
            if '*' in key_pattern:
                self._wildcard_subscribers[key_pattern].append(handler)
                logger.debug(f"Wildcard handler {handler.__name__} subscribed to pattern '{key_pattern}'")
            else:
                self._subscribers[key_pattern].append(handler)
                logger.debug(f"Handler {handler.__name__} subscribed to key '{key_pattern}'")

            # Опционально: немедленно вызвать обработчик с текущим значением?
            # current_value = self.get(key_pattern) # Не сработает для wildcard
            # if current_value is not None: handler(current_value)

    def unsubscribe(self, key_pattern: str, handler: Callable[[Any], None]):
        """Отписывает обработчик от ключа или паттерна."""
        with self._lock:
            removed = False
            if '*' in key_pattern:
                if key_pattern in self._wildcard_subscribers:
                    try:
                        self._wildcard_subscribers[key_pattern].remove(handler)
                        if not self._wildcard_subscribers[key_pattern]:
                            del self._wildcard_subscribers[key_pattern]
                        removed = True
                    except ValueError:
                        pass  # Handler not found
            else:
                if key_pattern in self._subscribers:
                    try:
                        self._subscribers[key_pattern].remove(handler)
                        if not self._subscribers[key_pattern]:
                            del self._subscribers[key_pattern]
                        removed = True
                    except ValueError:
                        pass  # Handler not found

            if removed:
                logger.debug(f"Handler {handler.__name__} unsubscribed from '{key_pattern}'")
            else:
                logger.warning(f"Handler {handler.__name__} not found for '{key_pattern}' during unsubscribe")

    def _notify_subscribers(self, changed_key: str, new_value: Any):
        """Уведомляет всех релевантных подписчиков об изменении."""
        handlers_to_call: List[Callable[[Any], None]] = []

        # Точные совпадения
        if changed_key in self._subscribers:
            handlers_to_call.extend(self._subscribers[changed_key])

        # Wildcard совпадения (используем fnmatch)
        for pattern, handlers in self._wildcard_subscribers.items():
            if fnmatch.fnmatch(changed_key, pattern):
                handlers_to_call.extend(handlers)

        # Вызов обработчиков
        # Пока синхронно, т.к. StateManager обычно используется из GUI потока
        # TODO: Рассмотреть асинхронный вызов или запуск в отдельном потоке для долгих обработчиков
        logger.debug(f"Notifying {len(handlers_to_call)} subscribers about change in '{changed_key}'")
        for handler in handlers_to_call:
            try:
                handler(new_value)
            except Exception as e:
                logger.error(f"Error executing state subscriber {handler.__name__} for key '{changed_key}': {e}",
                             exc_info=True)
