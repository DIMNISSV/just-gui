# src/just_gui/security/sandbox.py
import logging
from types import TracebackType
from typing import Optional, Type

logger = logging.getLogger(__name__)


class Sandbox:
    """
    Context manager for running code in a limited environment.
    Currently a STUB - does NOT provide real isolation.

    Future modes:
        - 'soft': sys.modules substitution.
        - 'hard_process': Running in a separate process (multiprocessing).
        - 'hard_docker': Running in a Docker container.
    """

    def __init__(self, plugin_name: str, mode: str = 'soft'):
        """
        Args:
            plugin_name: The plugin name for logging.
            mode: The isolation mode (not used yet).
        """
        self.plugin_name = plugin_name
        self.mode = mode
        logger.warning(
            f"[SECURITY STUB] Sandbox for plugin '{plugin_name}' in mode '{mode}' activated, but real isolation is ABSENT.")

    def __enter__(self):
        """Entry into the sandbox context."""
        logger.debug(f"[SECURITY STUB] Entering sandbox for '{self.plugin_name}'")
        return self

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        """Exiting the sandbox context."""
        logger.debug(f"[SECURITY STUB] Exiting sandbox for '{self.plugin_name}'")
        return False
