# just-gui

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Version](https://img.shields.io/badge/version-0.1.1--beta-orange.svg)

A lightweight framework for creating modular (plugin-oriented) graphical applications using PySide6 with state
management, an event bus, and basic extension mechanisms.

**Warning:** The project is in an early development stage (beta). Security features (sandbox, permission decorators) are
currently stubs and do not provide real protection.

## About the Project

`just-gui` provides a core structure for building desktop GUI applications where the main logic and UI components are
implemented as plugins. The framework handles tasks such as:

* Managing the application and GUI lifecycle (PySide6).
* Loading and initializing plugins based on a TOML profile file.
* Centralized application state management with change history (Undo/Redo).
* An asynchronous event bus for interaction between components and plugins.
* Standardized extension points for plugins (declaring views, registering menu/toolbar actions).
* Saving/restoring the state of open views (tabs).
* Theme management (supports qdarktheme).

## Installation

The project can be installed directly from the Git repository using Poetry or Pip.

### Via Poetry

1. Install Poetry if you haven't already. Follow the instructions on
   the [official Poetry website](https://python-poetry.org/docs/#installation).
2. Navigate to your project directory where you want to use `just-gui`.
3. Add `just-gui` as a dependency:

   ```bash
   poetry add git+https://github.com/DIMNISSV/just-gui.git#v0.1.1-beta
   ```
   (Replace `v0.1.1-beta` with the actual tag or branch if needed)

4. Poetry will install `just-gui` and all its dependencies into your project's virtual environment.

### Via Pip

1. Ensure you have Git and Python 3.8+ installed.
2. Install `just-gui` from the Git repository:

   ```bash
   pip install git+https://github.com/DIMNISSV/just-gui.git@v0.1.1-beta
   ```
   (Replace `v0.1.1-beta` with the actual tag, branch, or commit hash if needed. You can omit `@v0.1.1-beta` to install
   the latest version from the master/main branch, but specifying the version is preferred.)

3. Optionally, install the additional dependency for the dark theme:

   ```bash
   pip install qdarktheme
   ```

## Usage

To run an application built on `just-gui`, you need to specify the path to a TOML profile file:

```bash
python -m just_gui --profile path/to/your/profile.toml
```

**Example Profile File (`my_app.toml`):**

```toml
[profile_metadata]
title = "My Just-GUI Application"
version = "1.0.0"
author = "Your Name"
description = "An example application using Just-GUI"

[config]
theme = "dark" # or "light"
log_level = "DEBUG" # INFO, WARNING, ERROR, CRITICAL

[plugins]
# Example local plugin (the directory relative_path/my_plugin must exist)
local = [
    "relative_path/my_plugin"
]

# Example dependencies that must be installed in the environment
[plugins.dependencies]
some_library = ">=1.0,<2.0"

[plugin_configs.my_plugin]
# Configuration specific to the "my_plugin" plugin
setting1 = "value1"
setting2 = 123
```

Inside the plugin directory (`relative_path/my_plugin`), there must be a `plugin.toml` file with the plugin's metadata
and the source code.

## Plugin Structure

Minimal structure for a local plugin:

```
my_plugin/
├── plugin.toml
└── my_plugin_module.py
```

**plugin.toml:**

```toml
[metadata]
name = "my_plugin" # Unique plugin identifier
entry_point = "my_plugin_module:MyPluginClass" # Module:PluginClass
version = "0.1.0"
title = "My Plugin" # Optional, for display
author = "Plugin Author" # Optional
description = "A simple plugin example" # Optional

# [dependencies] # Optional, dependencies specific to this plugin

# [permissions] # Optional, declared permissions (stub in current version)
```

**my_plugin_module.py:**

```python
from just_gui.plugins.base import BasePlugin, PluginContext, ViewFactory
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton
from PySide6.QtGui import QAction
import logging

logger = logging.getLogger(__name__)


def create_example_view() -> QWidget:
    """Factory function for the example view."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel("Hello from Example View!")
    button = QPushButton("Click Me")
    button.clicked.connect(lambda: logger.info("Button clicked in example view!"))
    layout.addWidget(label)
    layout.addWidget(button)
    return widget


class MyPluginClass(BasePlugin):
    def __init__(self, context: PluginContext):
        super().__init__(context)
        # Access plugin-specific config
        logger.info(f"MyPlugin initialized. Config setting1: {self.get_config('setting1')}")

    def on_load(self):
        """Called when the plugin is loaded."""
        logger.info(f"{self.name}: on_load called.")

        # Declare a view
        self.declare_view(
            view_id="example_view",
            name="Example View",
            factory=create_example_view  # Pass the factory function
        )

        # Register a menu action
        example_action = QAction("Trigger Example Action", self._app)
        example_action.triggered.connect(self._on_example_action)
        # Menus are automatically created if they don't exist
        self.register_menu_action("Tools/My Plugin Actions", example_action)

        # Register a toolbar widget
        toolbar_button = QPushButton("Plugin Toolbar Btn")
        toolbar_button.clicked.connect(lambda: self.update_status("Toolbar button clicked!", 3000))
        self.register_toolbar_widget(toolbar_button, section="My Section")

    def on_unload(self):
        """Called when the plugin is unloaded."""
        logger.info(f"{self.name}: on_unload called. Cleaning up...")
        # Perform cleanup here (e.g., unsubscribe from events, release resources)

    def _on_example_action(self):
        """Handler for the example menu action."""
        logger.info(f"{self.name}: Example menu action triggered.")
        self.update_status(f"{self.title}: Menu action triggered!", 5000)

```

## License

The project is distributed under the MIT License. See the `LICENSE` file in the repository root (if present) or the
license information provided in the code and this README.

## Donate

You can donate to the development using Monero: `87QGCoHeYz74Ez22geY1QHerZqbN5J2z7JLNgyWijmrpCtDuw66kR7UQsWXWd6QCr3G86TBADcyFX5pNaqt7dpsEHE9HBJs`

[![imageban](https://i4.imageban.ru/thumbs/2025.04.15/566393a122f2a27b80defcbe9b074dc0.png)](https://imageban.ru/show/2025/04/15/566393a122f2a27b80defcbe9b074dc0/png)

I will also be happy to arrange any other way for you to transfer funds, please contact me.

## Contacts

[telegram](https://t.me/dimnissv) or email [dimnissv@yandex.kz](mailto:dimnissv@yandex.kz)