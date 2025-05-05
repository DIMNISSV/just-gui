# src/just_gui/state/history.py
import logging
from abc import ABC, abstractmethod
from collections import deque
from contextlib import contextmanager
from typing import Optional, Deque, List, Tuple, Union

logger = logging.getLogger(__name__)


class Command(ABC):
    """Абстрактный базовый класс для команд, поддерживающих отмену."""

    def __init__(self, description: str = ""):
        self.description = description  # Описание для UI или логов

    @abstractmethod
    def execute(self):
        """Выполняет действие команды."""
        pass

    @abstractmethod
    def undo(self):
        """Отменяет действие команды."""
        pass


class HistoryManager:
    """Управляет стеками undo/redo команд."""

    def __init__(self, max_depth: int = 100):
        self._undo_stack: Deque[Union[Command, List[Command]]] = deque(maxlen=max_depth)
        self._redo_stack: Deque[Union[Command, List[Command]]] = deque(maxlen=max_depth)
        self._group_level = 0
        self._current_group: Optional[List[Command]] = None
        # TODO: Добавить поддержку контекстных стеков

    def add_command(self, command: Command):
        """
        Добавляет выполненную команду в историю.
        Очищает стек redo.
        """
        if self._group_level > 0 and self._current_group is not None:
            self._current_group.append(command)
            logger.debug(f"Command '{command.description}' added to group")
        else:
            self._add_to_undo(command)

    def _add_to_undo(self, item: Union[Command, List[Command]]):
        """Добавляет элемент (команду или группу) в стек undo и очищает redo."""
        if not item:  # Не добавлять пустые группы
            return
        self._undo_stack.append(item)
        self._redo_stack.clear()
        description = item.description if isinstance(item, Command) else f"Group ({len(item)} commands)"
        logger.debug(f"Added to undo: '{description}'. Redo stack cleared.")
        # TODO: Сигнал об изменении состояния истории для UI (enable/disable undo/redo buttons)

    @contextmanager
    def group(self, description: str = "Grouped action"):
        """Контекстный менеджер для группировки команд."""
        self._group_level += 1
        if self._group_level == 1:  # Начало внешней группы
            self._current_group = []
            logger.debug(f"Starting command group '{description}'")
        try:
            yield
        finally:
            self._group_level -= 1
            if self._group_level == 0 and self._current_group is not None:  # Конец внешней группы
                # Добавляем группу как единое целое в undo стек
                grouped_commands = self._current_group
                self._current_group = None
                logger.debug(f"Ending command group '{description}' with {len(grouped_commands)} commands.")
                self._add_to_undo(grouped_commands)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self):
        """Отменяет последнюю команду или группу команд."""
        if not self.can_undo():
            logger.warning("Undo stack is empty.")
            return

        item = self._undo_stack.pop()
        try:
            if isinstance(item, list):  # Группа команд
                logger.debug(f"Undoing group of {len(item)} commands.")
                # Отменяем в обратном порядке
                for command in reversed(item):
                    command.undo()
                description = f"Group ({len(item)} commands)"
            else:  # Одиночная команда
                logger.debug(f"Undoing command: '{item.description}'")
                item.undo()
                description = item.description
            self._redo_stack.append(item)
            logger.debug(f"Moved '{description}' to redo stack.")
            # TODO: Сигнал об изменении состояния истории
        except Exception as e:
            logger.error(f"Error during undo operation: {e}", exc_info=True)
            # Попытка вернуть команду обратно в undo стек в случае ошибки? Спорно.
            # self._undo_stack.append(item)

    def redo(self):
        """Повторяет последнюю отмененную команду или группу."""
        if not self.can_redo():
            logger.warning("Redo stack is empty.")
            return

        item = self._redo_stack.pop()
        try:
            if isinstance(item, list):  # Группа команд
                logger.debug(f"Redoing group of {len(item)} commands.")
                # Выполняем в прямом порядке
                for command in item:
                    command.execute()
                description = f"Group ({len(item)} commands)"
            else:  # Одиночная команда
                logger.debug(f"Redoing command: '{item.description}'")
                item.execute()
                description = item.description
            self._undo_stack.append(item)  # Перемещаем обратно в undo стек
            logger.debug(f"Moved '{description}' back to undo stack.")
            # TODO: Сигнал об изменении состояния истории
        except Exception as e:
            logger.error(f"Error during redo operation: {e}", exc_info=True)
            # Попытка вернуть команду обратно в redo стек?
            # self._redo_stack.append(item)
