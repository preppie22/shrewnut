"""Checks GitHub for a newer Shrewnut release.

Attributes:
    RELEASES_URL (str): GitHub API address that lists Shrewnut's releases,
        newest first, 30 to a page. Drafts are left out. The release
        workflow never marks a release as a pre-release on GitHub, so
        betas are only told apart by their tags.
"""

import requests
from importlib import metadata
import logging
from packaging.version import Version, InvalidVersion
import time
from datetime import datetime, timedelta
import json

from PySide6.QtCore import (
    QThread,
    Signal
)

from shrewnut.constants import HTTP_TIMEOUT
from shrewnut.paths import ConfigFile, config_file_path

log = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/preppie22/shrewnut/releases"

class UpdateCheckFailed(Exception):
    """GitHub couldn't be asked, or its answer wasn't a list of releases."""
    pass

class FetchAppUpdate(QThread):
    """Runs ``get_latest_release`` off the GUI thread.

    One instance is reused for every check: set ``cache_timeout``,
    ``prerelease`` and ``force_fetch``, then call ``start()``. Each run
    emits exactly one of the two signals.

    Attributes:
        fetched_update (Signal(str, str)): Emitted when the check worked,
            with the newer release's version and page URL, or two empty
            strings if nothing newer was found.
        error (Signal(str)): Emitted instead of ``fetched_update`` when the
            check failed, with the reason.
        prerelease (bool): Whether betas count on the next run.
        force_fetch (bool): Whether the next run asks GitHub even if the
            cache is fresh.
    """
    fetched_update = Signal(str, str)
    error = Signal(str)

    def __init__(self, *, cache_timeout: timedelta = timedelta(hours=12), prerelease: bool = False, force_fetch: bool = False, parent = None):
        """Create the thread with the settings for its first run.

        Args:
            cache_timeout (timedelta, optional): How long a cached answer
                is used. Defaults to 12 hours.
            prerelease (bool, optional): Whether betas count. Defaults to
                False.
            force_fetch (bool, optional): Ask GitHub even if the cache is
                fresh. Defaults to False.
            parent (QObject, optional): Owner of the thread.
        """
        super().__init__(parent)
        self._cache_timeout = cache_timeout
        self.prerelease = prerelease
        self.force_fetch = force_fetch

    @property
    def cache_timeout(self):
        """timedelta: How long a cached answer is used on the next run.

        Set it in hours, as the ``check_update_hours`` setting stores it.
        """
        return self._cache_timeout

    @cache_timeout.setter
    def cache_timeout(self, value: int):
        self._cache_timeout = timedelta(hours=value)

    def run(self):
        """Run the check and emit its result, or the reason it failed."""
        try:
            release_data = get_latest_release(cache_timeout=self._cache_timeout, prerelease=self.prerelease, force_fetch=self.force_fetch)
        except (UpdateCheckFailed, ValueError) as e:
            self.error.emit(str(e))
            return
        if release_data:
            self.fetched_update.emit(release_data[0], release_data[1])
            return
        self.fetched_update.emit("", "")

