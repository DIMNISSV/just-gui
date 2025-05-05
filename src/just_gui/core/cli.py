# src/just_gui/core/cli.py
import argparse
import asyncio
import logging
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
import qasync
# from platformdirs import user_config_dir # Можно импортировать здесь, но используется в AppCore

from .app import AppCore, APP_NAME, APP_AUTHOR  # <-- Импортируем константы


# Настройка базового логирования (можно вынести в отдельную функцию)
def setup_logging():
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # По умолчанию для других библиотек - WARNING

    # Настраиваем логгер нашего приложения
    app_logger = logging.getLogger('just_gui')
    # Уровень установится позже из конфига, пока ставим DEBUG, чтобы видеть логи AppCore.__init__
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = False  # Не передавать сообщения корневому

    # Создаем обработчик для вывода в консоль
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Добавляем обработчик к нашему логгеру
    if not app_logger.handlers:
        app_logger.addHandler(handler)

    # Можно добавить FileHandler при необходимости
    # file_handler = logging.FileHandler("app.log")
    # file_handler.setFormatter(formatter)
    # app_logger.addHandler(file_handler)


setup_logging()  # Вызываем настройку логирования при загрузке модуля
logger = logging.getLogger(__name__)  # Получаем логгер для cli (__name__ будет 'just_gui.core.cli')


def main():
    """Главная функция запуска приложения."""
    parser = argparse.ArgumentParser(description="Запуск just-gui приложения.")
    parser.add_argument(
        "--profile",
        type=str,
        required=True,
        help="Путь к файлу профиля приложения (*.toml)",
    )
    args = parser.parse_args()

    logger.info(f"Запуск just-gui с профилем: {args.profile}")

    # Создание QApplication ДО event loop'а qasync
    # Используем try...except для QApplication, т.к. оно может уже существовать
    try:
        qapp = QApplication.instance()
        if qapp is None:
            logger.debug("Создание нового экземпляра QApplication.")
            # Передаем sys.argv в QApplication
            qapp = QApplication(sys.argv)
        else:
            logger.debug("Использование существующего экземпляра QApplication.")
    except Exception as e:
        print(f"Критическая ошибка при создании QApplication: {e}", file=sys.stderr)
        sys.exit(1)

    # Настройка qasync
    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    app_core = None  # Инициализируем переменную

    try:
        # --- Шаг 1: Создание экземпляра AppCore (синхронно) ---
        logger.debug("Создание экземпляра AppCore...")
        app_core = AppCore(profile_path=args.profile)
        logger.debug("Экземпляр AppCore создан.")

        # --- Шаг 2: Асинхронная инициализация (загрузка плагинов, восстановление вида) ---
        logger.debug("Запуск асинхронной инициализации AppCore...")
        # Используем loop.run_until_complete для выполнения async initialize()
        # до старта основного цикла
        loop.run_until_complete(app_core.initialize())
        logger.debug("Асинхронная инициализация AppCore завершена.")

        # --- Шаг 3: Показ окна ---
        logger.debug("Отображение главного окна...")
        app_core.show()
        logger.debug("Главное окно отображено.")

        # --- Шаг 4: Запуск главного цикла событий ---
        with loop:
            logger.info("Запуск основного цикла событий...")
            loop.run_forever()  # Запускаем бесконечный цикл событий Qt

        logger.info("Основной цикл событий завершен.")
        # Код после loop.run_forever() выполнится после закрытия приложения (когда окно закроется)

    except Exception as e:
        logger.critical(f"Необработанное исключение на верхнем уровне: {e}", exc_info=True)
        # Показываем критическую ошибку пользователю, если GUI еще работает
        try:
            # QMainWindow может быть недоступен, используем None в качестве родителя
            QMessageBox.critical(
                None,  # Нет родительского окна, т.к. app_core мог не создаться/быть поврежден
                "Критическая ошибка",
                f"Произошла непредвиденная ошибка:\n{e}\n\nПриложение будет закрыто."
            )
            # Убедимся, что приложение Qt завершается после показа ошибки
            if qapp:
                qapp.quit()  # Попытка завершить приложение Qt
        except Exception as msg_e:
            # Если даже QMessageBox не сработал, выводим в stderr
            print(f"Критическая ошибка приложения: {e}\nОшибка показа сообщения об ошибке: {msg_e}", file=sys.stderr)
        sys.exit(1)  # Выход с кодом ошибки
    finally:
        # Очистка asyncio loop (рекомендуется)
        # Проверяем состояние цикла перед закрытием
        if loop.is_running():
            logger.debug("Остановка цикла событий asyncio перед закрытием...")
            loop.stop()  # Остановка, если вдруг run_forever завершился иначе
        logger.debug("Закрытие цикла событий asyncio...")
        loop.close()
        logger.info("Цикл событий asyncio закрыт.")
        # sys.exit(0) # Нормальный выход, если не было ошибок (уже происходит через app.exec())


if __name__ == "__main__":
    main()
