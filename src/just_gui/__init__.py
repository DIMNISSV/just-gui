# src/just_gui/__init__.py
"""
Основной пакет библиотеки just-gui.
"""

# Экспорт ключевых классов для удобства использования
from .core.app import AppCore
from .plugins.base import BasePlugin, PluginContext
from .state.manager import StateManager
from .events.bus import EventBus
from .security.decorators import require_permission  # Пока заглушка

__version__ = "0.0.1-alpha.0"

__all__ = [
    "AppCore",
    "BasePlugin",
    "PluginContext",
    "StateManager",
    "EventBus",
    "require_permission",
    "__version__",
]
