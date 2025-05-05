# src/just_gui/utils/config_loader.py
import toml
from pathlib import Path
from typing import Any, Dict


class ConfigError(Exception):
    """Error during configuration loading or parsing."""
    pass


def load_toml(file_path: Path) -> Dict[str, Any]:
    """
    Loads and parses a TOML file.

    Args:
        file_path: Path to the TOML file.

    Returns:
        Dictionary with data from the file.

    Raises:
        FileNotFoundError: If the file is not found.
        ConfigError: If a TOML parsing error occurred.
        Exception: Other possible file reading errors.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return toml.load(f)
    except toml.TomlDecodeError as e:
        raise ConfigError(f"Error parsing TOML file {file_path}: {e}") from e
    except IOError as e:
        raise ConfigError(f"Error reading file {file_path}: {e}") from e
