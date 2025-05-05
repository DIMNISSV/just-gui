# src/just_gui/__main__.py
"""
Точка входа для запуска пакета just_gui как скрипта.
Пример: python -m just_gui --profile my_app.toml
"""
from .core import cli

if __name__ == "__main__":
    cli.main()
