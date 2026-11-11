import json
import logging
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
import requests

from shrewnut import updates
from shrewnut.constants import HTTP_TIMEOUT


def page(tag):
    return f"https://github.com/preppie22/shrewnut/releases/tag/{tag}"


def make_response(body, status_code=200, content_type="application/json"):
    # A real Response rather than a MagicMock, so raise_for_status() and
    # json() behave exactly like they will when GitHub is the one talking.
    response = requests.Response()
    response.status_code = status_code
    response.headers["Content-Type"] = content_type
    response._content = (json.dumps(body) if not isinstance(body, str) else body).encode()
    response.url = updates.RELEASES_URL
    return response


def release(tag):
    return {"tag_name": tag, "html_url": page(tag)}


def releases(*tags):
    return make_response([release(tag) for tag in tags])


@pytest.fixture(autouse=True)
def cache_file(tmp_path):
    # Every test gets its own throwaway cache, so nothing here ever
    # touches the real config folder, and no test inherits a "checked
    # recently" from the one before it.
    path = tmp_path / "update_check.json"
    with patch("shrewnut.updates.config_file_path", return_value=path):
        yield path


def write_cache(path, version="2026.12.1", url=None, age=timedelta(hours=1), **overrides):
    data = {
        "timestamp": time.time() - age.total_seconds(),
        "upstream_version": version,
        "upstream_url": page(f"v{version}") if url is None else url,
    }
    data.update(overrides)
    path.write_text(json.dumps(data))


@pytest.fixture
def installed():
    # Pretend to be whatever version the test needs, instead of whatever
    # the venv happens to have installed this week.
    with patch("shrewnut.updates.metadata.version") as mock_version:
        yield mock_version


@pytest.fixture
def github():
    with patch("shrewnut.updates.requests.get") as mock_get:
        yield mock_get


def test_newer_release_returns_its_version_and_page(installed, github):
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.12.1", "v2026.11.10", "v2026.10.30-beta")

    result = updates.get_latest_release()

    assert result == ("2026.12.1", page("v2026.12.1"))
    # A plain string for the status bar, not a Version object in disguise.
    assert type(result[0]) is str
    installed.assert_called_once_with("shrewnut")
    args, kwargs = github.call_args
    assert args[0] == "https://api.github.com/repos/preppie22/shrewnut/releases"
    # No timeout means a quiet GitHub could keep the thread waiting forever.
    assert kwargs["timeout"] == HTTP_TIMEOUT


def test_same_version_is_up_to_date(installed, github):
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.11.10", "v2026.10.30-beta")

    assert updates.get_latest_release() is None


def test_build_newer_than_the_release_is_not_downgraded(installed, github):
    # A dev build from the future doesn't need to hear about the past.
    installed.return_value = "2026.12.1"
    github.return_value = releases("v2026.11.10")

    assert updates.get_latest_release() is None


def test_beta_tag_matches_its_normalized_installed_version(installed, github):
    # The tag says "-beta", the metadata says "b0". Same release, two
    # accents. A string comparison would announce the app to itself.
    installed.return_value = "2026.10.30b0"
    github.return_value = releases("v2026.10.30-beta")

    assert updates.get_latest_release(prerelease=True) is None


def test_stable_release_beats_the_beta_of_the_same_date(installed, github):
    installed.return_value = "2026.11.10b0"
    github.return_value = releases("v2026.11.10")

    assert updates.get_latest_release() == ("2026.11.10", page("v2026.11.10"))


def test_month_10_is_newer_than_month_9(installed, github):
    # As strings, "2026.9.26" > "2026.10.5", because "9" > "1". Strings
    # can't count, versions can.
    installed.return_value = "2026.9.26"
    github.return_value = releases("v2026.9.26", "v2026.10.5")

    assert updates.get_latest_release() == ("2026.10.5", page("v2026.10.5"))


def test_highest_version_wins_whatever_order_github_lists(installed, github):
    # A re-created old release jumps to the top of GitHub's list. It
    # doesn't get to jump the version queue too.
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.11.20", "v2026.12.1", "v2026.11.10")

    assert updates.get_latest_release() == ("2026.12.1", page("v2026.12.1"))


def test_newer_beta_is_skipped_for_stable_users(installed, github):
    # A beta on top must not hide the stable release underneath it.
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.12.5-beta", "v2026.12.1", "v2026.11.10")

    assert updates.get_latest_release() == ("2026.12.1", page("v2026.12.1"))


def test_newer_beta_is_offered_when_betas_are_on(installed, github):
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.12.5-beta", "v2026.12.1", "v2026.11.10")

    assert updates.get_latest_release(prerelease=True) == ("2026.12.5b0", page("v2026.12.5-beta"))


def test_only_betas_newer_is_up_to_date_for_stable_users(installed, github):
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.12.5-beta", "v2026.12.2-beta")

    assert updates.get_latest_release() is None


