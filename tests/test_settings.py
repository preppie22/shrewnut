import errno
import json
import os
from pathlib import Path

import pytest

from shrewnut import paths, settings


def _settings_file():
    return paths.config_file_path(paths.ConfigFile.SETTINGS)


def _no_entry(*args, **kwargs):
    raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))


def test_create_settings_writes_default_settings_file():
    settings._create_settings()
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    assert settings_file.exists()
    with open(settings_file) as f:
        assert json.load(f) == settings.DEFAULT_SETTINGS


def test_create_settings_leaves_an_existing_file_alone():
    settings._create_settings()
    settings.update_setting("theme", "Dark")

    assert settings._create_settings() is True  # already there, nothing to do

    assert settings.read_setting("theme") == "Dark"


def test_create_settings_reports_a_folder_it_cannot_write(monkeypatch):
    monkeypatch.setattr(settings, "open", _no_entry, raising=False)

    assert settings._create_settings() is False
    assert not _settings_file().exists()


def test_read_setting_creates_file_if_missing():
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    assert not settings_file.exists()

    result = settings.read_setting("theme")

    assert settings_file.exists()
    assert result == settings.DEFAULT_SETTINGS["theme"]


def test_read_settings_merges_missing_keys_from_defaults():
    settings._create_settings()
    settings_file = paths.config_file_path(paths.ConfigFile.SETTINGS)
    with open(settings_file, "w") as f:
        json.dump({"theme": "Dark"}, f)  # simulates a settings file from an older version

    result = settings._read_settings()

    assert result["theme"] == "Dark"
    assert result["download_concurrency"] == settings.DEFAULT_SETTINGS["download_concurrency"]


def test_update_setting_persists_new_value():
    settings.update_setting("download_concurrency", 5)
    assert settings.read_setting("download_concurrency") == 5


def test_update_setting_persists_falsy_values():
    # Regression: an earlier version treated any falsy new value as "no update".
    settings.update_setting("verify_downloads", False)
    assert settings.read_setting("verify_downloads") is False

    settings.update_setting("download_concurrency", 0)
    assert settings.read_setting("download_concurrency") == 0


def test_update_setting_raises_for_unknown_key():
    with pytest.raises(KeyError):
        settings.update_setting("not_a_real_setting", "value")


def test_read_setting_returns_none_for_unknown_key():
    assert settings.read_setting("not_a_real_setting") is None


def test_set_default_resets_single_key():
    settings.update_setting("theme", "Dark")
    settings.update_setting("download_concurrency", 10)

    settings.set_default("theme")

    assert settings.read_setting("theme") == settings.DEFAULT_SETTINGS["theme"]
    assert settings.read_setting("download_concurrency") == 10  # untouched


def test_set_default_resets_key_currently_set_to_falsy_value():
    # Regression: an earlier version skipped the reset whenever the current value was falsy.
    settings.update_setting("verify_downloads", False)

    settings.set_default("verify_downloads")

    assert settings.read_setting("verify_downloads") == settings.DEFAULT_SETTINGS["verify_downloads"]


def test_set_default_raises_for_unknown_key():
    with pytest.raises(KeyError):
        settings.set_default("not_a_real_setting")


# --- damaged or unreadable settings file ---

DAMAGED_CONTENTS = [
    pytest.param("", id="empty"),
    pytest.param('{\n  "download_path": "/mnt/nas/Ga', id="cut-off"),
    pytest.param("not json at all", id="junk"),
    pytest.param("[1, 2]", id="list"),
    pytest.param("null", id="null"),
    pytest.param('"hello"', id="string"),
]


@pytest.mark.parametrize("contents", DAMAGED_CONTENTS)
def test_a_damaged_settings_file_reads_as_the_defaults(contents):
    _settings_file().write_text(contents)

    assert settings._read_settings() == settings.DEFAULT_SETTINGS


def test_an_unreadable_settings_file_reads_as_the_defaults(monkeypatch):
    settings._create_settings()
    monkeypatch.setattr(settings, "open", _no_entry, raising=False)

    assert settings.read_setting("theme") == settings.DEFAULT_SETTINGS["theme"]


