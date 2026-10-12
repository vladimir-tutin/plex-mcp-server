import json
import unittest
from unittest.mock import AsyncMock, patch

from modules import mcp
from modules import watchlist as w

GUID = "plex://movie/abc123"
ROW = {"guid": GUID, "title": "Example", "type": "movie", "year": 2020}


class WatchlistTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration(self):
        names = {tool.name for tool in await mcp.list_tools()}
        self.assertTrue({"watchlist_list", "watchlist_search", "watchlist_add", "watchlist_remove"} <= names)

    async def test_list_pagination(self):
        with patch.object(w, "_request", AsyncMock(return_value={"MediaContainer": {"Metadata": [ROW], "totalSize": 51}})) as request:
            result = json.loads(await w.watchlist_list(offset=50, limit=1))
            self.assertEqual(result["items"], [ROW])
            self.assertEqual(result["totalItems"], 51)
            self.assertEqual(request.call_args.args[2]["X-Plex-Container-Start"], 50)

    async def test_search_external_titles(self):
        data = {"MediaContainer": {"SearchResults": [{"id": "external", "SearchResult": [{"Metadata": ROW}]}]}}
        with patch.object(w, "_request", AsyncMock(return_value=data)):
            self.assertEqual(json.loads(await w.watchlist_search("Example"))["items"], [ROW])

    async def test_membership_on_second_page(self):
        with patch.object(w, "_page", AsyncMock(side_effect=[([{"guid": "other"}], 2), ([ROW], 2)])):
            self.assertTrue(await w._contains(GUID))

    async def test_incomplete_page_does_not_claim_absence(self):
        with patch.object(w, "_page", AsyncMock(return_value=([], 1))):
            with self.assertRaises(ValueError):
                await w._contains(GUID)

    async def test_add_and_remove_confirm_state(self):
        for desired, tool, action in [(True, w.watchlist_add, "addToWatchlist"), (False, w.watchlist_remove, "removeFromWatchlist")]:
            with self.subTest(desired=desired), patch.object(w, "_contains", AsyncMock(side_effect=[not desired, desired])), patch.object(w, "_request", AsyncMock()) as request:
                result = json.loads(await tool(GUID))
                self.assertTrue(result["changed"])
                self.assertEqual(result["watchlisted"], desired)
                request.assert_awaited_once_with("PUT", "/actions/" + action, {"ratingKey": "abc123"})

    async def test_idempotent_operations_do_not_write(self):
        for state, tool in [(True, w.watchlist_add), (False, w.watchlist_remove)]:
            with patch.object(w, "_contains", AsyncMock(return_value=state)), patch.object(w, "_request", AsyncMock()) as request:
                self.assertFalse(json.loads(await tool(GUID))["changed"])
                request.assert_not_awaited()

    async def test_unconfirmed_write_is_error(self):
        with patch.object(w, "_contains", AsyncMock(return_value=False)), patch.object(w, "_request", AsyncMock()), patch.object(w.asyncio, "sleep", AsyncMock()):
            self.assertEqual(json.loads(await w.watchlist_add(GUID))["status"], "error")

    async def test_invalid_inputs_do_not_request(self):
        with patch.object(w, "_request", AsyncMock()) as request:
            for guid in ["123", "plex://episode/abc", "plex://movie/../../token", "https://evil.test"]:
                self.assertEqual(json.loads(await w.watchlist_add(guid))["status"], "error")
            self.assertEqual(json.loads(await w.watchlist_list(limit=0))["status"], "error")
            self.assertEqual(json.loads(await w.watchlist_search("", limit=1))["status"], "error")
            request.assert_not_awaited()

    async def test_upstream_errors_do_not_expose_credentials(self):
        with patch.object(w, "_page", AsyncMock(side_effect=RuntimeError("https://plex.test?X-Plex-Token=secret"))):
            result = await w.watchlist_list()
            self.assertNotIn("secret", result)
            self.assertEqual(json.loads(result)["status"], "error")
