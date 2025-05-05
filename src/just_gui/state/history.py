# src/just_gui/state/history.py
import logging
from abc import ABC, abstractmethod
from collections import deque
from contextlib import contextmanager
from typing import Optional, Deque, List, Tuple, Union

logger = logging.getLogger(__name__)


class Command(ABC):
    """Abstract base class for commands supporting undo."""

    def __init__(self, description: str = ""):
        self.description = description

    @abstractmethod
    def execute(self):
        """Executes the command's action."""
        pass

    @abstractmethod
    def undo(self):
        """Undoes the command's action."""
        pass


class HistoryManager:
    """Manages undo/redo command stacks."""

    def __init__(self, max_depth: int = 100):
        self._undo_stack: Deque[Union[Command, List[Command]]] = deque(maxlen=max_depth)
        self._redo_stack: Deque[Union[Command, List[Command]]] = deque(maxlen=max_depth)
        self._group_level = 0
        self._current_group: Optional[List[Command]] = None

    def add_command(self, command: Command):
        """
        Adds an executed command to the history.
        Clears the redo stack.
        """
        if self._group_level > 0 and self._current_group is not None:
            self._current_group.append(command)
            logger.debug(f"Command '{command.description}' added to group")
        else:
            self._add_to_undo(command)

    def _add_to_undo(self, item: Union[Command, List[Command]]):
        """Adds an item (command or group) to the undo stack and clears the redo stack."""
        if not item:
            return
        self._undo_stack.append(item)
        self._redo_stack.clear()
        description = item.description if isinstance(item, Command) else f"Group ({len(item)} commands)"
        logger.debug(f"Added to undo: '{description}'. Redo stack cleared.")

    @contextmanager
    def group(self, description: str = "Grouped action"):
        """Context manager for grouping commands."""
        self._group_level += 1
        if self._group_level == 1:
            self._current_group = []
            logger.debug(f"Starting command group '{description}'")
        try:
            yield
        finally:
            self._group_level -= 1
            if self._group_level == 0 and self._current_group is not None:
                grouped_commands = self._current_group
                self._current_group = None
                logger.debug(f"Ending command group '{description}' with {len(grouped_commands)} commands.")
                self._add_to_undo(grouped_commands)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self):
        """Undoes the last command or group of commands."""
        if not self.can_undo():
            logger.warning("Undo stack is empty.")
            return

        item = self._undo_stack.pop()
        try:
            if isinstance(item, list):
                logger.debug(f"Undoing group of {len(item)} commands.")
                for command in reversed(item):
                    command.undo()
                description = f"Group ({len(item)} commands)"
            else:
                logger.debug(f"Undoing command: '{item.description}'")
                item.undo()
                description = item.description
            self._redo_stack.append(item)
            logger.debug(f"Moved '{description}' to redo stack.")
        except Exception as e:
            logger.error(f"Error during undo operation: {e}", exc_info=True)

    def redo(self):
        """Repeats the last undone command or group."""
        if not self.can_redo():
            logger.warning("Redo stack is empty.")
            return

        item = self._redo_stack.pop()
        try:
            if isinstance(item, list):
                logger.debug(f"Redoing group of {len(item)} commands.")
                for command in item:
                    command.execute()
                description = f"Group ({len(item)} commands)"
            else:
                logger.debug(f"Redoing command: '{item.description}'")
                item.execute()
                description = item.description
            self._undo_stack.append(item)
            logger.debug(f"Moved '{description}' back to undo stack.")
        except Exception as e:
            logger.error(f"Error during redo operation: {e}", exc_info=True)
