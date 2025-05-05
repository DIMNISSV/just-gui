# src/just_gui/core/i18n.py
import logging
import sys
from pathlib import Path
from typing import Optional, List, Dict

# Используем importlib.resources для доступа к файлам внутри пакета
try:
    import importlib.resources as pkg_resources
except ImportError:
    # Fallback для Python < 3.7 или если backport не установлен
    import importlib_resources as pkg_resources

from PySide6.QtCore import QTranslator, QLocale, QLibraryInfo, QCoreApplication

logger = logging.getLogger(__name__)

# Глобальные трансляторы для ядра и Qt
core_translator = QTranslator()
qt_translator = QTranslator()


def get_available_languages(translations_dir: Path) -> List[str]:
    """Находит доступные языки (файлы .qm) в указанной директории."""
    languages = []
    if translations_dir.is_dir():
        for file in translations_dir.glob('*.qm'):
            # Извлекаем код языка из имени файла (e.g., just_gui_fr.qm -> fr)
            parts = file.stem.split('_')
            if len(parts) > 1:
                lang_code = parts[-1]
                if QLocale(lang_code).language() != QLocale.Language.AnyLanguage:
                    languages.append(lang_code)
                    logger.debug(f"Найден файл перевода для языка: {lang_code}")
    return languages


def load_core_translations(language: str) -> bool:
    """Загружает перевод для ядра just-gui и стандартных диалогов Qt."""
    app = QCoreApplication.instance()
    if not app:
        logger.error("QApplication не инициализирован, не могу загрузить переводы.")
        return False

    loaded_core = False
    loaded_qt = False

    # 1. Загрузка перевода Qt (стандартные кнопки, диалоги)
    qt_base_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_translator.load(QLocale(language), "qtbase", "_", qt_base_dir):
        app.installTranslator(qt_translator)
        logger.info(f"Загружен системный перевод Qt для языка: {language}")
        loaded_qt = True
    else:
        logger.warning(f"Не удалось найти/загрузить системный перевод Qt для языка: {language} в {qt_base_dir}")

    # 2. Загрузка перевода ядра just-gui
    try:
        # Ищем файл перевода внутри пакета just_gui.translations
        package = 'just_gui.translations'
        filename = f"just_gui_{language}.qm"
        # Используем traversable API из importlib.resources
        with pkg_resources.path(package, filename) as qm_path:
            if core_translator.load(str(qm_path)):
                app.installTranslator(core_translator)
                logger.info(f"Загружен перевод ядра just-gui для языка: {language} из {qm_path}")
                loaded_core = True
            else:
                logger.error(f"Ошибка загрузки файла перевода ядра: {qm_path}")

    except FileNotFoundError:
        logger.warning(f"Файл перевода ядра 'just_gui_{language}.qm' не найден в пакете.")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при загрузке перевода ядра: {e}", exc_info=True)

    return loaded_core  # Возвращаем успех загрузки именно *нашего* перевода


def determine_language(user_config_lang: Optional[str] = None) -> str:
    """Определяет язык для использования: конфиг -> система -> fallback."""
    if user_config_lang and QLocale(user_config_lang).language() != QLocale.Language.AnyLanguage:
        logger.info(f"Используется язык из конфигурации пользователя: {user_config_lang}")
        return user_config_lang

    # Получаем системные языки
    system_locales = QLocale.system().uiLanguages()
    if system_locales:
        sys_lang = system_locales[0].split('-')[0]  # Берем только код языка (e.g., "en" из "en-US")
        logger.info(f"Используется системный язык: {sys_lang} (из {system_locales[0]})")
        return sys_lang

    fallback_lang = "en"  # Английский как fallback
    logger.warning(f"Не удалось определить язык системы, используется fallback: {fallback_lang}")
    return fallback_lang


# --- Утилиты для плагинов ---

# Словарь для хранения трансляторов плагинов {plugin_name: QTranslator}
plugin_translators: Dict[str, QTranslator] = {}


def load_plugin_translation(plugin_name: str, plugin_dir: Path, language: str) -> bool:
    """Загружает перевод для конкретного плагина."""
    app = QCoreApplication.instance()
    if not app: return False

    translations_sub_dir = plugin_dir / "translations"
    if not translations_sub_dir.is_dir():
        logger.debug(f"Директория переводов не найдена для плагина '{plugin_name}' в {plugin_dir}")
        return False

    translator = QTranslator()
    filename = f"{plugin_name}_{language}.qm"
    qm_path = translations_sub_dir / filename

    if qm_path.exists():
        if translator.load(str(qm_path)):
            app.installTranslator(translator)
            plugin_translators[plugin_name] = translator  # Сохраняем ссылку!
            logger.info(f"Загружен перевод для плагина '{plugin_name}' (язык: {language})")
            return True
        else:
            logger.error(f"Ошибка загрузки файла перевода плагина: {qm_path}")
            return False
    else:
        logger.debug(f"Файл перевода '{filename}' не найден для плагина '{plugin_name}'")
        return False


def unload_plugin_translation(plugin_name: str):
    """Выгружает перевод для плагина."""
    app = QCoreApplication.instance()
    if not app: return

    if plugin_name in plugin_translators:
        translator = plugin_translators.pop(plugin_name)
        if app.removeTranslator(translator):
            logger.info(f"Выгружен перевод для плагина '{plugin_name}'.")
        else:
            logger.warning(f"Не удалось выгрузить перевод для плагина '{plugin_name}'.")
