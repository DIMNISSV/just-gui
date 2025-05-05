# examples/plugins/event_listener/listener.py

import logging
import asyncio
from typing import Dict, Any
from PySide6.QtGui import QAction, QIcon  # Используем стандартные иконки
from PySide6.QtCore import Slot

from just_gui import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


class ListenerPlugin(BasePlugin):
    """Плагин, который слушает события счетчика и показывает их в статусе,
       а также позволяет вывести текущее значение в лог по кнопке."""

    COUNTER_STATE_KEY = "counter.value"  # Ключ состояния счетчика
    COUNTER_EVENT_PATTERN = "counter.*"  # Паттерн для подписки на события счетчика

    def on_load(self):
        """Инициализация плагина при загрузке."""
        logger.info(f"Плагин '{self.name}': Загрузка...")

        # Подписываемся на события счетчика
        # Обработчик должен быть async, т.к. EventBus.publish - async
        self._bus.subscribe(self.COUNTER_EVENT_PATTERN, self._handle_counter_event)
        logger.debug(f"Плагин '{self.name}': Подписан на события '{self.COUNTER_EVENT_PATTERN}'")

        # Регистрируем кнопку на тулбаре
        log_action = QAction(QIcon.fromTheme("document-print-preview"), "Лог счетчика", self._app)  # Используем QIcon
        log_action.setStatusTip("Вывести текущее значение счетчика в лог")
        log_action.triggered.connect(self._log_current_count)
        self.register_toolbar_widget(log_action, section="Info")  # Указываем секцию

        logger.info(f"Плагин '{self.name}': Загружен успешно.")

    def on_unload(self):
        """Очистка при выгрузке плагина."""
        logger.info(f"Плагин '{self.name}': Выгрузка...")
        # Отписываемся от событий
        try:
            self._bus.unsubscribe(self.COUNTER_EVENT_PATTERN, self._handle_counter_event)
            logger.debug(f"Плагин '{self.name}': Отписан от событий '{self.COUNTER_EVENT_PATTERN}'")
        except Exception as e:
            logger.warning(f"Плагин '{self.name}': Ошибка при отписке от событий: {e}")
        logger.info(f"Плагин '{self.name}': Выгружен.")

    async def _handle_counter_event(self, event_data: Dict[str, Any]):
        """Асинхронный обработчик событий от счетчика."""
        value = event_data.get('value', 'N/A')
        message = f"Событие: Счетчик изменен на {value}"
        logger.debug(f"Плагин '{self.name}': Получено событие: {event_data}. Статус: '{message}'")
        # Обновляем статус-бар
        self.update_status(message, timeout=5000)  # Показываем на 5 секунд

    @Slot()  # Помечаем как слот
    def _log_current_count(self):
        """Получает текущее значение счетчика из состояния и выводит в лог."""
        current_value = self._state.get(self.COUNTER_STATE_KEY, "N/A")
        logger.info(f"Плагин '{self.name}': Текущее значение счетчика (из состояния): {current_value}")
        # Можно также вывести в статус
        self.update_status(f"Текущий счетчик: {current_value}", timeout=3000)
