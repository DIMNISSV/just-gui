# src/just_gui/security/sandbox.py
import logging
from types import TracebackType
from typing import Optional, Type

logger = logging.getLogger(__name__)


# ЗАГЛУШКА: Реальная изоляция пока отсутствует
class Sandbox:
    """
    Контекстный менеджер для запуска кода в ограниченном окружении.
    ПОКА ЯВЛЯЕТСЯ ЗАГЛУШКОЙ - НЕ ПРЕДОСТАВЛЯЕТ РЕАЛЬНОЙ ИЗОЛЯЦИИ.

    Режимы в будущем:
        - 'soft': Подмена модулей sys.modules.
        - 'hard_process': Запуск в отдельном процессе (multiprocessing).
        - 'hard_docker': Запуск в Docker контейнере.
    """

    def __init__(self, plugin_name: str, mode: str = 'soft'):
        """
        Args:
            plugin_name: Имя плагина для логирования.
            mode: Режим изоляции (пока не используется).
        """
        self.plugin_name = plugin_name
        self.mode = mode
        logger.warning(
            f"[SECURITY STUB] Песочница для плагина '{plugin_name}' в режиме '{mode}' активирована, но реальная изоляция ОТСУТСТВУЕТ.")

    def __enter__(self):
        """Вход в контекст песочницы."""
        # --- НАЧАЛО ЗАГЛУШКИ ---
        # В реальной реализации здесь будет:
        # - Сохранение текущего состояния (например, sys.modules).
        # - Применение ограничений (подмена модулей, настройка chroot/seccomp, запуск процесса/контейнера).
        logger.debug(f"[SECURITY STUB] Вход в песочницу для '{self.plugin_name}'")
        # --- КОНЕЦ ЗАГЛУШКИ ---
        return self  # Возвращаем сам объект песочницы, если нужно

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        """Выход из контекста песочницы."""
        # --- НАЧАЛО ЗАГЛУШКИ ---
        # В реальной реализации здесь будет:
        # - Восстановление исходного состояния.
        # - Остановка процесса/контейнера.
        # - Обработка исключений, возникших внутри песочницы.
        logger.debug(f"[SECURITY STUB] Выход из песочницы для '{self.plugin_name}'")
        # --- КОНЕЦ ЗАГЛУШКИ ---
        # Если возвращаем True, исключение будет подавлено. Пока не подавляем.
        return False
