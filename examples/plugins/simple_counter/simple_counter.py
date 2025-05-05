# examples/plugins/simple_counter/simple_counter.py
import logging
from typing import Optional
import asyncio  # Added for event bus

from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Slot, Signal
# --- ИЗМЕНЕНО: Импортируем QAction ---
from PySide6.QtGui import QAction

from just_gui import BasePlugin, PluginContext
from just_gui.security.decorators import require_permission

logger = logging.getLogger(__name__)


# --- Виджет (без изменений) ---
class CounterWidget(QWidget):
    valueChanged = Signal(int)

    def __init__(self, initial_value=0, step=1, parent=None):
        super().__init__(parent)
        self.current_value = initial_value
        self.step = step
        self.label = QLabel(f"Значение: {self.current_value}")
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
        f"Значение: {self.current_value}"); self.valueChanged.emit(value)

    def get_value(self) -> int: return self.current_value

    def increment(self): return self.current_value + self.step

    def decrement(self): return self.current_value - self.step


# --- Плагин ---
class CounterPlugin(BasePlugin):
    COUNTER_STATE_KEY = "counter.value"

    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.widget_instance: Optional[CounterWidget] = None
        self.initial_value = 0
        self.step = 1

    def on_load(self):
        logger.info(f"Плагин '{self.name}': Загрузка...")
        config = self.get_config("simple_counter", {})  # Используем get_config
        self.initial_value = config.get("initial_value", 0)
        self.step = config.get("step", 1)

        self.declare_view(
            view_id="counter_widget",
            name="Счетчик",
            factory=self._create_counter_widget
        )

        # Добавляем действия в меню
        # --- ИЗМЕНЕНО: Родитель QAction теперь self._app ---
        action_inc_10 = QAction(f"Увеличить на {self.step * 10}", self._app)
        action_inc_10.triggered.connect(self.increment_by_10)
        # Добавляем в подменю плагина
        self.register_menu_action(f"Инструменты/{self.name}", action_inc_10)

        action_reset = QAction("Сбросить счетчик", self._app)
        action_reset.triggered.connect(self.reset_counter)
        self.register_menu_action(f"Инструменты/{self.name}", action_reset)
        # --- КОНЕЦ ИЗМЕНЕНИЙ В РОДИТЕЛЕ ---

        # Инициализация состояния
        current_state_value = self._state.get(self.COUNTER_STATE_KEY)
        if current_state_value is None:
            logger.debug(f"Инициализация состояния '{self.COUNTER_STATE_KEY}' значением {self.initial_value}")
            self._state.set(self.COUNTER_STATE_KEY, self.initial_value, description="Начальное значение счетчика")
        else:
            self.initial_value = current_state_value
            logger.debug(f"Состояние '{self.COUNTER_STATE_KEY}' уже содержит значение: {self.initial_value}")

        logger.info(f"Плагин '{self.name}': Загружен.")

    def _create_counter_widget(self) -> CounterWidget:
        logger.debug(f"Плагин '{self.name}': Создание экземпляра CounterWidget...")
        current_value = self._state.get(self.COUNTER_STATE_KEY, self.initial_value)
        widget = CounterWidget(initial_value=current_value, step=self.step)
        # Слабая ссылка или просто ссылка? Пока оставляем прямую для простоты.
        self.widget_instance = widget

        widget.inc_button.clicked.connect(self.increment_value)
        widget.dec_button.clicked.connect(self.decrement_value)

        # Подписка виджета на состояние
        self._state.subscribe(self.COUNTER_STATE_KEY, widget.update_display)
        logger.debug(f"CounterWidget подписан на состояние '{self.COUNTER_STATE_KEY}'")
        # Сохраняем колбэк отписки
        widget.setProperty("unsubscribe_callback",
                           lambda: self._state.unsubscribe(self.COUNTER_STATE_KEY, widget.update_display))

        return widget

    @Slot()
    @require_permission("state", "write")
    def increment_value(self):
        if self.widget_instance:
            new_value = self.widget_instance.increment()
            logger.debug(f"Инкремент: новое значение = {new_value}")
            with self._state.history.group("Инкремент счетчика"):
                self._state.set(self.COUNTER_STATE_KEY, new_value)
                asyncio.create_task(self._bus.publish("counter.changed", {"value": new_value, "change": "increment"}))
        else:
            logger.warning("Попытка инкремента, но виджет не создан.")

    @Slot()
    @require_permission("state", "write")
    def decrement_value(self):
        if self.widget_instance:
            new_value = self.widget_instance.decrement()
            logger.debug(f"Декремент: новое значение = {new_value}")
            with self._state.history.group("Декремент счетчика"):
                self._state.set(self.COUNTER_STATE_KEY, new_value)
                asyncio.create_task(self._bus.publish("counter.changed", {"value": new_value, "change": "decrement"}))
        else:
            logger.warning("Попытка декремента, но виджет не создан.")

    # --- Новые слоты для действий меню ---
    @Slot()
    def increment_by_10(self):
        """Увеличивает счетчик на 10 * шаг."""
        current_value = self._state.get(self.COUNTER_STATE_KEY, self.initial_value)
        new_value = current_value + (self.step * 10)
        logger.debug(f"Инкремент на {self.step * 10}: новое значение = {new_value}")
        with self._state.history.group(f"Увеличить на {self.step * 10}"):
            self._state.set(self.COUNTER_STATE_KEY, new_value)
            asyncio.create_task(self._bus.publish("counter.changed", {"value": new_value, "change": "increment_10"}))

    @Slot()
    def reset_counter(self):
        """Сбрасывает счетчик к начальному значению."""
        logger.debug(f"Сброс счетчика к {self.initial_value}")
        with self._state.history.group("Сброс счетчика"):
            self._state.set(self.COUNTER_STATE_KEY, self.initial_value)
            asyncio.create_task(self._bus.publish("counter.changed", {"value": self.initial_value, "change": "reset"}))

    # --- Конец новых слотов ---

    def on_unload(self):
        logger.info(f"Плагин '{self.name}': Выгрузка...")
        # Отписка происходит при закрытии вкладки/виджета
        self.widget_instance = None
        logger.info(f"Плагин '{self.name}': Выгружен.")
