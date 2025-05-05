# examples/plugins/event_listener/listener.py
import logging
from typing import Dict, Any

from PySide6.QtCore import Slot
from PySide6.QtGui import QAction, QIcon

from just_gui import BasePlugin

logger = logging.getLogger(__name__)


class ListenerPlugin(BasePlugin):
    """A plugin that listens to counter events and displays them in the status bar,
       and also allows logging the current value via a button."""

    COUNTER_STATE_KEY = "counter.value"
    COUNTER_EVENT_PATTERN = "counter.*"

    def on_load(self):
        """Initializes the plugin upon loading."""
        logger.info(f"Plugin '{self.name}': Loading...")

        self._bus.subscribe(self.COUNTER_EVENT_PATTERN, self._handle_counter_event)
        logger.debug(f"Plugin '{self.name}': Subscribed to events '{self.COUNTER_EVENT_PATTERN}'")

        log_action = QAction(QIcon.fromTheme("document-print-preview"), "Log Counter", self._app)
        log_action.setStatusTip("Output the current counter value to the log")
        log_action.triggered.connect(self._log_current_count)
        self.register_toolbar_widget(log_action, section="Info")

        logger.info(f"Plugin '{self.name}': Loaded successfully.")

    def on_unload(self):
        """Cleanup upon plugin unloading."""
        logger.info(f"Plugin '{self.name}': Unloading...")
        try:
            self._bus.unsubscribe(self.COUNTER_EVENT_PATTERN, self._handle_counter_event)
            logger.debug(f"Plugin '{self.name}': Unsubscribed from events '{self.COUNTER_EVENT_PATTERN}'")
        except Exception as e:
            logger.warning(f"Plugin '{self.name}': Error unsubscribing from events: {e}")
        logger.info(f"Plugin '{self.name}': Unloaded.")

    async def _handle_counter_event(self, event_data: Dict[str, Any]):
        """Asynchronous handler for counter events."""
        value = event_data.get('value', 'N/A')
        message = f"Event: Counter changed to {value}"
        logger.debug(f"Plugin '{self.name}': Received event: {event_data}. Status: '{message}'")
        self.update_status(message, timeout=5000)

    @Slot()
    def _log_current_count(self):
        """Gets the current counter value from the state and outputs it to the log."""
        current_value = self._state.get(self.COUNTER_STATE_KEY, "N/A")
        logger.info(f"Plugin '{self.name}': Current counter value (from state): {current_value}")
        self.update_status(f"Current counter: {current_value}", timeout=3000)
