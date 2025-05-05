# src/just_gui/__main__.py
"""
The entrance point for launching the Just_gui package as a script.
Example: python -m just_gui --profile my_app.toml
"""
from .core import cli

if __name__ == "__main__":
    cli.main()
