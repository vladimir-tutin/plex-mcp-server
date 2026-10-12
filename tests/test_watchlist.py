import json
import asyncio
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from modules import mcp
from modules import watchlist as w

GUID = "plex://movie/abc123"
ROW = {"guid": GUID, "title": "Example", "type": "movie", "year": 2020}


class WatchlistTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"PLEX_TOKEN": "configured-token"})
        env.start()
        self.addCleanup(env.stop)

    async def test_home_profile_switch_and_pin(self):
        target = SimpleNamespace(id=42, home=True, protected=True)
        account = Mock(id=1)
        account.users.return_value = [target]
        account.switchHomeUser.return_value = SimpleNamespace(id=42, authenticationToken="profile-token")
        with patch.object(w, "MyPlexAccount", return_value=account):
            with self.assertRaises(ValueError):
                w._home_token(42, None)
            self.assertEqual(w._home_token(42, "1234"), "profile-token")
            account.switchHomeUser.assert_called_once_with(target, pin="1234")

    async def test_shared_friend_and_wrong_identity_rejected(self):
        account = Mock(id=1)
        account.users.return_value = [SimpleNamespace(id=42, home=False)]
        account.switchHomeUser.return_value = SimpleNamespace(id=99, authenticationToken="wrong-token")
        with patch.object(w, "MyPlexAccount", return_value=account):
            with self.assertRaises(ValueError):
                w._home_token(42, None)
            account.switchHomeUser.assert_called_once()
            account.users.return_value = [SimpleNamespace(id=42, home=True, protected=False)]
            account.switchHomeUser.return_value = SimpleNamespace(id=99, authenticationToken="wrong-token")
            with self.assertRaises(ValueError):
                w._home_token(42, None)

    async def test_concurrent_profiles_remain_isolated(self):
        async def page(offset, limit):
            before = w._profile_token.get()
            await asyncio.sleep(0.01)
            self.assertEqual(w._profile_token.get(), before)
            return [{"title": before}], 1
        with patch.object(w, "_home_token", side_effect=lambda user, pin: str(user)), patch.object(w, "_page", side_effect=page):
            results = await asyncio.gather(w.watchlist_list(include_state=False, home_user_id=42), w.watchlist_list(include_state=False, home_user_id=43))
            self.assertEqual([json.loads(r)["items"][0]["title"] for r in results], ["42", "43"])
            self.assertIsNone(w._profile_token.get())
            self.assertEqual(os.environ["PLEX_TOKEN"], "configured-token")

    async def test_home_switch_failure_does_not_fall_back(self):
        with patch.object(w, "_home_token", side_effect=ValueError("Profile unavailable")), patch.object(w, "_request", AsyncMock()) as request:
            result = json.loads(await w.watchlist_add(GUID, home_user_id=42))
            self.assertEqual(result["status"], "error")
            request.assert_not_awaited()

    async def test_username_selects_profile_for_all_tools(self):
        account = Mock(id=1, username="admin", title="Admin")
        target = SimpleNamespace(id=42, username=None, title="Eric", protected=False)
        account.users.return_value = [target]
        account.switchHomeUser.return_value = SimpleNamespace(id=42, authenticationToken="profile-token")
        with patch.object(w, "MyPlexAccount", return_value=account):
            self.assertEqual(w._home_token(None, None, username="eric"), "profile-token")
            account.switchHomeUser.assert_called_once_with(target, pin=None)
        with patch.object(w, "_home_token", side_effect=ValueError("Plex denied access")) as select, patch.object(w, "_request", AsyncMock()) as request:
            calls = [w.watchlist_list(include_state=False, username="Eric"), w.watchlist_search("Example", username="Eric"),
                     w.watchlist_add(GUID, username="Eric"), w.watchlist_remove(GUID, username="Eric")]
            for call in calls:
                result = json.loads(await call)
                self.assertEqual(result, {"status": "error", "message": "Plex denied access"})
            self.assertEqual(select.call_count, 4)
            select.assert_called_with(None, None, username="Eric")
            request.assert_not_awaited()

    async def test_registration(self):
        names = {tool.name for tool in await mcp.list_tools()}
        self.assertTrue({"watchlist_list", "watchlist_search", "watchlist_add", "watchlist_remove"} <= names)

    async def test_list_pagination(self):
        with patch.object(w, "_request", AsyncMock(return_value={"MediaContainer": {"Metadata": [ROW], "totalSize": 51}})) as request:
            result = json.loads(await w.watchlist_list(include_state=False, offset=50, limit=1))
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
            self.assertEqual(json.loads(await w.watchlist_list(include_state=False, limit=0))["status"], "error")
            self.assertEqual(json.loads(await w.watchlist_search("", limit=1))["status"], "error")
            request.assert_not_awaited()

    async def test_upstream_errors_do_not_expose_credentials(self):
        with patch.object(w, "_page", AsyncMock(side_effect=RuntimeError("https://plex.test?X-Plex-Token=secret"))):
            result = await w.watchlist_list(include_state=False, )
            self.assertNotIn("secret", result)
            self.assertEqual(json.loads(result)["status"], "error")
