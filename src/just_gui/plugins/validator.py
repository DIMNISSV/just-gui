# src/just_gui/plugins/validator.py
import ast
import logging
from typing import List, Set, Tuple, Dict

logger = logging.getLogger(__name__)

# ЗАГЛУШКА: Список пока простой, без детальной конфигурации
DEFAULT_DANGEROUS_MODULES: Set[str] = {
    "os",
    "subprocess",
    # "socket", # Разрешать или нет? Зависит от разрешений
    "ctypes",
    "sys",  # Импорт sys сам по себе не опасен, но доступ к __dict__ и т.д. - да
    "_thread",  # Прямое использование потоков может быть рискованным
}

# ЗАГЛУШКА: Проверка вызовов пока не реализована
DEFAULT_DANGEROUS_CALLS: Dict[str, Set[str]] = {
    "os": {"system", "execv", "execl", "spawn", "remove", "unlink", "rmdir"},
    "subprocess": {"run", "call", "check_call", "check_output", "Popen"},
    "builtins": {"eval", "exec"},  # Встроенные функции
    "shutil": {"rmtree"},
}


class PluginValidationError(Exception):
    """Ошибка валидации кода плагина."""
    pass


class AstValidator(ast.NodeVisitor):
    """
    Посетитель AST для поиска потенциально опасных конструкций.
    ПОКА РЕАЛИЗОВАНО ТОЛЬКО ОБНАРУЖЕНИЕ ИМПОРТА ЗАПРЕЩЕННЫХ МОДУЛЕЙ.
    """

    def __init__(self, dangerous_modules: Set[str] = DEFAULT_DANGEROUS_MODULES):
        self.dangerous_modules = dangerous_modules
        self.errors: List[Tuple[int, int, str]] = []  # (lineno, col, message)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in self.dangerous_modules:
                msg = f"Импорт запрещенного модуля: '{alias.name}'"
                self.errors.append((node.lineno, node.col_offset, msg))
                logger.warning(f"[SECURITY STUB] {msg} в строке {node.lineno}")
        self.generic_visit(node)  # Продолжаем обход

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module in self.dangerous_modules:
            msg = f"Импорт из запрещенного модуля: '{node.module}'"
            self.errors.append((node.lineno, node.col_offset, msg))
            logger.warning(f"[SECURITY STUB] {msg} в строке {node.lineno}")
        # TODO: Проверять импорт конкретных опасных имен из разрешенных модулей
        self.generic_visit(node)

    # TODO: Реализовать visit_Call для поиска опасных вызовов (DEFAULT_DANGEROUS_CALLS)
    # Это сложнее, нужно отслеживать, откуда пришла функция (импорты, псевдонимы)


def validate_plugin_ast(code_string: str) -> bool:
    """
    Выполняет статическую проверку AST кода плагина на базовые опасные конструкции.
    ПОКА ПРОВЕРЯЕТ ТОЛЬКО ИМПОРТЫ.

    Args:
        code_string: Исходный код плагина в виде строки.

    Returns:
        True, если проверка пройдена (опасные конструкции не найдены), False иначе.

    Raises:
        SyntaxError: Если код невалиден и не может быть распарсен.
    """
    logger.info("[SECURITY STUB] Запуск базовой AST валидации...")
    try:
        tree = ast.parse(code_string)
        validator = AstValidator()
        validator.visit(tree)

        if validator.errors:
            logger.error("[SECURITY STUB] AST валидация провалена. Найдены проблемы:")
            for lineno, col, msg in validator.errors:
                logger.error(f"  - Строка {lineno}, позиция {col}: {msg}")
            return False  # Валидация не пройдена
        else:
            logger.info("[SECURITY STUB] Базовая AST валидация пройдена успешно.")
            return True  # Валидация пройдена

    except SyntaxError as e:
        logger.error(f"Синтаксическая ошибка при AST валидации: {e}", exc_info=True)
        raise  # Перевыбрасываем ошибку синтаксиса
