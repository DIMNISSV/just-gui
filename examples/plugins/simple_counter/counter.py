# examples/plugins/simple_counter/counter.py

import logging
import asyncio  # Для публикации событий
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal, Slot  # Добавляем Signal и Slot

from just_gui import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


# --- Виджет для вкладки ---
class CounterWidget(QWidget):
    """Простой виджет для отображения и изменения счетчика."""
    # Сигналы для уведомления плагина о действиях пользователя
    increment_requested = Signal()
    decrement_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count_label = QLabel("Начальное значение")
        self.increment_button = QPushButton("+")
        self.decrement_button = QPushButton("-")

        # Подключение кнопок к сигналам виджета
        self.increment_button.clicked.connect(self.increment_requested)
        self.decrement_button.clicked.connect(self.decrement_requested)

        layout = QVBoxLayout(self)
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.decrement_button)
        h_layout.addWidget(self.count_label)
        h_layout.addWidget(self.increment_button)
        layout.addLayout(h_layout)
        # Можно добавить сюда еще что-нибудь

    # Слот для обновления отображаемого значения извне (из StateManager)
    @Slot(object)  # Используем object, т.к. значение может быть None или int
    def update_display(self, value):
        """Обновляет текст метки счетчика."""
        logger.debug(f"CounterWidget: Обновление отображения на {value}")
        if value is None:
            self.count_label.setText("N/A")
        else:
            self.count_label.setText(f"Счетчик: {value}")


# --- Класс плагина ---
class CounterPlugin(BasePlugin):
    """Плагин, управляющий простым счетчиком."""

    STATE_KEY = "counter.value"  # Ключ для хранения значения в StateManager
    EVENT_TOPIC = "counter.changed"  # Топик для событий изменения

    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.widget: Optional[CounterWidget] = None
        self.step: int = 1  # Значение шага по умолчанию

    def on_load(self):
        """Инициализация плагина при загрузке."""
        logger.info(f"Плагин '{self.name}': Загрузка...")

        # Получаем конфигурацию
        initial_value = self.get_config("initial_value", 0)
        self.step = self.get_config("step", 1)
        logger.info(f"Плагин '{self.name}': Начальное значение={initial_value}, Шаг={self.step}")

        # Инициализируем состояние, если его еще нет
        current_value = self._state.get(self.STATE_KEY)
        if current_value is None:
            logger.debug(
                f"Плагин '{self.name}': Установка начального значения состояния '{self.STATE_KEY}' = {initial_value}")
            # Устанавливаем без записи в историю для начального значения
            self._state._set_value(self.STATE_KEY, initial_value, record_history=False)
            # Альтернатива: self._state.set(self.STATE_KEY, initial_value, description="Initialize counter")

        # Создаем виджет
        self.widget = CounterWidget()

        # Подключаем сигналы виджета к методам плагина
        self.widget.increment_requested.connect(self._increment_state)
        self.widget.decrement_requested.connect(self._decrement_state)

        # Подписываем метод обновления виджета на изменения состояния
        # Важно: передаем именно метод экземпляра self.widget
        self._state.subscribe(self.STATE_KEY, self.widget.update_display)
        logger.debug(f"Плагин '{self.name}': Виджет подписан на состояние '{self.STATE_KEY}'")

        # Регистрируем вкладку
        self.register_tab("Счетчик", self.widget)

        # Регистрируем действие в меню
        reset_action = QAction("Сбросить счетчик", self._app)  # self._app - родитель QMainWindow
        reset_action.triggered.connect(self._reset_state)
        self.register_menu_action("Инструменты/Счетчик", reset_action)

        # Первоначальное отображение значения в виджете
        # Получаем текущее значение из состояния и обновляем виджет
        initial_display_value = self._state.get(self.STATE_KEY)
        self.widget.update_display(initial_display_value)

        logger.info(f"Плагин '{self.name}': Загружен успешно.")

    def on_unload(self):
        """Очистка при выгрузке плагина."""
        logger.info(f"Плагин '{self.name}': Выгрузка...")
        if self.widget:
            # Отписываем виджет от состояния
            try:
                self._state.unsubscribe(self.STATE_KEY, self.widget.update_display)
                logger.debug(f"Плагин '{self.name}': Виджет отписан от состояния '{self.STATE_KEY}'")
            except Exception as e:
                logger.warning(f"Плагин '{self.name}': Ошибка при отписке виджета от состояния: {e}")
        # Удаление вкладок, меню, тулбаров обычно происходит автоматически при закрытии
        # главного окна или при явном удалении через API (если он будет)
        self.widget = None  # Помочь сборщику мусора
        logger.info(f"Плагин '{self.name}': Выгружен.")

    @Slot()  # Помечаем как слот
    def _increment_state(self):
        """Увеличивает значение счетчика в состоянии."""
        current_value = self._state.get(self.STATE_KEY, 0)  # Получаем текущее или 0
        new_value = current_value + self.step
        logger.debug(f"Плагин '{self.name}': Запрос на инкремент. Новое значение = {new_value}")
        # Используем 'set' для записи в историю
        self._state.set(self.STATE_KEY, new_value, description=f"Increment counter by {self.step}")
        # Публикуем событие асинхронно
        asyncio.create_task(self._publish_change_event(new_value))

    @Slot()  # Помечаем как слот
    def _decrement_state(self):
        """Уменьшает значение счетчика в состоянии."""
        current_value = self._state.get(self.STATE_KEY, 0)
        new_value = current_value - self.step
        logger.debug(f"Плагин '{self.name}': Запрос на декремент. Новое значение = {new_value}")
        self._state.set(self.STATE_KEY, new_value, description=f"Decrement counter by {self.step}")
        # Публикуем событие асинхронно
        asyncio.create_task(self._publish_change_event(new_value))

    @Slot()  # Помечаем как слот
    def _reset_state(self):
        """Сбрасывает счетчик к начальному значению из конфигурации."""
        initial_value = self.get_config("initial_value", 0)
        logger.debug(f"Плагин '{self.name}': Запрос на сброс. Новое значение = {initial_value}")
        self._state.set(self.STATE_KEY, initial_value, description="Reset counter")
        # Публикуем событие асинхронно
        asyncio.create_task(self._publish_change_event(initial_value))

    async def _publish_change_event(self, value):
        """Асинхронно публикует событие об изменении счетчика."""
        event_data = {"value": value}
        logger.debug(f"Плагин '{self.name}': Публикация события '{self.EVENT_TOPIC}' с данными {event_data}")
        await self._bus.publish(self.EVENT_TOPIC, event_data)
