import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from modules import mcp, library, media
from modules.profiles import ProfileAccessError


class MediaProfileTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, name, args):
        content, _ = await mcp.call_tool(name, args)
        return json.loads(content[0].text)

    async def test_library_requests_use_selected_token_including_show_details(self):
        selected = SimpleNamespace(_baseurl="http://plex.test/", _token="selected-token")
        responses = [
            {"MediaContainer": {"Directory": [{"title": "TV", "key": "1", "type": "show"}]}},
            {"MediaContainer": {"Metadata": [{"ratingKey": "42", "title": "Example"}], "size": 1}},
            {"MediaContainer": {"Metadata": [{"leafCount": 3, "viewedLeafCount": 1}]}},
        ]
        with patch.object(library, "connect_to_plex") as connect, patch.object(
            library, "server_for_user", return_value=selected
        ) as resolve, patch.object(library, "async_get_json", AsyncMock(side_effect=responses)) as request:
            result = await self.call("library_get_contents", {"library_name": "TV", "watched": True, "username": "Target"})
            resolve.assert_called_once_with(connect.return_value, username="Target")
            self.assertEqual(result["items"][0]["watchStatus"], "partial")
            self.assertEqual(len(request.await_args_list), 3)
            for call in request.await_args_list:
                self.assertEqual(call.args[2]["X-Plex-Token"], "selected-token")

    async def test_media_details_by_id_and_title_use_selected_account(self):
        item = SimpleNamespace(type="movie", title="Example", ratingKey=42, viewCount=2,
                               viewOffset=1500, duration=3000, userRating=8)
        selected = Mock()
        selected.fetchItem.return_value = item
        selected.search.return_value = [item]
        for args in ({"media_id": 42}, {"media_title": "Example"}):
            with self.subTest(args=args), patch.object(media, "connect_to_plex") as connect, patch.object(
                media, "server_for_user", return_value=selected
            ) as resolve:
                result = await self.call("media_get_details", dict(args, username="Target"))
                resolve.assert_called_once_with(connect.return_value, username="Target")
                self.assertEqual(result["progress_percent"], 50)
                self.assertTrue(result["watched"])
                self.assertEqual(result["view_count"], 2)
                self.assertEqual(result["playback_offset_ms"], 1500)
                self.assertEqual(result["rating"], 8)
                connect.return_value.fetchItem.assert_not_called()

    async def test_failed_selection_returns_error_without_reading_owner(self):
        for module, name, args in ((library, "library_get_contents", {"library_name": "Movies"}),
                                   (media, "media_get_details", {"media_id": 42})):
            with patch.object(module, "connect_to_plex") as connect, patch.object(
                module, "server_for_user", side_effect=ProfileAccessError("User unavailable")
            ), patch.object(library, "async_get_json", AsyncMock()) as request:
                result = await self.call(name, dict(args, username="Unknown"))
                self.assertIn("User unavailable", result["error"])
                request.assert_not_called()
                connect.return_value.fetchItem.assert_not_called()

    def test_saved_progress_is_independent_of_watched_and_handles_missing_duration(self):
        for offset, duration, expected in ((0, 1000, 0), (500, 1000, 50), (2000, 1000, 100), (500, None, None)):
            item = SimpleNamespace(type="episode", viewCount=0, viewOffset=offset, duration=duration)
            result = media.get_media_details(item)
            self.assertFalse(result["watched"])
            self.assertEqual(result["in_progress"], offset > 0)
            self.assertEqual(result["progress_percent"], expected)
