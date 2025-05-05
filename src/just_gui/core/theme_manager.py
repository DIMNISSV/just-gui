# src/just_gui/core/theme_manager.py
import logging
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


def apply_theme(target_widget: QWidget, theme_name: str):
    """Применяет цветовую тему к указанному виджету."""
    logger.info(f"Применение темы '{theme_name}'...")
    style = ""
    theme_applied_source = "system"  # Источник примененной темы

    try:
        # Сначала пробуем qdarktheme
        import qdarktheme
        valid_qdark_themes = ["dark", "light"]
        if theme_name.lower() in valid_qdark_themes:
            style = qdarktheme.load_stylesheet(theme_name.lower())
            theme_applied_source = f"qdarktheme ({theme_name})"
            logger.info(f"Применена тема qdarktheme '{theme_name}'.")
        else:
            logger.warning(
                f"Тема '{theme_name}' не поддерживается qdarktheme (ожидалось 'light' или 'dark'). Используется системная тема.")
            style = ""  # Возврат к системной теме
            # qdarktheme.setup() # Можно попробовать сбросить qdarktheme
    except ImportError:
        # qdarktheme не установлен, используем базовые стили
        logger.warning("Библиотека qdarktheme не найдена. Применяется базовый стиль.")
        if theme_name.lower() == "dark":
            style = """
                QWidget { background-color: #2d2d2d; color: #f0f0f0; border: none; }
                QMainWindow { background-color: #2d2d2d; }
                QMenuBar { background-color: #3c3c3c; color: #f0f0f0; }
                QMenuBar::item:selected { background-color: #555; }
                QMenu { background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555; }
                QMenu::item:selected { background-color: #555; }
                QToolBar { background-color: #3c3c3c; border: none; padding: 2px; }
                QStatusBar { background-color: #3c3c3c; color: #f0f0f0; }
                QTabWidget::pane { border: 1px solid #444; }
                QTabBar::tab { background: #3c3c3c; color: #f0f0f0; padding: 5px; border: 1px solid #444; border-bottom: none; }
                QTabBar::tab:selected { background: #555; }
                QTabBar::tab:!selected { color: #a0a0a0; background: #2d2d2d;}
                QTabBar::close-button { image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-close-16.png); subcontrol-position: right; }
                QTabBar::close-button:hover { background: #555; }
                QPushButton { background-color: #555; color: #f0f0f0; border: 1px solid #666; padding: 5px; min-width: 60px;}
                QPushButton:hover { background-color: #666; }
                QPushButton:pressed { background-color: #444; }
                QLabel { color: #f0f0f0; background-color: transparent; }
                QLineEdit { background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555; padding: 2px; }
            """
            theme_applied_source = "basic dark"
        else:
            style = ""  # Системная/светлая тема
            theme_applied_source = "system/basic light"
            logger.info("Применена системная тема (светлая).")

    try:
        target_widget.setStyleSheet(style)
    except Exception as e:
        logger.error(f"Ошибка применения стиля темы '{theme_name}': {e}", exc_info=True)

    logger.debug(f"Источник примененной темы: {theme_applied_source}")
