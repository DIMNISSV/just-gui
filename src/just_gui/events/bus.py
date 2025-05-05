# src/just_gui/events/bus.py
import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any, Dict, List, Coroutine, Union
import fnmatch

logger = logging.getLogger(__name__)

HandlerType = Union[Callable[[Dict[str, Any]], None], Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]]


class EventBus:
    """
    Asynchronous event bus for publishing and subscribing.
    Supports wildcard '*' at the end of subscription topics.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[HandlerType]] = defaultdict(list)
        self._wildcard_subscribers: Dict[str, List[HandlerType]] = defaultdict(list)

    def subscribe(self, topic: str, handler: HandlerType):
        """
        Subscribes a handler to the specified topic.
        The topic can contain '*' at the end for wildcard subscription (e.g., "file.*").
        """
        if topic.endswith('*'):
            pattern = topic[:-1]
            self._wildcard_subscribers[pattern].append(handler)
            logger.debug(f"Wildcard handler {handler.__name__} subscribed to pattern '{pattern}'")
        else:
            self._subscribers[topic].append(handler)
            logger.debug(f"Handler {handler.__name__} subscribed to topic '{topic}'")

    def unsubscribe(self, topic: str, handler: HandlerType):
        """Unsubscribes a handler from a topic."""
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
        Publishes an event asynchronously.
        Notifies all subscribers for the exact topic and matching wildcard topics.
        """
        logger.debug(f"Publishing event on topic '{topic}': {data}")
        handlers_to_call: List[HandlerType] = []

        if topic in self._subscribers:
            handlers_to_call.extend(self._subscribers[topic])

        for pattern, handlers in self._wildcard_subscribers.items():
            if topic.startswith(pattern):
                handlers_to_call.extend(handlers)

        tasks = []
        for handler in handlers_to_call:
            try:
                if asyncio.iscoroutinefunction(handler):
                    task = asyncio.create_task(handler(data))
                    tasks.append(task)
                    logger.debug(f"Scheduled async handler {handler.__name__} for topic '{topic}'")
                else:
                    handler(data)
                    logger.debug(f"Called sync handler {handler.__name__} for topic '{topic}'")
            except Exception as e:
                logger.error(f"Error executing handler {handler.__name__} for topic '{topic}': {e}", exc_info=True)

        if tasks:
            await asyncio.gather(*tasks,
                                 return_exceptions=True)
