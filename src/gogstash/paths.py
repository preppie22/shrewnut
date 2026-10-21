"""Filesystem locations for GogStash configuration and downloads."""

import platformdirs
from pathlib import Path
from enum import StrEnum

_LEGACY_NAME = "gogstash"

class ConfigFile(StrEnum):
    """Names of the files kept in the GogStash config directory."""
    SETTINGS = 'settings.json'
    DB_CACHE = 'goglibrary.db'
    TOKEN = 'token.json'

class LogFile(StrEnum):
    """Names of the files kept in the ``logs`` folder of the config directory."""
    DOWNLOAD_LOG = 'downloads.log'
    APP_LOG = 'gogstash.log'
    AUTH_LOG = 'login.log'

def user_download_path() -> Path:
    """Return the user's downloads directory.

    Returns:
        Path: The platform-specific downloads directory.
    """
    return platformdirs.user_downloads_path()

def default_download_path() -> Path:
    """Return the default download directory for games.

    Returns:
        Path: A ``Shrewnut`` folder inside the user's downloads directory.
    """
    return user_download_path() / 'Shrewnut'

def migrate_config() -> bool:
    """Move the config directory from its GogStash name to its Shrewnut name.

    The folder is renamed in one step, so it either moves whole or stays
    where it was. Nothing happens on a fresh install, or when the Shrewnut
    folder already exists. Call it before anything writes to the config
    directory, since logging setup creates the new folder.

    Returns:
        bool: True if the old folder was moved, False if there was nothing
        to move.

    Raises:
        OSError: If the rename fails, such as on Windows while GogStash is
            still running and holding its files open.
    """
    old_config = platformdirs.user_config_path(appname=_LEGACY_NAME, appauthor=False)
    new_config = config_path()
    if not new_config.exists() and old_config.exists():
        old_config.rename(new_config)
        return True
    return False


def config_path() -> Path:
    """Return the GogStash configuration directory.

    Returns:
        Path: The platform-specific config directory for GogStash.
    """
    return platformdirs.user_config_path(appname='shrewnut', appauthor=False)

def config_file_path(config_file: ConfigFile) -> Path:
    """Return the full path of a config file.

    Args:
        config_file (ConfigFile): The config file to locate.

    Returns:
        Path: Path to the file inside the config directory.
    """
    return config_path() / config_file.value

def log_file_path(log_file: LogFile) -> Path:
    """Return the full path of a log file.

    Args:
        log_file (LogFile): The log file to locate.

    Returns:
        Path: Path to the file inside the ``logs`` folder of the config
        directory.
    """
    return config_path() / "logs" / log_file.value

def config_file_backup(config_file: ConfigFile) -> Path:
    """Return the backup path of a config file.

    Args:
        config_file (ConfigFile): The config file to back up.

    Returns:
        Path: Path next to the original file with a ``.bak`` suffix.
    """
    filename = config_file.value + ".bak"
    return config_path() / filename