def test_saving_over_a_damaged_file_leaves_the_defaults_alone():
    # Regression: the fallback handed out DEFAULT_SETTINGS itself, so the
    # first theme change rewrote the defaults for the rest of the run, and
    # set_default happily "reset" the theme to the one you just picked.
    _settings_file().write_text("not json at all")

    assert settings.update_setting("theme", "Dark") is True

    assert settings.DEFAULT_SETTINGS["theme"] == "System"
    settings.set_default("theme")
    assert settings.read_setting("theme") == "System"


def test_settings_broken_is_quiet_about_a_good_file():
    settings.update_setting("theme", "Dark")

    assert settings.settings_broken() == ""

    assert settings.read_setting("theme") == "Dark"
    assert not _settings_file().with_name("settings_broken.json").exists()


def test_settings_broken_creates_a_missing_file():
    assert settings.settings_broken() == ""

    assert json.loads(_settings_file().read_text()) == settings.DEFAULT_SETTINGS


@pytest.mark.parametrize("contents", DAMAGED_CONTENTS)
def test_settings_broken_moves_a_damaged_file_aside(contents):
    # The download folder in there is the one thing worth fishing out by
    # hand, so the bad file is moved, not binned.
    _settings_file().write_text(contents)

    backup = settings.settings_broken()

    assert backup == str(_settings_file().with_name("settings_broken.json"))
    assert Path(backup).read_text() == contents
    assert not _settings_file().exists()
    assert settings.read_settings() == settings.DEFAULT_SETTINGS


def test_settings_broken_replaces_an_older_backup():
    # Regression: rename() refuses to overwrite on Windows, so the second
    # bad file in a settings file's life would have crashed the very check
    # meant to stop the crash.
    _settings_file().with_name("settings_broken.json").write_text("the first disaster")
    _settings_file().write_text("the second disaster")

    backup = settings.settings_broken()

    assert Path(backup).read_text() == "the second disaster"


def test_settings_broken_reports_a_damaged_file_it_cannot_move(monkeypatch):
    _settings_file().write_text("not json at all")
    monkeypatch.setattr(Path, "replace", _no_entry)

    assert settings.settings_broken() == settings.ERROR_STR

    assert _settings_file().read_text() == "not json at all"


def test_settings_broken_reports_a_file_it_cannot_open(monkeypatch):
    settings._create_settings()
    monkeypatch.setattr(settings, "open", _no_entry, raising=False)

    assert settings.settings_broken() == settings.ERROR_STR


def test_settings_broken_reports_a_missing_file_it_cannot_create(monkeypatch):
    monkeypatch.setattr(settings, "open", _no_entry, raising=False)

    assert settings.settings_broken() == settings.ERROR_STR


# --- saving ---

def test_saving_leaves_no_temp_file_behind():
    assert settings.update_setting("theme", "Dark") is True

    assert not _settings_file().with_name("settings.json~").exists()


def test_a_save_that_fills_the_disk_keeps_the_old_settings(monkeypatch):
    # The whole point of #35's write half: half a settings file used to mean
    # no settings file, and no download folder either.
    settings.update_setting("download_path", "/mnt/nas/Games")
    before = _settings_file().read_text()

    def disk_fills_up_mid_dump(obj, fp, **kwargs):
        fp.write('{\n  "download_path": "/mnt/na')
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(settings.json, "dump", disk_fills_up_mid_dump)

    assert settings.update_setting("theme", "Dark") is False

    assert _settings_file().read_text() == before
    assert not _settings_file().with_name("settings.json~").exists()


def test_a_save_that_cannot_replace_the_file_keeps_the_old_settings(monkeypatch):
    # Windows, antivirus, an editor with settings.json open: pick your villain.
    settings.update_setting("download_path", "/mnt/nas/Games")
    before = _settings_file().read_text()
    monkeypatch.setattr(Path, "replace", _no_entry)

    assert settings.update_settings({"theme": "Dark", "download_concurrency": 4}) is False

    assert _settings_file().read_text() == before
    assert not _settings_file().with_name("settings.json~").exists()
