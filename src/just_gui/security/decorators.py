# src/just_gui/security/decorators.py
import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class PermissionError(Exception):
    """Error accessing resource or performing operation."""
    pass


def require_permission(*permission_args, **permission_kwargs) -> Callable:
    """
    Decorator for checking permissions before calling a function/method.
    CURRENTLY A STUB - DOES NOT PERFORM REAL CHECKS.

    Future usage example:
        @require_permission("filesystem.read", path="/data/images")
        def read_image(path: str): ...

        @require_permission("network.connect", host="api.example.com")
        def call_api(): ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            instance = args[0] if args else None
            plugin_name = getattr(instance, 'name', 'unknown_plugin') if instance else 'unknown_context'

            logger.warning(
                f"[SECURITY STUB] Permission check for '{func.__name__}' "
                f"in plugin '{plugin_name}' skipped. "
                f"Required: {permission_args}, {permission_kwargs}"
            )

            return func(*args, **kwargs)

        return wrapper

    return decorator
