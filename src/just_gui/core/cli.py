# src/just_gui/core/cli.py
import argparse
import asyncio
import logging
import sys
import toml  # Добавляем для чтения user_settings
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication  # Для установки атрибутов
import qasync
import platformdirs

# Импортируем утилиты i18n и AppCore
from .app import AppCore, APP_NAME, APP_AUTHOR
from .i18n import determine_language, load_core_translations


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    app_logger = logging.getLogger('just_gui')
    app_logger.setLevel(logging.DEBUG)  # По умолчанию DEBUG, потом переопределится
    app_logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    if not app_logger.handlers: app_logger.addHandler(handler)


setup_logging()
logger = logging.getLogger(__name__)


def get_user_settings() -> dict:
    """Загружает пользовательские настройки."""
    try:
        settings_dir = Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))
        settings_file = settings_dir / "user_settings.toml"
        if settings_file.exists():
            logger.debug(f"Загрузка пользовательских настроек из {settings_file}")
            return toml.load(settings_file)
        else:
            logger.debug("Файл пользовательских настроек не найден.")
            return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки пользовательских настроек: {e}", exc_info=True)
        return {}


def main():
    parser = argparse.ArgumentParser(description="Запуск just-gui приложения.")
    parser.add_argument("--profile", type=str, required=True, help="Профиль *.toml")
    
    parser.add_argument("--lang", type=str, help="Код языка для интерфейса (напр., 'en', 'fr')")
    
    args = parser.parse_args()
    logger.info(f"Запуск just-gui с профилем: {args.profile}")

    
    user_settings = get_user_settings()
    # Приоритет: CLI -> user_settings -> система -> fallback
    user_lang = args.lang or user_settings.get("language")
    language_to_load = determine_language(user_lang)
    logger.info(f"Выбранный язык интерфейса: {language_to_load}")

    # Установка атрибутов организации для QSettings и др.
    QCoreApplication.setOrganizationName(APP_AUTHOR)
    QCoreApplication.setApplicationName(APP_NAME)
    

    try:
        qapp = QApplication.instance()
        if qapp is None:
            logger.debug("Создание QApplication.")
            qapp = QApplication(sys.argv)
        else:
            logger.debug("Использование QApplication.")
    except Exception as e:
        print(f"Ошибка QApplication: {e}", file=sys.stderr); sys.exit(1)

    
    if not load_core_translations(language_to_load):
        # Если наш перевод не загрузился, можно сообщить пользователю
        logger.warning(
            f"Не удалось загрузить основной перевод для языка '{language_to_load}'. Интерфейс будет на языке по умолчанию (Английский).")
    

    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    app_core = None

    try:
        logger.debug("Создание AppCore...")
        app_core = AppCore(profile_path=args.profile)
        
        app_core.current_language = language_to_load
        
        logger.debug("AppCore создан.")

        logger.debug("Запуск async initialize...")
        loop.run_until_complete(app_core.initialize())
        logger.debug("Async initialize завершен.")

        logger.debug("Отображение окна...")
        app_core.show()
        logger.debug("Окно отображено.")

        with loop:
            logger.info("Запуск цикла событий...")
            loop.run_forever()
        logger.info("Цикл событий завершен.")

    except Exception as e:
        logger.critical(f"Необработанное исключение: {e}", exc_info=True)
        try:
            QMessageBox.critical(None, "Критическая ошибка", f"Ошибка:\n{e}\n\nПриложение будет закрыто.")
        except Exception as msg_e:
            print(f"Критическая ошибка: {e}\nОшибка QMessageBox: {msg_e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if loop.is_running(): loop.stop()
        logger.debug("Закрытие цикла asyncio...")
        loop.close()
        logger.info("Цикл asyncio закрыт.")


if __name__ == "__main__":
    main()
