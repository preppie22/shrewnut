from shrewnut import paths


def test_log_files_live_in_their_own_folder(tmp_path):
    # The config folder holds settings, the token and the cache. The logs
    # get a room of their own instead of sprawling across the living room.
    for log_file in paths.LogFile:
        assert paths.log_file_path(log_file) == tmp_path / "logs" / log_file.value


# --- GogStash -> Shrewnut: moving the config folder ---

import pytest  # noqa: E402  (kept with the tests that need it)
import platformdirs  # noqa: E402
from pathlib import Path  # noqa: E402


@pytest.fixture
def two_config_dirs(tmp_path, monkeypatch):
    """conftest sends every app name to the same tmp_path, so old and new
    would be one folder. Give each name its own room for these tests."""
    monkeypatch.setattr(platformdirs, "user_config_path",
                        lambda appname, **kwargs: tmp_path / "config" / appname)
    return tmp_path / "config" / "gogstash", tmp_path / "config" / "shrewnut"


def test_migrate_config_moves_the_old_folder_with_everything_in_it(two_config_dirs):
    # Same login, same settings, same download path. New name on the door.
    old, new = two_config_dirs
    (old / "logs").mkdir(parents=True)
    (old / "settings.json").write_text('{"download_path": "/mnt/nas/games"}')
    (old / "token.json").write_text('{"refresh_token": "still-good"}')
    (old / "logs" / "gogstash.log").write_text("the good old days\n")

    assert paths.migrate_config() is True

    assert not old.exists()
    assert (new / "settings.json").read_text() == '{"download_path": "/mnt/nas/games"}'
    assert (new / "token.json").read_text() == '{"refresh_token": "still-good"}'
    assert (new / "logs" / "gogstash.log").read_text() == "the good old days\n"


def test_migrate_config_leaves_both_alone_when_shrewnut_already_moved_in(two_config_dirs):
    # Someone ran an old GogStash after upgrading. Its fresh folder doesn't
    # get to evict the real one.
    old, new = two_config_dirs
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "settings.json").write_text("old")
    (new / "settings.json").write_text("new")

    assert paths.migrate_config() is False

    assert (old / "settings.json").read_text() == "old"
    assert (new / "settings.json").read_text() == "new"


def test_migrate_config_on_a_fresh_install_does_nothing(two_config_dirs):
    # Nothing to move. Creating the folder is settings' job, not ours.
    old, new = two_config_dirs

    assert paths.migrate_config() is False

    assert not old.exists()
    assert not new.exists()


def test_migrate_config_lets_a_refused_move_reach_the_caller(two_config_dirs, monkeypatch):
    # Windows, GogStash still running, log file held open. The move has to
    # fail loudly and leave the old folder exactly as it was.
    old, new = two_config_dirs
    old.mkdir(parents=True)
    (old / "token.json").write_text("precious")

    def refuse(self, target):
        raise PermissionError(13, "[WinError 5] Access is denied")
    monkeypatch.setattr(Path, "rename", refuse)

    with pytest.raises(PermissionError):
        paths.migrate_config()

    assert (old / "token.json").read_text() == "precious"
    assert not new.exists()
