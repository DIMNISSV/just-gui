# src/just_gui/core/__init__.py
from .app import AppCore, APP_NAME, APP_AUTHOR
from .cli import main

__all__ = ["AppCore", "main", "APP_NAME", "APP_AUTHOR"]
