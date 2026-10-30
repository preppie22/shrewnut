from unittest.mock import MagicMock, patch

import pytest
import requests

from shrewnut import gog_api
from shrewnut.constants import HTTP_TIMEOUT, HTTP_TIMEOUT_SHORT


FAKE_TOKEN = {"access_token": "mytoken"}


def make_response(json_data, status_code=200):
    response = MagicMock()
    response.json.return_value = json_data
    response.status_code = status_code  # a bare MagicMock's status_code is a MagicMock, which is never 200
    # A bare MagicMock is truthy for everything, so it would "redirect" every time
    response.is_redirect = False
    return response


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_owned_ids_returns_owned_list_as_a_set(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response({"owned": [1207658695, 1456702644, 1293681291]})

    result = gog_api.fetch_owned_ids()

    assert mock_get.call_count == 1
    args, kwargs = mock_get.call_args
    assert args[0] == gog_api.USER_GAMES
    assert kwargs["headers"] == {"Authorization": "Bearer mytoken"}
    assert kwargs["allow_redirects"] is False
    # Without a timeout, a CDN that goes quiet holds the thread hostage
    # forever (#29). requests has no default; it will wait until the heat
    # death of the universe if asked politely enough.
    assert kwargs["timeout"] == HTTP_TIMEOUT
    assert result == {1207658695, 1456702644, 1293681291}


@patch("shrewnut.gog_api.gog_auth.clear_token")
@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_owned_ids_treats_login_redirect_as_auth_failure(mock_get_valid_token, mock_get, mock_clear_token):
    # GOG doesn't say 401, it just shows you the door: 302 to /en##openlogin
    mock_get_valid_token.return_value = FAKE_TOKEN
    response = make_response({})
    response.is_redirect = True
    mock_get.return_value = response

    with pytest.raises(gog_api.AuthenticationFailure):
        gog_api.fetch_owned_ids()

    mock_clear_token.assert_called_once_with()
    response.json.assert_not_called()


@patch("shrewnut.gog_api.gog_auth.clear_token")
@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_a_rejected_token_says_so_in_the_log(mock_get_valid_token, mock_get, mock_clear_token, caplog):
    # Not logged in and logged in with a token GOG has stopped liking raise
    # the same exception. The log is where the two part ways.
    mock_get_valid_token.return_value = FAKE_TOKEN
    response = make_response({})
    response.is_redirect = True
    mock_get.return_value = response

    with caplog.at_level("INFO", logger="shrewnut.gog_api"):
        with pytest.raises(gog_api.AuthenticationFailure):
            gog_api.fetch_owned_ids()

    [record] = caplog.records
    assert record.levelname == "WARNING"
    assert "mytoken" not in record.getMessage()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_owned_ids_returns_empty_set_for_an_empty_library(mock_get_valid_token, mock_get):
    # Owning nothing is a lifestyle choice, not an error
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response({"owned": []})

    assert gog_api.fetch_owned_ids() == set()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_owned_ids_raises_on_http_error_status(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    response = make_response({})
    response.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
    mock_get.return_value = response

    with pytest.raises(requests.HTTPError):
        gog_api.fetch_owned_ids()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_owned_ids_raises_when_owned_key_is_missing(mock_get_valid_token, mock_get):
    # A 200 with no "owned" list must not pass for an empty library and wipe the cache
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response({"error": "nope"})

    with pytest.raises(KeyError):
        gog_api.fetch_owned_ids()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_owned_ids_raises_auth_failure_when_not_logged_in(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = None

    with pytest.raises(gog_api.AuthenticationFailure):
        gog_api.fetch_owned_ids()

    mock_get.assert_not_called()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_get_downloadable_single_batch_under_50(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response([{"id": 1}, {"id": 2}, {"id": 3}])

    result = gog_api.fetch_downloadables([1, 2, 3])

    assert mock_get.call_count == 1
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["ids"] == "1,2,3"
    assert kwargs["params"]["expand"] == "downloads"
    assert kwargs["headers"] == {"Authorization": "Bearer mytoken"}
    assert kwargs["timeout"] == HTTP_TIMEOUT
    assert result == [{"id": 1}, {"id": 2}, {"id": 3}]


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_get_downloadable_splits_into_chunks_of_50(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    ids = list(range(1, 121))  # 120 ids -> chunks of 50, 50, 20
    mock_get.side_effect = [
        make_response([{"id": "from-batch-1"}]),
        make_response([{"id": "from-batch-2"}]),
        make_response([{"id": "from-batch-3"}]),
    ]

    result = gog_api.fetch_downloadables(ids)

    assert mock_get.call_count == 3
    sent_ids = [call.kwargs["params"]["ids"] for call in mock_get.call_args_list]
    assert sent_ids[0] == ",".join(str(i) for i in range(1, 51))
    assert sent_ids[1] == ",".join(str(i) for i in range(51, 101))
    assert sent_ids[2] == ",".join(str(i) for i in range(101, 121))
    assert result == [
        {"id": "from-batch-1"},
        {"id": "from-batch-2"},
        {"id": "from-batch-3"},
    ]


@pytest.mark.parametrize("status_code", [302, 500])
@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_a_failed_batch_raises_instead_of_passing_for_a_finished_library(mock_get_valid_token, mock_get, caplog, status_code):
    # Returning what it had would let a refresh "succeed" with half a library,
    # or none of it. 302 counts too: raise_for_status() waves redirects through.
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.side_effect = [
        make_response([{"id": "from-batch-1"}]),
        make_response({"error": "nope"}, status_code=status_code),
    ]

    with caplog.at_level("INFO", logger="shrewnut.gog_api"):
        with pytest.raises(requests.HTTPError) as raised:
            gog_api.fetch_downloadables(list(range(1, 121)))

    assert mock_get.call_count == 2  # and not a third, there's no point
    assert raised.value.response.status_code == status_code
    assert str(status_code) in str(raised.value)
    [record] = caplog.records
    assert str(status_code) in record.getMessage()
    assert "50" in record.getMessage()  # how big the batch that failed was
    assert "mytoken" not in record.getMessage()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_get_downloadable_empty_input_makes_no_requests(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN

    result = gog_api.fetch_downloadables([])

    mock_get.assert_not_called()
    assert result == []


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_downloadables_stops_between_batches_when_asked(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response([{"id": "batch"}])
    should_stop = MagicMock(side_effect=[False, True])

    # Raises rather than returning the one batch it got, so nobody caches
    # a library that's 50 games long by accident.
    with pytest.raises(gog_api.FetchInterrupted):
        gog_api.fetch_downloadables(list(range(1, 121)), should_stop=should_stop)

    assert mock_get.call_count == 1


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_downloadables_runs_to_the_end_when_never_asked_to_stop(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response([{"id": "batch"}])

    result = gog_api.fetch_downloadables(list(range(1, 121)), should_stop=lambda: False)

    assert mock_get.call_count == 3
    assert len(result) == 3


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_fetch_downloadables_raises_auth_failure_when_not_logged_in(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = None

    with pytest.raises(gog_api.AuthenticationFailure):
        gog_api.fetch_downloadables([1, 2, 3])

    mock_get.assert_not_called()


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_resolve_downlink_returns_cdn_url_and_checksum(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = FAKE_TOKEN
    mock_get.return_value = make_response({
        "downlink": "https://gog-cdn.example.com/secure/offline/111/setup_fake_game.exe",
        "checksum": "https://gog-cdn.example.com/secure/offline/111/setup_fake_game.exe.xml",
    })

    result = gog_api.resolve_downlink("https://api.gog.com/products/111/downlink/installer/file1")

    assert mock_get.call_count == 1
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.gog.com/products/111/downlink/installer/file1"
    assert kwargs["headers"] == {"Authorization": "Bearer mytoken"}
    assert kwargs["timeout"] == HTTP_TIMEOUT
    assert result == {
        "downlink": "https://gog-cdn.example.com/secure/offline/111/setup_fake_game.exe",
        "checksum": "https://gog-cdn.example.com/secure/offline/111/setup_fake_game.exe.xml",
    }


@patch("shrewnut.gog_api.requests.get")
@patch("shrewnut.gog_api.gog_auth.get_valid_token")
def test_resolve_downlink_raises_auth_failure_when_not_logged_in(mock_get_valid_token, mock_get):
    mock_get_valid_token.return_value = None

    with pytest.raises(gog_api.AuthenticationFailure):
        gog_api.resolve_downlink("https://api.gog.com/products/111/downlink/installer/file1")

    mock_get.assert_not_called()


# --- get_store_url ---

V2 = "https://api.gog.com/v2/games"


def v2_game(product_id, slug, for_sale, included_in=()):
    # Just the parts of a v2/games answer that get_store_url reads. The
    # real thing also carries screenshots, copyrights and a small novel.
    return {
        "_links": {
            "store": {"href": f"https://www.gog.com/en/game/{slug}"},
            "isIncludedInGames": [{"href": f"{V2}/{pid}?locale=en-US"} for pid in included_in],
        },
        "_embedded": {"product": {"id": product_id, "isAvailableForSale": for_sale}},
    }


def answer_with(games):
    # requests.get stand-in that answers from a dict of URL -> JSON, so each
    # test reads like the GOG catalog it's pretending to be.
    def fake_get(url, **kwargs):
        return make_response(games[url])
    return MagicMock(side_effect=fake_get)


def test_get_store_url_uses_the_products_own_page_when_its_on_sale():
    games = {f"{V2}/1752654506": v2_game(1752654506, "bioshock_infinite", for_sale=True)}

    with patch("shrewnut.gog_api.requests.get", answer_with(games)) as mock_get:
        assert gog_api.get_store_url(1752654506) == "https://www.gog.com/en/game/bioshock_infinite"

    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs["timeout"] == HTTP_TIMEOUT_SHORT


def test_get_store_url_follows_packs_to_the_first_one_on_sale():
    # BioShock Remastered, the Amazon Prime copy: its own page and the Prime
    # pack's are both off the shelf, so the shop window is two doors down.
    games = {
        f"{V2}/1439656515": v2_game(1439656515, "bioshock_remastered_game", for_sale=False, included_in=[1157510446, 1269268081]),
        f"{V2}/1157510446?locale=en-US": v2_game(1157510446, "bioshock_remastered_1157510446", for_sale=False),
        f"{V2}/1269268081?locale=en-US": v2_game(1269268081, "bioshock_remastered", for_sale=True),
    }

    with patch("shrewnut.gog_api.requests.get", answer_with(games)):
        assert gog_api.get_store_url(1439656515) == "https://www.gog.com/en/game/bioshock_remastered"


def test_get_store_url_stops_at_the_first_pack_on_sale():
    games = {
        f"{V2}/1": v2_game(1, "old", for_sale=False, included_in=[2, 3]),
        f"{V2}/2?locale=en-US": v2_game(2, "first_pack", for_sale=True),
        f"{V2}/3?locale=en-US": v2_game(3, "second_pack", for_sale=True),
    }

    with patch("shrewnut.gog_api.requests.get", answer_with(games)) as mock_get:
        assert gog_api.get_store_url(1) == "https://www.gog.com/en/game/first_pack"

    assert mock_get.call_count == 2  # the second pack never got a knock on the door


@pytest.mark.parametrize("included_in", [[], [2]])
def test_get_store_url_returns_none_when_nothing_is_on_sale(included_in):
    # Delisted, and every pack it came in is delisted too. No page beats a
    # page that dumps you in the catalog wondering what you clicked.
    games = {
        f"{V2}/1": v2_game(1, "gone", for_sale=False, included_in=included_in),
        f"{V2}/2?locale=en-US": v2_game(2, "also_gone", for_sale=False),
    }

    with patch("shrewnut.gog_api.requests.get", answer_with(games)):
        assert gog_api.get_store_url(1) is None


@pytest.mark.parametrize("error", [requests.ConnectionError(), requests.Timeout()])
def test_get_store_url_returns_none_when_gog_cant_be_reached(error):
    with patch("shrewnut.gog_api.requests.get", side_effect=error):
        assert gog_api.get_store_url(1) is None


def test_get_store_url_returns_none_when_a_pack_cant_be_reached():
    games = {f"{V2}/1": v2_game(1, "old", for_sale=False, included_in=[2])}

    def fake_get(url, **kwargs):
        if url in games:
            return make_response(games[url])
        raise requests.ConnectionError()

    with patch("shrewnut.gog_api.requests.get", side_effect=fake_get):
        assert gog_api.get_store_url(1) is None


def test_get_store_url_returns_none_for_an_html_error_page():
    # A wrong URL gets GOG's 404 page, in HTML. .json() chokes on it, and
    # that has to come out as "no page", not a dead lookup thread.
    response = make_response(None, status_code=404)
    response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "<!DOCTYPE html>", 0)

    with patch("shrewnut.gog_api.requests.get", return_value=response):
        assert gog_api.get_store_url(1) is None


def test_get_store_url_returns_none_when_gogs_answer_is_missing_fields():
    with patch("shrewnut.gog_api.requests.get", return_value=make_response({"error": "not_found"})):
        assert gog_api.get_store_url(1) is None