def test_no_releases_at_all_returns_none(installed, github):
    installed.return_value = "2026.11.10"
    github.return_value = make_response([])

    assert updates.get_latest_release() is None


def test_bad_tag_is_skipped_not_fatal(installed, github, caplog):
    # One test tag in the list shouldn't blind the check for the next 29
    # releases.
    installed.return_value = "2026.11.10"
    github.return_value = releases("the-good-one", "v2026.12.1")

    with caplog.at_level(logging.WARNING, logger="shrewnut.updates"):
        result = updates.get_latest_release()

    assert result == ("2026.12.1", page("v2026.12.1"))
    assert "the-good-one" in caplog.text


def test_release_without_a_page_is_skipped(installed, github):
    # Newest one has no html_url. Its version mustn't leave with the
    # previous release's page, or with no page at all.
    installed.return_value = "2026.11.10"
    github.return_value = make_response([{"tag_name": "v2026.12.5"}, release("v2026.11.20")])

    assert updates.get_latest_release() == ("2026.11.20", page("v2026.11.20"))


@pytest.mark.parametrize("entry", [
    {"html_url": page("v2026.12.1")},
    {"tag_name": "v2026.12.1"},
    {"tag_name": "the-good-one", "html_url": page("the-good-one")},
], ids=["no tag", "no page", "bad tag"])
def test_nothing_usable_returns_none(installed, github, entry):
    installed.return_value = "2026.11.10"
    github.return_value = make_response([entry])

    assert updates.get_latest_release() is None


@pytest.mark.parametrize("error", [
    requests.ConnectionError("no network, no problem"),
    requests.Timeout("GitHub is thinking very hard"),
])
def test_offline_or_slow_github_returns_none(installed, github, error):
    installed.return_value = "2026.11.10"
    github.side_effect = error

    assert updates.get_latest_release() is None


@pytest.mark.parametrize("status_code, body", [
    (403, {"message": "API rate limit exceeded for 203.0.113.7."}),
    (404, {"message": "Not Found", "status": "404"}),
    (500, {"message": "Server Error"}),
])
def test_github_error_returns_none(installed, github, status_code, body):
    # GitHub's errors are JSON too, just not a list of releases.
    installed.return_value = "2026.11.10"
    github.return_value = make_response(body, status_code=status_code)

    assert updates.get_latest_release() is None


def test_html_instead_of_json_returns_none(installed, github):
    # What you get from the web page URL instead of the API one.
    installed.return_value = "2026.11.10"
    github.return_value = make_response("<!DOCTYPE html><html>a lovely page</html>",
                                        content_type="text/html; charset=utf-8")

    assert updates.get_latest_release() is None


def test_failures_are_logged_as_warnings(installed, github, caplog):
    installed.return_value = "2026.11.10"
    github.side_effect = requests.ConnectionError("cable chewed by shrew")

    with caplog.at_level(logging.WARNING, logger="shrewnut.updates"):
        updates.get_latest_release()

    assert "cable chewed by shrew" in caplog.text


@pytest.mark.parametrize("body", [None, 5, "hi", {"message": "hi"}],
                         ids=["null", "number", "string", "object"])
def test_answer_that_isnt_a_list_returns_none(installed, github, body):
    # Something between us and GitHub (a proxy, a captive portal) can
    # answer 200 with JSON that has nothing to do with releases.
    installed.return_value = "2026.11.10"
    github.return_value = make_response(json.dumps(body))

    assert updates.get_latest_release() is None


def test_positional_arguments_are_refused():
    # get_latest_release(True) would have slipped True in as the cache
    # timeout, and nobody wants to wait True hours for an update.
    with pytest.raises(TypeError):
        updates.get_latest_release(True)


def test_malformed_installed_version_raises(installed, github):
    installed.return_value = "not-a-version"

    with pytest.raises(ValueError):
        updates.get_latest_release()


# The cache

