# examples/plugins/display_plugin/display_plugin.py
import logging
from typing import Optional
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Slot, Qt

from just_gui import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


# --- Виджет для вкладки ---
class DisplayWidget(QWidget):
    """Виджет, отображающий значение счетчика из состояния."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display_label = QLabel("Ожидание значения счетчика...")
        # Сделаем текст крупнее и по центру для наглядности
        font = self.display_label.font()
        font.setPointSize(24)
        self.display_label.setFont(font)
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addStretch(1)  # Растяжитель сверху
        layout.addWidget(self.display_label, alignment=Qt.AlignmentFlag.AlignCenter)  # Выравнивание метки
        layout.addStretch(1)  # Растяжитель снизу
        self.setLayout(layout)

        self.setMinimumSize(200, 100)  # Минимальный размер

    @Slot(object)  # Принимаем object, т.к. StateManager может вернуть None или другой тип
    def update_value(self, value):
        """Обновляет отображаемое значение."""
        logger.debug(f"DisplayWidget: Получено новое значение {value} из состояния.")
        if value is None:
            self.display_label.setText("Счетчик не инициализирован")
        else:
            # Проверяем, является ли значение числом для отображения
            if isinstance(value, (int, float)):
                self.display_label.setText(f"Текущее значение: {value}")
            else:
                self.display_label.setText(f"Неизвестное значение: {value}")


# --- Класс плагина ---
class DisplayPlugin(BasePlugin):
    """Плагин, который отображает значение счетчика в своей вкладке."""

    COUNTER_STATE_KEY = "counter.value"  # Ключ состояния, за которым следим

    def on_load(self):
        """Инициализация плагина при загрузке."""
        logger.info(f"Плагин '{self.name}': Загрузка...")

        # --- Изменено: Объявляем представление "Отображение" ---
        self.declare_view(
            view_id="display_widget",  # Уникальный ID для этого представления
            name="Отображение",  # Отображаемое имя в меню "Вид"
            factory=self._create_display_widget  # Метод, который создаст виджет
        )

        # Если этому плагину нужно выполнять действия при изменении состояния,
        # не связанные с конкретным виджетом, он может подписаться здесь:
        # self._state.subscribe(self.COUNTER_STATE_KEY, self._handle_state_change_globally)

        # Если плагину нужно слушать события, он может подписаться здесь:
        # self._bus.subscribe("counter.changed", self._handle_counter_changed)

        logger.info(f"Плагин '{self.name}': Загружен.")

    def _create_display_widget(self) -> DisplayWidget:
        """Фабричный метод для создания экземпляра DisplayWidget."""
        logger.debug(
            f"Плагин '{self.name}': Вызвана фабрика _create_display_widget(). Создание экземпляра DisplayWidget...")

        widget = DisplayWidget()

        # Подписываем метод обновления виджета на изменения состояния StateManager
        # Это нужно, чтобы виджет обновлялся, если состояние изменит ДРУГОЙ плагин
        # или действие из меню, или Undo/Redo.
        self._state.subscribe(self.COUNTER_STATE_KEY, widget.update_value)
        logger.debug(f"DisplayWidget подписан на состояние '{self.COUNTER_STATE_KEY}'")

        # Сохраняем колбэк для отписки в свойствах виджета.
        # AppCore вызовет этот колбэк, когда виджет будет удален (вместе с закрытием вкладки).
        widget.setProperty("unsubscribe_callback",
                           lambda: self._state.unsubscribe(self.COUNTER_STATE_KEY, widget.update_value))

        # Первоначальное отображение значения (если оно уже есть в состоянии)
        initial_value = self._state.get(self.COUNTER_STATE_KEY)
        widget.update_value(initial_value)
        logger.debug(f"Плагин '{self.name}': DisplayWidget создан и настроен.")

        return widget

    # TODO: Если плагину нужны глобальные обработчики состояния/событий, реализовать их здесь
    # def _handle_state_change_globally(self, value):
    #     logger.info(f"Плагин '{self.name}': Глобальное изменение состояния счетчика: {value}")

    # async def _handle_counter_changed(self, event_data):
    #     value = event_data.get("value")
    #     logger.info(f"Плагин '{self.name}': Получено событие 'counter.changed' со значением: {value}")

    def on_unload(self):
        """Очистка при выгрузке плагина."""
        logger.info(f"Плагин '{self.name}': Выгрузка...")
        # Важно: Отписка виджетов от состояния происходит в AppCore при их удалении.
        # Здесь нужно отписаться от любых глобальных подписок (на State или EventBus),
        # которые были сделаны в on_load НЕ в привязке к конкретному виджету.
        # Например:
        # self._state.unsubscribe(self.COUNTER_STATE_KEY, self._handle_state_change_globally)
        # self._bus.unsubscribe("counter.changed", self._handle_counter_changed)
        logger.info(f"Плагин '{self.name}': Выгружен.")
