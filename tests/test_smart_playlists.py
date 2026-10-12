import json
import unittest
from unittest.mock import Mock, patch

from modules import mcp, playlist
from modules.profiles import ProfileAccessError


class SmartPlaylistTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, name, args):
        content, _ = await mcp.call_tool(name, args)
        return json.loads(content[0].text)

    async def test_edit_preserves_type_filters_sort_and_limit_when_omitted(self):
        selected = Mock()
        target = Mock(smart=True, ratingKey=42, key="/playlists/42")
        definition = {"libtype": "show", "filters": {"show.title": "Band of Brothers"},
                      "sort": ["show.titleSort:asc"], "limit": 3}
        target.filters.return_value = definition
        selected.playlists.return_value = [target]
        selected._uriRoot.return_value = "server://example/com.plexapp.plugins.library"
        section = target.section.return_value
        section._buildSearchKey.return_value = "/library/sections/1/all?type=2"
        with patch.object(playlist, "connect_to_plex"), patch.object(playlist, "server_for_user", return_value=selected), patch.object(playlist, "_smart_result", return_value={"status": "success"}):
            result = await self.call("playlist_edit_smart_filters", {"playlist_id": 42, "username": "Target"})
            self.assertEqual(result["status"], "success")
            section._buildSearchKey.assert_called_once_with(libtype="show", filters=definition["filters"], sort=definition["sort"], limit=3)
            target.updateFilters.assert_not_called()
            result = await self.call("playlist_edit_smart_filters", {"playlist_id": 42, "username": "Target", "filters": {}, "sort": "", "limit": 0, "libtype": "episode"})
            section._buildSearchKey.assert_called_with(libtype="episode", filters={}, sort=None, limit=None)

    async def test_all_tools_report_user_access_failures(self):
        calls = {
            "playlist_get_smart_filter_options": {"library_name": "Movies"},
            "playlist_create_smart": {"library_name": "Movies", "playlist_title": "Test"},
            "playlist_edit_smart_filters": {"playlist_id": 42},
        }
        for name, args in calls.items():
            with self.subTest(tool=name), patch.object(playlist, "connect_to_plex"), patch.object(playlist, "server_for_user", side_effect=ProfileAccessError("User unavailable")):
                result = await self.call(name, dict(args, username="Unknown"))
                self.assertEqual(result, {"status": "error", "message": "User unavailable"})

    async def test_summary_failure_does_not_claim_complete_success(self):
        selected = Mock()
        selected.createPlaylist.return_value.ratingKey = 42
        selected.createPlaylist.return_value.editSummary.side_effect = RuntimeError("failed")
        with patch.object(playlist, "connect_to_plex"), patch.object(playlist, "server_for_user", return_value=selected):
            result = await self.call("playlist_create_smart", {"playlist_title": "Test", "library_name": "Movies", "summary": "Example"})
            self.assertEqual(result["status"], "error")
            self.assertTrue(result["created"])
            self.assertEqual(result["playlist_id"], 42)

    async def test_regular_playlist_is_not_modified(self):
        selected = Mock()
        selected.playlists.return_value = [Mock(smart=False, ratingKey=42)]
        with patch.object(playlist, "connect_to_plex"), patch.object(playlist, "server_for_user", return_value=selected):
            result = await self.call("playlist_edit_smart_filters", {"playlist_id": 42})
            self.assertEqual(result["status"], "error")
            selected.query.assert_not_called()
