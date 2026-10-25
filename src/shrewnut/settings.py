"""User settings stored as JSON in the config directory.

Attributes:
    DEFAULT_SETTINGS (dict): Every valid setting key and its default
        value. Keys missing from the settings file fall back to these.
    ERROR_STR (str): What ``settings_broken`` returns when the settings
        file can't be read, created or moved aside.
"""

import json
from typing import Any
from pathlib import Path

from shrewnut import paths

import logging
log = logging.getLogger(__name__)

ERROR_STR = "error"

GOG_LANGUAGES = {
    'en': 'English',                   # English
    'ar': 'العربية',                   # Arabic
    'br': 'Português do Brasil',       # Brazilian Portuguese
    'cn': '中文(简体)',                 # Chinese (Simplified)
    'cz': 'Čeština',                   # Czech
    'da': 'Dansk',                     # Danish
    'de': 'Deutsch',                   # German
    'es': 'Español',                   # Spanish (Spain)
    'es_mx': 'Español (Latinoamérica)',  # Spanish (Latin America)
    'fi': 'Suomi',                     # Finnish
    'fr': 'Français',                  # French
    'gk': 'Ελληνικά',                  # Greek
    'hr': 'Hrvatski',                  # Croatian
    'hu': 'Magyar',                    # Hungarian
    'id': 'Bahasa Indonesia',          # Indonesian
    'it': 'Italiano',                  # Italian
    'jp': '日本語',                     # Japanese
    'ko': '한국어',                     # Korean
    'nl': 'Nederlands',                # Dutch
    'no': 'Norsk',                     # Norwegian
    'pl': 'Polski',                    # Polish
    'pt': 'Português',                 # Portuguese (Portugal)
    'ro': 'Română',                    # Romanian
    'ru': 'Русский',                   # Russian
    'sv': 'Svenska',                   # Swedish
    'th': 'ไทย',                       # Thai
    'tr': 'Türkçe',                    # Turkish
    'uk': 'Українська',                # Ukrainian
    'vi': 'Tiếng Việt',                # Vietnamese
    'zh': '中文(繁體)',                 # Chinese (Traditional)
}

DEFAULT_SETTINGS = {
    'download_path': str(paths.default_download_path()),
    'download_concurrency': 2,
    'platform_filter': ['Linux','Windows','MacOS'],
    'verify_downloads': True,
    'installers': True,
    'bonus_content': False,
    'patches': True,
    'languages': ['en'],
    'theme': 'System'
}

def _create_settings() -> bool:
    """Write the default settings file if there isn't one yet.

    The file is written directly rather than through a temp file, since
    there are no earlier settings to lose.

    Returns:
        bool: True if the settings file exists afterwards, False if it
        couldn't be written. The reason is logged.
    """
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    if settings_file.exists():
        return True
    try:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_file, 'w') as sfw:
            json.dump(obj=DEFAULT_SETTINGS, fp=sfw, indent=2)
    except OSError as e:
        log.warning(f"failed to create settings file on disk: {str(e)}")
        return False
    return True

def _write_settings(settings: dict) -> bool:
    """Write settings to disk, creating the file first if needed.

    The settings are written to ``settings.json~`` first, which then
    replaces the settings file in one step. A write that fails partway,
    such as on a full disk, leaves the previous settings as they were,
    and the temp file is deleted.

    Args:
        settings (dict): The complete settings to save.

    Returns:
        bool: True if the settings were saved. False if writing or
        replacing the file failed, in which case the reason is logged and
        the previous settings file is unchanged.
    """
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    temp_file: Path = settings_file.with_name(settings_file.name + "~")
    
    if not settings_file.exists():
        _create_settings()
    try:
        with open(temp_file, 'w') as sfw:
            json.dump(obj=settings, fp=sfw, indent=2)
        temp_file.replace(settings_file)
    except OSError as e:
        log.warning(f"failed to write settings to disk: {str(e)}")
        temp_file.unlink(missing_ok=True)
        return False
    return True

