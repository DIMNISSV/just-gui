# src/just_gui/events/bus.py
import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any, Dict, List, Coroutine, Union
import fnmatch  # Для поддержки wildcard '*'

logger = logging.getLogger(__name__)

# Типы обработчиков: синхронная функция или корутина
HandlerType = Union[Callable[[Dict[str, Any]], None], Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]]


class EventBus:
    """
    Асинхронная шина событий для публикации и подписки.
    Поддерживает wildcard '*' в конце топиков подписки.
    """

    def __init__(self):
        # Словарь для хранения подписчиков: topic -> list[handler]
        self._subscribers: Dict[str, List[HandlerType]] = defaultdict(list)
        # Словарь для wildcard подписчиков: pattern -> list[handler]
        self._wildcard_subscribers: Dict[str, List[HandlerType]] = defaultdict(list)

    def subscribe(self, topic: str, handler: HandlerType):
        """
        Подписывает обработчик на указанный топик.
        Топик может содержать '*' в конце для wildcard подписки (e.g., "file.*").
        """
        if topic.endswith('*'):
            pattern = topic[:-1]  # Убираем '*' для fnmatch
            self._wildcard_subscribers[pattern].append(handler)
            logger.debug(f"Wildcard handler {handler.__name__} subscribed to pattern '{pattern}'")
        else:
            self._subscribers[topic].append(handler)
            logger.debug(f"Handler {handler.__name__} subscribed to topic '{topic}'")

    def unsubscribe(self, topic: str, handler: HandlerType):
        """Отписывает обработчик от топика."""
        if topic.endswith('*'):
            pattern = topic[:-1]
            if pattern in self._wildcard_subscribers:
                try:
                    self._wildcard_subscribers[pattern].remove(handler)
                    logger.debug(f"Wildcard handler {handler.__name__} unsubscribed from pattern '{pattern}'")
                    if not self._wildcard_subscribers[pattern]:
                        del self._wildcard_subscribers[pattern]
                except ValueError:
                    logger.warning(f"Handler {handler.__name__} not found for pattern '{pattern}'")
        else:
            if topic in self._subscribers:
                try:
                    self._subscribers[topic].remove(handler)
                    logger.debug(f"Handler {handler.__name__} unsubscribed from topic '{topic}'")
                    if not self._subscribers[topic]:
                        del self._subscribers[topic]
                except ValueError:
                    logger.warning(f"Handler {handler.__name__} not found for topic '{topic}'")

    async def publish(self, topic: str, data: Dict[str, Any]):
        """
        Публикует событие асинхронно.
        Уведомляет всех подписчиков на точный топик и совпадающие wildcard топики.
        """
        logger.debug(f"Publishing event on topic '{topic}': {data}")
        handlers_to_call: List[HandlerType] = []

        # Точные совпадения
        if topic in self._subscribers:
            handlers_to_call.extend(self._subscribers[topic])

        # Wildcard совпадения
        for pattern, handlers in self._wildcard_subscribers.items():
            # Используем fnmatch для базового wildcard (*) - сравниваем начало строки
            if topic.startswith(pattern):
                handlers_to_call.extend(handlers)

        # Вызов обработчиков
        tasks = []
        for handler in handlers_to_call:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Запускаем корутину как задачу asyncio
                    task = asyncio.create_task(handler(data))
                    tasks.append(task)
                    logger.debug(f"Scheduled async handler {handler.__name__} for topic '{topic}'")
                else:
                    # Вызываем синхронный обработчик немедленно
                    handler(data)
                    logger.debug(f"Called sync handler {handler.__name__} for topic '{topic}'")
            except Exception as e:
                logger.error(f"Error executing handler {handler.__name__} for topic '{topic}': {e}", exc_info=True)

        # Ожидаем завершения всех асинхронных задач
        if tasks:
            await asyncio.gather(*tasks,
                                 return_exceptions=True)  # return_exceptions чтобы не упасть при ошибке в одном хендлере
