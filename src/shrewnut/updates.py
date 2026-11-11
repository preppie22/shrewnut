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

from shrewnut.constants import HTTP_TIMEOUT

log = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/preppie22/shrewnut/releases"

def get_latest_release(prerelease: bool = False) -> tuple[str, str] | None:
    """Find out whether GitHub has a newer release than the one running.

    Makes one request to the GitHub API, without logging in, and looks at
    the 30 newest releases. Tags are read as PEP 440 versions, so
    ``v2026.10.30-beta`` matches an installed ``2026.10.30b0``, and a beta
    is older than the stable release of the same date. The highest
    version wins, whatever order GitHub lists them in. A release whose
    tag isn't a version, or that has no page URL, is skipped and logged.
    Being offline or an error from GitHub (such as its hourly limit)
    returns None instead of raising, and is logged.

    Args:
        prerelease (bool, optional): Whether betas count. If False, only
            stable releases are compared. Defaults to False.

    Returns:
        tuple[str, str] | None: The newer release's version and the URL
        of its release page, or None if the running version is the same
        or newer, or the check failed.
    """
    try:
        response = requests.get(
            RELEASES_URL,
            timeout=HTTP_TIMEOUT
        )
        response.raise_for_status()
        releases = response.json()
    except requests.RequestException as e:
        log.warning(f"could not fetch release: {str(e)}")
        return None
    try:
        current_version = Version(metadata.version("shrewnut"))
    except InvalidVersion:
        log.error("malformed project version", exc_info=True)
        return None
    release_version = None
    html_url = None
    for release in releases:
        try:
            version = Version(release['tag_name'])
            url = release['html_url']
            if (release_version is None or version > release_version) and (prerelease or not version.is_prerelease):
                release_version = version
                html_url = url
        except (KeyError, InvalidVersion) as e:
            log.warning(f"unexpected release info from GitHub: {str(e)}")
            continue
    if release_version is None:
        log.debug("no valid upstream releases found")
        return None
    if current_version < release_version:
        log.info(f"current: {current_version} upstream: {release_version}")
        return str(release_version), html_url
    log.debug("program up to date")
    return None