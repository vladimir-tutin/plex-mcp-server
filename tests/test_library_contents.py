import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from modules import mcp
from modules.library import library_get_contents


class LibraryContentsTests(unittest.IsolatedAsyncioTestCase):
    async def contents(self, library_type, items, details=(), total=None, **filters):
        responses = [
            {"MediaContainer": {"Directory": [
                {"title": "Test", "key": "2", "type": library_type}
            ]}},
            {"MediaContainer": {
                "Metadata": items, "size": len(items),
                "totalSize": len(items) if total is None else total,
            }},
            *details,
        ]
        plex = SimpleNamespace(_baseurl="http://plex.test:32400/", _token="test")
        with patch("modules.library.connect_to_plex", return_value=plex), patch(
            "modules.library.async_get_json", new_callable=AsyncMock,
            side_effect=responses,
        ) as request:
            result = json.loads(await library_get_contents("Test", **filters))
        self.assertNotIn("error", result)
        return result, request.await_args_list

    async def test_watched_movies_include_ids_and_preserve_pagination(self):
        result, calls = await self.contents(
            "movie", [{"ratingKey": "42", "title": "Movie", "viewCount": 1}],
            total=691, watched=True, offset=5, limit=1, genre="Drama",
        )
        self.assertEqual(result["items"][0]["media_id"], "42")
        self.assertTrue(result["items"][0]["watched"])
        self.assertEqual((result["offset"], result["limit"], result["size"],
                          result["totalItems"]), (5, 1, 1, 691))
        query = parse_qs(urlparse(calls[1].args[1]).query)
        self.assertEqual(query, {"start": ["5"], "size": ["1"],
                                 "unwatched": ["0"], "genre": ["Drama"]})
        self.assertEqual(calls[1].args[2]["X-Plex-Container-Start"], "5")
        self.assertEqual(calls[1].args[2]["X-Plex-Container-Size"], "1")

    async def test_unwatched_movies(self):
        result, calls = await self.contents(
            "movie", [{"ratingKey": "43", "title": "Unplayed"}], unwatched=True,
        )
        self.assertFalse(result["items"][0]["watched"])
        self.assertEqual(parse_qs(urlparse(calls[1].args[1]).query)["unwatched"], ["1"])

    async def test_show_states_include_partial_and_empty(self):
        items = [{"ratingKey": str(i), "title": str(i)} for i in range(4)]
        details = [{"MediaContainer": {"Metadata": [data]}} for data in [
            {"leafCount": 8, "viewedLeafCount": 0},
            {"leafCount": 8, "viewedLeafCount": 3},
            {"leafCount": 8, "viewedLeafCount": 8},
            {},
        ]]
        result, calls = await self.contents("show", items, details)
        self.assertEqual([x["watchStatus"] for x in result["items"]],
                         ["unwatched", "partial", "watched", "unwatched"])
        self.assertEqual([x["watched"] for x in result["items"]],
                         [False, False, True, False])
        self.assertEqual([x["watchedEpisodeCount"] for x in result["items"]], [0, 3, 8, 0])
        self.assertEqual([x["media_id"] for x in result["items"]], ["0", "1", "2", "3"])
        self.assertNotIn("unwatched", parse_qs(urlparse(calls[1].args[1]).query))

    async def test_watched_show_filter_retains_partial_shows_and_total(self):
        result, calls = await self.contents(
            "show", [{"ratingKey": "99", "title": "Partial"}],
            [{"MediaContainer": {"Metadata": [{"leafCount": 10, "viewedLeafCount": 2}]}}],
            total=339, watched=True, offset=2, limit=1,
        )
        self.assertEqual(result["items"][0]["watchStatus"], "partial")
        self.assertFalse(result["items"][0]["watched"])
        self.assertEqual(result["totalItems"], 339)
        self.assertEqual(result["size"], 1)
        self.assertEqual(parse_qs(urlparse(calls[1].args[1]).query)["unwatched"], ["0"])

    async def test_conflicting_filters_rejected_before_connection(self):
        with patch("modules.library.connect_to_plex") as connect:
            result = json.loads(await library_get_contents("Test", watched=True, unwatched=True))
        self.assertIn("cannot both be true", result["error"])
        connect.assert_not_called()

    async def test_same_name_artists_keep_distinct_ids_and_tracks(self):
        result, _ = await self.contents(
            "artist", [{"ratingKey": "10", "title": "Same"},
                       {"ratingKey": "11", "title": "Same"}],
            [{"MediaContainer": {"Metadata": [{"parentTitle": "Album", "viewCount": 2}]}},
             {"MediaContainer": {"Metadata": []}}],
        )
        self.assertEqual([x["media_id"] for x in result["items"]], ["10", "11"])
        self.assertEqual([x["trackCount"] for x in result["items"]], [1, 0])
        self.assertEqual([x["viewCount"] for x in result["items"]], [2, 0])

    async def test_other_library_types_include_id(self):
        result, _ = await self.contents("photo", [{"ratingKey": "77", "title": "Photo"}])
        self.assertEqual(result["items"], [{"media_id": "77", "title": "Photo"}])

    async def test_empty_filtered_page(self):
        result, _ = await self.contents("show", [], watched=True)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["totalItems"], 0)

    async def test_tool_schema_exposes_watch_filter_documentation(self):
        tool = next(t for t in await mcp.list_tools() if t.name == "library_get_contents")
        self.assertIn("watched", tool.inputSchema["properties"])
        self.assertIn("Partially watched shows are included", tool.description)
        self.assertIn("watchStatus", tool.description)


if __name__ == "__main__":
    unittest.main()
