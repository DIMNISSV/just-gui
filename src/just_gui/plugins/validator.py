# src/just_gui/plugins/validator.py
import ast
import logging
from typing import List, Set, Tuple, Dict

logger = logging.getLogger(__name__)

DEFAULT_DANGEROUS_MODULES: Set[str] = {
    "os",
    "subprocess",
    "ctypes",
    "sys",
    "_thread",
}

DEFAULT_DANGEROUS_CALLS: Dict[str, Set[str]] = {
    "os": {"system", "execv", "execl", "spawn", "remove", "unlink", "rmdir"},
    "subprocess": {"run", "call", "check_call", "check_output", "Popen"},
    "builtins": {"eval", "exec"},
    "shutil": {"rmtree"},
}


class PluginValidationError(Exception):
    """Plugin code validation error."""
    pass


class AstValidator(ast.NodeVisitor):
    """
    AST visitor to find potentially dangerous constructs.
    CURRENTLY ONLY DETECTS IMPORTS OF FORBIDDEN MODULES.
    """

    def __init__(self, dangerous_modules: Set[str] = DEFAULT_DANGEROUS_MODULES):
        self.dangerous_modules = dangerous_modules
        self.errors: List[Tuple[int, int, str]] = []  # (lineno, col, message)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in self.dangerous_modules:
                msg = f"Import of forbidden module: '{alias.name}'"
                self.errors.append((node.lineno, node.col_offset, msg))
                logger.warning(f"[SECURITY STUB] {msg} on line {node.lineno}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module in self.dangerous_modules:
            msg = f"Import from forbidden module: '{node.module}'"
            self.errors.append((node.lineno, node.col_offset, msg))
            logger.warning(f"[SECURITY STUB] {msg} on line {node.lineno}")
        self.generic_visit(node)


def validate_plugin_ast(code_string: str) -> bool:
    """
    Performs static AST validation of plugin code for basic dangerous constructs.
    CURRENTLY ONLY CHECKS IMPORTS.

    Args:
        code_string: The plugin's source code as a string.

    Returns:
        True if validation passes (dangerous constructs not found), False otherwise.

    Raises:
        SyntaxError: If the code is invalid and cannot be parsed.
    """
    logger.info("[SECURITY STUB] Starting basic AST validation...")
    try:
        tree = ast.parse(code_string)
        validator = AstValidator()
        validator.visit(tree)

        if validator.errors:
            logger.error("[SECURITY STUB] AST validation failed. Issues found:")
            for lineno, col, msg in validator.errors:
                logger.error(f"  - Line {lineno}, position {col}: {msg}")
            return False # Validation failed
        else:
            logger.info("[SECURITY STUB] Basic AST validation passed successfully.")
            return True # Validation passed

    except SyntaxError as e:
        logger.error(f"Syntax error during AST validation: {e}", exc_info=True)
        raise # Re-raise the syntax error