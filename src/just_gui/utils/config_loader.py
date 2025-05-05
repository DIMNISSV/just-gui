# src/just_gui/utils/config_loader.py
import toml
from pathlib import Path
from typing import Any, Dict


class ConfigError(Exception):
    """Ошибка при загрузке или парсинге конфигурации."""
    pass


def load_toml(file_path: Path) -> Dict[str, Any]:
    """
    Загружает и парсит TOML файл.

    Args:
        file_path: Путь к TOML файлу.

    Returns:
        Словарь с данными из файла.

    Raises:
        FileNotFoundError: Если файл не найден.
        ConfigError: Если произошла ошибка парсинга TOML.
        Exception: Другие возможные ошибки чтения файла.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Файл конфигурации не найден: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return toml.load(f)
    except toml.TomlDecodeError as e:
        raise ConfigError(f"Ошибка парсинга TOML файла {file_path}: {e}") from e
    except IOError as e:
        raise ConfigError(f"Ошибка чтения файла {file_path}: {e}") from e
