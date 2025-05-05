# examples/plugins/simple_counter/simple_counter.py
import logging
from typing import Optional
import asyncio

from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Slot, Signal
from PySide6.QtGui import QAction

from just_gui import BasePlugin, PluginContext
from just_gui.security.decorators import require_permission

logger = logging.getLogger(__name__)


class CounterWidget(QWidget):
    valueChanged = Signal(int)

    def __init__(self, initial_value=0, step=1, parent=None):
        super().__init__(parent)
        self.current_value = initial_value
        self.step = step
        self.label = QLabel(f"Value: {self.current_value}")
        self.inc_button = QPushButton("+")
        self.dec_button = QPushButton("-")
        layout = QVBoxLayout(self)
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.dec_button)
        h_layout.addWidget(self.inc_button)
        layout.addWidget(self.label)
        layout.addLayout(h_layout)

    @Slot(int)
    def update_display(self, value: int): self.current_value = value; self.label.setText(
        f"Value: {self.current_value}"); self.valueChanged.emit(value)

    def get_value(self) -> int: return self.current_value

    def increment(self): return self.current_value + self.step

    def decrement(self): return self.current_value - self.step


class CounterPlugin(BasePlugin):
    COUNTER_STATE_KEY = "counter.value"

    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.widget_instance: Optional[CounterWidget] = None
        self.initial_value = 0
        self.step = 1

    def on_load(self):
        logger.info(f"Plugin '{self.name}': Loading...")
        config = self.get_config("simple_counter", {})
        self.initial_value = config.get("initial_value", 0)
        self.step = config.get("step", 1)

        self.declare_view(
            view_id="counter_widget",
            name="Counter",
            factory=self._create_counter_widget
        )

        action_inc_10 = QAction(f"Increase by {self.step * 10}", self._app)
        action_inc_10.triggered.connect(self.increment_by_10)
        self.register_menu_action(f"Tools/{self.name}", action_inc_10)

        action_reset = QAction("Reset Counter", self._app)
        action_reset.triggered.connect(self.reset_counter)
        self.register_menu_action(f"Tools/{self.name}", action_reset)

        current_state_value = self._state.get(self.COUNTER_STATE_KEY)
        if current_state_value is None:
            logger.debug(f"Initializing state '{self.COUNTER_STATE_KEY}' with value {self.initial_value}")
            self._state.set(self.COUNTER_STATE_KEY, self.initial_value, description="Initial counter value")
        else:
            self.initial_value = current_state_value
            logger.debug(f"State '{self.COUNTER_STATE_KEY}' already contains value: {self.initial_value}")

        logger.info(f"Plugin '{self.name}': Loaded.")

    def _create_counter_widget(self) -> CounterWidget:
        logger.debug(f"Plugin '{self.name}': Creating CounterWidget instance...")
        current_value = self._state.get(self.COUNTER_STATE_KEY, self.initial_value)
        widget = CounterWidget(initial_value=current_value, step=self.step)
        self.widget_instance = widget

        widget.inc_button.clicked.connect(self.increment_value)
        widget.dec_button.clicked.connect(self.decrement_value)

        self._state.subscribe(self.COUNTER_STATE_KEY, widget.update_display)
        logger.debug(f"CounterWidget subscribed to state '{self.COUNTER_STATE_KEY}'")
        widget.setProperty("unsubscribe_callback",
                           lambda: self._state.unsubscribe(self.COUNTER_STATE_KEY, widget.update_display))

        return widget

    @Slot()
    @require_permission("state", "write")
    def increment_value(self):
        if self.widget_instance:
            new_value = self.widget_instance.increment()
            logger.debug(f"Increment: new value = {new_value}")
            with self._state.history.group("Increment counter"):
                self._state.set(self.COUNTER_STATE_KEY, new_value)
                asyncio.create_task(self._bus.publish("counter.changed", {"value": new_value, "change": "increment"}))
        else:
            logger.warning("Attempted increment, but widget not created.")

    @Slot()
    @require_permission("state", "write")
    def decrement_value(self):
        if self.widget_instance:
            new_value = self.widget_instance.decrement()
            logger.debug(f"Decrement: new value = {new_value}")
            with self._state.history.group("Decrement counter"):
                self._state.set(self.COUNTER_STATE_KEY, new_value)
                asyncio.create_task(self._bus.publish("counter.changed", {"value": new_value, "change": "decrement"}))
        else:
            logger.warning("Attempted decrement, but widget not created.")

    @Slot()
    def increment_by_10(self):
        """Increases the counter by 10 * step."""
        current_value = self._state.get(self.COUNTER_STATE_KEY, self.initial_value)
        new_value = current_value + (self.step * 10)
        logger.debug(f"Increment by {self.step * 10}: new value = {new_value}")
        with self._state.history.group(f"Increase by {self.step * 10}"):
            self._state.set(self.COUNTER_STATE_KEY, new_value)
            asyncio.create_task(self._bus.publish("counter.changed", {"value": new_value, "change": "increment_10"}))

    @Slot()
    def reset_counter(self):
        """Drops the counter to the initial value."""
        logger.debug(f"Resetting counter to {self.initial_value}")
        with self._state.history.group("Reset counter"):
            self._state.set(self.COUNTER_STATE_KEY, self.initial_value)
            asyncio.create_task(self._bus.publish("counter.changed", {"value": self.initial_value, "change": "reset"}))

    def on_unload(self):
        logger.info(f"Plugin '{self.name}': Unloading...")
        self.widget_instance = None
        logger.info(f"Plugin '{self.name}': Unloaded.")
