import json
import logging
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