def test_answer_is_cached(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.12.1", "v2026.12.5-beta")

    updates.get_latest_release()

    cached = json.loads(cache_file.read_text())
    assert cached["upstream_version"] == "2026.12.1"
    assert cached["upstream_url"] == page("v2026.12.1")
    assert time.time() - cached["timestamp"] < 60


def test_up_to_date_answer_is_cached_too(installed, github, cache_file):
    # "Nothing new" is still an answer, and the whole point is not asking
    # GitHub the same question every launch.
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.11.10")

    assert updates.get_latest_release() is None
    assert json.loads(cache_file.read_text())["upstream_version"] == "2026.11.10"


@pytest.mark.parametrize("failure", [
    {"side_effect": requests.ConnectionError("offline")},
    {"return_value": make_response({"message": "rate limited"}, status_code=403)},
    {"return_value": make_response([])},
], ids=["offline", "github error", "no releases"])
def test_failed_check_is_not_cached(installed, github, cache_file, failure):
    # A failed check must not count as a check, or one offline launch
    # would hide updates for 12 hours.
    installed.return_value = "2026.11.10"
    github.configure_mock(**failure)

    updates.get_latest_release()

    assert not cache_file.exists()


def test_fresh_cache_skips_github(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.1")

    assert updates.get_latest_release() == ("2026.12.1", page("v2026.12.1"))
    github.assert_not_called()


def test_fresh_cache_is_compared_with_the_running_version(installed, github, cache_file):
    # Cached 2026.12.1, then the user updated to it. The cache is still
    # fresh, but there's nothing left to announce.
    installed.return_value = "2026.12.1"
    write_cache(cache_file, "2026.12.1")

    assert updates.get_latest_release() is None
    github.assert_not_called()


def test_force_fetch_ignores_a_fresh_cache(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.1")
    github.return_value = releases("v2026.12.3")

    assert updates.get_latest_release(force_fetch=True) == ("2026.12.3", page("v2026.12.3"))
    assert json.loads(cache_file.read_text())["upstream_version"] == "2026.12.3"


def test_stale_cache_asks_github_again(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.1", age=timedelta(hours=13))
    github.return_value = releases("v2026.12.3")

    assert updates.get_latest_release() == ("2026.12.3", page("v2026.12.3"))


def test_cache_timeout_is_honoured(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.1", age=timedelta(hours=2))
    github.return_value = releases("v2026.12.3")

    assert updates.get_latest_release(cache_timeout=timedelta(hours=1)) == ("2026.12.3", page("v2026.12.3"))


def test_cache_from_the_future_is_ignored(installed, github, cache_file):
    # Written while the clock thought it was tomorrow. Trusting it would
    # mute the check until tomorrow actually shows up.
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.1", age=-timedelta(hours=1))
    github.return_value = releases("v2026.12.3")

    assert updates.get_latest_release() == ("2026.12.3", page("v2026.12.3"))


def test_cached_beta_is_ignored_when_betas_are_off(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.9b0", url=page("v2026.12.9-beta"))
    github.return_value = releases("v2026.12.9-beta", "v2026.12.3")

    assert updates.get_latest_release() == ("2026.12.3", page("v2026.12.3"))


def test_cached_beta_is_used_when_betas_are_on(installed, github, cache_file):
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2026.12.9b0", url=page("v2026.12.9-beta"))

    assert updates.get_latest_release(prerelease=True) == ("2026.12.9b0", page("v2026.12.9-beta"))
    github.assert_not_called()


@pytest.mark.parametrize("contents", [
    "",
    "{",
    "[1, 2]",
    json.dumps({"upstream_version": "2026.12.1", "upstream_url": "u"}),
    json.dumps({"timestamp": "yesterday", "upstream_version": "2026.12.1", "upstream_url": "u"}),
    json.dumps({"timestamp": 1e20, "upstream_version": "2026.12.1", "upstream_url": "u"}),
    json.dumps({"timestamp": -1e12, "upstream_version": "2026.12.1", "upstream_url": "u"}),
    json.dumps({"timestamp": time.time(), "upstream_version": "garbage", "upstream_url": "u"}),
    json.dumps({"timestamp": time.time(), "upstream_version": "2026.12.1"}),
], ids=["empty", "half written", "list", "no timestamp", "text timestamp",
        "year 3 billion", "long ago", "bad version", "no url"])
def test_damaged_cache_asks_github_again(installed, github, cache_file, contents):
    # A cache that makes no sense is no cache at all. Ask again, and
    # write a sane one over it.
    installed.return_value = "2026.11.10"
    cache_file.write_text(contents)
    github.return_value = releases("v2026.12.3")

    assert updates.get_latest_release() == ("2026.12.3", page("v2026.12.3"))
    assert json.loads(cache_file.read_text())["upstream_version"] == "2026.12.3"


def test_cached_version_with_no_page_doesnt_leak_into_the_fetch(installed, github, cache_file):
    # A cache with a version but a null URL triggers a fetch. The cached
    # 2027.1.1 must not sit there as the bar GitHub's releases have to beat.
    installed.return_value = "2026.11.10"
    write_cache(cache_file, "2027.1.1", url=None, upstream_url=None)
    github.return_value = releases("v2026.12.3")

    assert updates.get_latest_release() == ("2026.12.3", page("v2026.12.3"))


def test_unwritable_cache_still_returns_the_answer(installed, github, tmp_path):
    # Config folder gone missing: the check still answers, it just can't
    # remember it.
    installed.return_value = "2026.11.10"
    github.return_value = releases("v2026.12.3")

    with patch("shrewnut.updates.config_file_path", return_value=tmp_path / "nope" / "update_check.json"):
        assert updates.get_latest_release() == ("2026.12.3", page("v2026.12.3"))
