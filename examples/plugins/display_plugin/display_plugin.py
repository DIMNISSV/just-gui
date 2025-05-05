# examples/plugins/display_plugin/display_plugin.py
import logging

from PySide6.QtCore import Slot, Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

from just_gui import BasePlugin

logger = logging.getLogger(__name__)


class DisplayWidget(QWidget):
    """A widget that displays the counter value from the state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display_label = QLabel("Waiting for counter value...")
        font = self.display_label.font()
        font.setPointSize(24)
        self.display_label.setFont(font)
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.display_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        self.setLayout(layout)

        self.setMinimumSize(200, 100)

    @Slot(object)
    def update_value(self, value):
        """Updates the displayed value."""
        logger.debug(f"DisplayWidget: Received new value {value} from state.")
        if value is None:
            self.display_label.setText("Counter not initialized")
        else:
            if isinstance(value, (int, float)):
                self.display_label.setText(f"Current value: {value}")
            else:
                self.display_label.setText(f"Unknown value: {value}")


class DisplayPlugin(BasePlugin):
    """A plugin that displays the counter value in its own tab."""

    COUNTER_STATE_KEY = "counter.value"

    def on_load(self):
        """Initializes the plugin upon loading."""
        logger.info(f"Plugin '{self.name}': Loading...")

        self.declare_view(
            view_id="display_widget",
            name="Display",
            factory=self._create_display_widget
        )

        logger.info(f"Plugin '{self.name}': Loaded.")

    def _create_display_widget(self) -> DisplayWidget:
        """Factory method for creating a DisplayWidget instance."""
        logger.debug(
            f"Plugin '{self.name}': Factory method _create_display_widget() called. Creating DisplayWidget instance...")

        widget = DisplayWidget()

        self._state.subscribe(self.COUNTER_STATE_KEY, widget.update_value)
        logger.debug(f"DisplayWidget subscribed to state '{self.COUNTER_STATE_KEY}'")

        widget.setProperty("unsubscribe_callback",
                           lambda: self._state.unsubscribe(self.COUNTER_STATE_KEY, widget.update_value))

        initial_value = self._state.get(self.COUNTER_STATE_KEY)
        widget.update_value(initial_value)
        logger.debug(f"Plugin '{self.name}': DisplayWidget created and configured.")

        return widget

    def on_unload(self):
        """Cleanup upon plugin unloading."""
        logger.info(f"Plugin '{self.name}': Unloading...")
        logger.info(f"Plugin '{self.name}': Unloaded.")