def get_latest_release(*, cache_timeout: timedelta = timedelta(hours=12), prerelease: bool = False, force_fetch: bool = False) -> tuple[str, str] | None:
    """Find out whether GitHub has a newer release than the one running.

    GitHub's answer is cached in ``update_check.json`` in the config
    directory. While the cache is younger than ``cache_timeout``, the
    cached release is compared with the running version and GitHub isn't
    asked. A cache that is old, unreadable, dated in the future, or holds
    a beta while betas are off is ignored, and GitHub is asked again.

    Asking GitHub makes one request, without logging in, and looks at the
    30 newest releases. Tags are read as PEP 440 versions, so
    ``v2026.10.30-beta`` matches an installed ``2026.10.30b0``, and a beta
    is older than the stable release of the same date. The highest
    version wins, whatever order GitHub lists them in. A release whose
    tag isn't a version, or that has no page URL, is skipped and logged.
    Only an answer with at least one usable release is cached. Being
    offline, an error from GitHub (such as its hourly limit) or an answer
    that isn't a list of releases is logged and raises
    ``UpdateCheckFailed``. An answer with no usable releases at all
    returns None.

    Args:
        cache_timeout (timedelta, optional): How long a cached answer is
            used before GitHub is asked again. Defaults to 12 hours.
        prerelease (bool, optional): Whether betas count. If False, only
            stable releases are compared. Defaults to False.
        force_fetch (bool, optional): Ask GitHub even if the cache is
            fresh. Defaults to False.

    Returns:
        tuple[str, str] | None: The newer release's version and the URL
        of its release page, or None if the running version is the same
        or newer.

    Raises:
        UpdateCheckFailed: If GitHub couldn't be asked or its answer
            wasn't a list of releases. A failed request is kept as the
            cause.
        ValueError: If the installed Shrewnut's own version isn't a valid
            PEP 440 version.
    """
    release_version = None
    html_url = None
    try:
        current_version = Version(metadata.version("shrewnut"))
    except InvalidVersion:
        log.error("malformed project version", exc_info=True)
        raise ValueError("version string in project metadata is malformed")
    if not force_fetch:
        cached_release = _cached_release(cache_timeout, prerelease)
        if cached_release is not None:
            release_version, html_url = cached_release
    if release_version is None or html_url is None:
        release_version = None
        html_url = None
        try:
            response = requests.get(
                RELEASES_URL,
                timeout=HTTP_TIMEOUT
            )
            response.raise_for_status()
            releases = response.json()
            if not isinstance(releases, list):
                log.warning("unexpected response from GitHub api")
                raise UpdateCheckFailed("Unexpected response from GitHub api")
        except requests.RequestException as e:
            log.warning(f"could not fetch release: {str(e)}")
            raise UpdateCheckFailed(str(e)) from e
        for release in releases:
            try:
                version = Version(release['tag_name'])
                url = release['html_url']
                if (release_version is None or version > release_version) and (prerelease or not version.is_prerelease):
                    release_version = version
                    html_url = url
            except (KeyError, InvalidVersion, TypeError) as e:
                log.warning(f"unexpected release info from GitHub: {str(e)}")
                continue
        if release_version is None:
            log.debug("no valid upstream releases found")
            return None
        _update_last_checked(release_version, html_url)
    if current_version < release_version:
        log.info(f"current: {current_version} upstream: {release_version}")
        return str(release_version), html_url
    log.debug("program up to date")
    return None

def _update_last_checked(version: Version, url: str):
    """Cache GitHub's newest release with the current time.

    The file is overwritten directly rather than through a temp file. A
    file damaged by a crash mid-write only costs one extra check, since
    ``_cached_release`` ignores it. A failed write is logged.

    Args:
        version (Version): The newest release GitHub listed.
        url (str): The URL of that release's page.
    """
    update_check_file = config_file_path(ConfigFile.UPDATE_CHECK)
    update_metadata = {
        'timestamp': time.time(),
        'upstream_version': str(version),
        'upstream_url': url
    }
    try:
        with open(update_check_file, 'w') as wp:
            json.dump(update_metadata, wp)
    except OSError as e:
        log.warning(f"cannot open {update_check_file.name}: {str(e)}")
        return

def _cached_release(timeout: timedelta, prerelease: bool) -> tuple[Version, str] | None:
    """Read the cached release, if it's still fresh enough to use.

    Args:
        timeout (timedelta): How old the cache may be.
        prerelease (bool): Whether betas count. If False, a cached beta
            isn't used.

    Returns:
        tuple[Version, str] | None: The cached release's version and page
        URL, or None if there is no cache, it can't be read or is
        missing a field, it's older than ``timeout`` or dated in the
        future, or it holds a beta while betas are off. Problems other
        than a missing file are logged.
    """
    update_check_file = config_file_path(ConfigFile.UPDATE_CHECK)
    update_metadata = None
    last_checked = None
    try:
        with open(update_check_file, 'r') as rp:
            update_metadata = json.load(rp)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning(f"could not read {update_check_file.name}: {str(e)}")
        return None
    try:
        last_checked = datetime.fromtimestamp(update_metadata['timestamp'])
        version = Version(update_metadata['upstream_version'])
        url = update_metadata['upstream_url']
    except Exception as e:
        log.info(f"invalid update cache: {str(e)}")
        return None
    time_now = datetime.now()
    if time_now > last_checked + timeout or last_checked > time_now or (not prerelease and version.is_prerelease):
        return None
    return version, url


