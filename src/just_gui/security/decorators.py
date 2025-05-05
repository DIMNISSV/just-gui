# src/just_gui/security/decorators.py
import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class PermissionError(Exception):
    """Ошибка доступа к ресурсу или выполнения операции."""
    pass


# ЗАГЛУШКА: Реальная проверка разрешений пока отсутствует
def require_permission(*permission_args, **permission_kwargs) -> Callable:
    """
    Декоратор для проверки разрешений перед вызовом функции/метода.
    ПОКА ЯВЛЯЕТСЯ ЗАГЛУШКОЙ - НЕ ВЫПОЛНЯЕТ РЕАЛЬНЫХ ПРОВЕРОК.

    Пример использования (в будущем):
        @require_permission("filesystem.read", path="/data/images")
        def read_image(path: str): ...

        @require_permission("network.connect", host="api.example.com")
        def call_api(): ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # --- НАЧАЛО ЗАГЛУШКИ ---
            # В реальной реализации здесь будет логика проверки:
            # 1. Получить контекст плагина (обычно 'self' для методов плагина).
            # 2. Получить разрешения, выданные этому плагину.
            # 3. Сравнить требуемые разрешения (*permission_args, **permission_kwargs)
            #    с выданными, учитывая контекст вызова (например, конкретный path).
            # 4. Если проверка не пройдена -> raise PermissionError(...)
            instance = args[0] if args else None  # Предполагаем, что это метод
            plugin_name = getattr(instance, 'name', 'unknown_plugin') if instance else 'unknown_context'

            logger.warning(
                f"[SECURITY STUB] Проверка разрешений для '{func.__name__}' "
                f"в плагине '{plugin_name}' пропущена. "
                f"Требовалось: {permission_args}, {permission_kwargs}"
            )
            # --- КОНЕЦ ЗАГЛУШКИ ---

            # Вызов оригинальной функции, если проверка (бы) пройдена
            return func(*args, **kwargs)

        return wrapper

    return decorator