def _read_settings() -> dict:
    """Read settings from disk, creating the file first if needed.

    Never raises for a bad settings file. If the file can't be opened,
    isn't valid JSON or doesn't hold a JSON object, the reason is logged
    and the defaults are used. Telling the user about it is left to
    ``settings_broken``.

    Returns:
        dict: Saved settings merged over ``DEFAULT_SETTINGS``, or a copy
        of ``DEFAULT_SETTINGS`` if the file can't be read.
    """
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    if not settings_file.exists():
        _create_settings()
    try:
        with open(settings_file, 'r') as sfr:
            settings: dict = {**DEFAULT_SETTINGS, **json.load(fp=sfr)}
    except (ValueError, TypeError, OSError) as e:
        if isinstance(e, ValueError):
            log.warning(f"malformed settings file: {str(e)}")
        elif isinstance(e, TypeError):
            log.warning(f"invalid json format: {str(e)}")
        else:
            log.warning(f"cannot open settings file: {str(e)}")
        return DEFAULT_SETTINGS.copy()
    return settings

def settings_broken() -> str:
    """Check that the settings file can be read, moving a damaged one aside.

    ``main`` calls it once at startup, before the main window reads or
    saves any setting, so the user can be told. A file that isn't valid JSON, or that doesn't hold a
    JSON object, is renamed to ``settings_broken.json`` in the same folder,
    replacing any earlier one. The next read then starts from the
    defaults, and the old values can still be copied out by hand. Merging
    the loaded value into ``DEFAULT_SETTINGS`` is what catches a file that
    holds a list or other non-object JSON, since that raises ``TypeError``.
    A missing file is created with the defaults.

    Returns:
        str: An empty string if the settings file is fine or was just
        created. The backup's path if the file was damaged and moved
        aside. ``ERROR_STR`` if the file couldn't be opened, moved aside or
        created, in which case the defaults are used for this run and
        saving settings may fail.
    """
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    if not settings_file.exists():
        if not _create_settings():
            return ERROR_STR
        return ""
    try:
        with open(settings_file, 'r') as fr:
            {**DEFAULT_SETTINGS, **json.load(fp=fr)}
    except (ValueError, TypeError) as e:
        if isinstance(e, ValueError):
            log.warning(f"malformed settings file, loading defaults: {str(e)}")
        else:
            log.warning(f"invalid json format, loading defaults: {str(e)}")
        bad_name = settings_file.stem + "_broken" + settings_file.suffix
        try:
            bad_file = settings_file.replace(settings_file.with_name(bad_name))
            return str(bad_file)
        except OSError as e2:
            log.warning(f"backing up bad settings failed: {str(e2)}")
            return ERROR_STR
    except OSError as e:
        log.warning(f"cannot open settings file, loading defaults: {str(e)}")
        return ERROR_STR
    return ""

def update_setting(key: str, value: Any) -> bool:
    """Update and save a single setting.

    Args:
        key (str): The setting to update.
        value (Any): The new value.

    Returns:
        bool: True if saved, False if the settings file couldn't be
        written. The previous settings file is then unchanged.

    Raises:
        KeyError: If ``key`` is not a known setting.
    """
    settings = _read_settings()
    if key not in DEFAULT_SETTINGS.keys():
        raise KeyError(key)
    settings[key] = value
    return _write_settings(settings)

def update_settings(settings: dict) -> bool:
    """Update and save several settings at once.

    Nothing is written if any key is invalid.

    Args:
        settings (dict): Setting keys mapped to their new values.

    Returns:
        bool: True if saved, False if the settings file couldn't be
        written. The previous settings file is then unchanged.

    Raises:
        KeyError: If any key is not a known setting.
    """
    current_settings = _read_settings()
    for item in settings.items():
        if item[0] not in DEFAULT_SETTINGS:
            raise KeyError(item[0])
        current_settings[item[0]] = item[1] 
    return _write_settings(current_settings)

def read_setting(key: str) -> Any:
    """Return the value of a single setting.

    Args:
        key (str): The setting to read.

    Returns:
        Any: The setting's value, or None if the key is unknown.
    """
    settings = _read_settings()
    return settings.get(key)

def read_settings() -> dict:
    """Return all settings.

    Returns:
        dict: Saved settings merged over ``DEFAULT_SETTINGS``.
    """
    return _read_settings()

def set_default(key: str) -> bool:
    """Reset a single setting to its default value.

    Args:
        key (str): The setting to reset.

    Returns:
        bool: True if saved, False if the settings file couldn't be
        written. The previous settings file is then unchanged.

    Raises:
        KeyError: If ``key`` is not a known setting.
    """
    settings = _read_settings()
    if key not in DEFAULT_SETTINGS.keys():
        raise KeyError(key)
    settings[key] = DEFAULT_SETTINGS.get(key)
    return _write_settings(settings)