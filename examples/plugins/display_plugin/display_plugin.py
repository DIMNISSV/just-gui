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
        layout.addWidget(self.display_label)
        self.setLayout(layout)

    @Slot(object)  # Принимаем int или None
    def update_value(self, value):
        """Обновляет отображаемое значение."""
        logger.debug(f"DisplayWidget: Получено новое значение {value}")
        if value is None:
            self.display_label.setText("Счетчик не инициализирован")
        else:
            self.display_label.setText(f"Текущее значение: {value}")


# --- Класс плагина ---
class DisplayPlugin(BasePlugin):
    """Плагин, который отображает значение счетчика в своей вкладке."""

    COUNTER_STATE_KEY = "counter.value"  # Ключ состояния, за которым следим

    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.widget: Optional[DisplayWidget] = None

    def on_load(self):
        """Инициализация плагина при загрузке."""
        logger.info(f"Плагин '{self.name}': Загрузка...")

        # Создаем виджет
        self.widget = DisplayWidget()

        # Подписываем метод обновления виджета на изменения состояния счетчика
        self._state.subscribe(self.COUNTER_STATE_KEY, self.widget.update_value)
        logger.debug(f"Плагин '{self.name}': Виджет подписан на состояние '{self.COUNTER_STATE_KEY}'")

        # Регистрируем вкладку
        self.register_tab("Отображение", self.widget)

        # Первоначальное отображение значения (если оно уже есть в состоянии)
        initial_value = self._state.get(self.COUNTER_STATE_KEY)
        self.widget.update_value(initial_value)

        logger.info(f"Плагин '{self.name}': Загружен успешно.")

    def on_unload(self):
        """Очистка при выгрузке плагина."""
        logger.info(f"Плагин '{self.name}': Выгрузка...")
        if self.widget:
            # Отписываемся от состояния
            try:
                self._state.unsubscribe(self.COUNTER_STATE_KEY, self.widget.update_value)
                logger.debug(f"Плагин '{self.name}': Виджет отписан от состояния '{self.COUNTER_STATE_KEY}'")
            except Exception as e:
                logger.warning(f"Плагин '{self.name}': Ошибка при отписке виджета от состояния: {e}")
        self.widget = None
        logger.info(f"Плагин '{self.name}': Выгружен.")
