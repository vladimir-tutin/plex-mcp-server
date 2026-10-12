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

    async def test_title_combines_with_filters_before_pagination(self):
        result, calls = await self.contents(
            "movie", [{"ratingKey": "42", "title": "Dungeons & Dragons", "viewCount": 1}],
            title="  Dungeons & Dragons  ", watched=True, genre="Fantasy", offset=1, limit=1, total=3,
        )
        query = parse_qs(urlparse(calls[1].args[1]).query)
        self.assertEqual(query["title"], ["Dungeons & Dragons"])
        self.assertEqual(query["unwatched"], ["0"])
        self.assertEqual(query["genre"], ["Fantasy"])
        self.assertEqual((result["totalItems"], result["offset"], result["size"]), (3, 1, 1))
        tool = next(t for t in await mcp.list_tools() if t.name == "library_get_contents")
        self.assertIn("title", tool.inputSchema["properties"])

    async def test_blank_title_does_not_filter(self):
        for title in (None, "", "   "):
            _, calls = await self.contents("movie", [], title=title)
            self.assertNotIn("title", parse_qs(urlparse(calls[1].args[1]).query))

    async def test_cross_library_track_filters_and_pagination(self):
        plex = SimpleNamespace(_baseurl="http://plex.test:32400/", _token="selected")
        response = {"MediaContainer": {"totalSize": 12, "size": 1, "Metadata": [{
            "ratingKey": "50", "type": "track", "title": "Example", "viewCount": 2,
            "duration": 1000, "viewOffset": 500, "librarySectionTitle": "Music", "librarySectionID": 3,
            "grandparentTitle": "Artist", "parentTitle": "Album"}]}}
        with patch("modules.library.connect_to_plex", return_value=plex), patch(
            "modules.library.server_for_user", return_value=plex
        ) as select, patch("modules.library.async_get_json", new_callable=AsyncMock, return_value=response) as request:
            result = json.loads(await library_get_contents(media_type="track", title="Example", watched=True,
                                                          offset=2, limit=1, username="Eric"))
        select.assert_called_once_with(plex, username="Eric")
        self.assertEqual(request.await_count, 1)
        url = urlparse(request.call_args.args[1])
        self.assertEqual(url.path, "/library/all")
        query = parse_qs(url.query)
        self.assertEqual(query['type'], ['10'])
        self.assertEqual(query['title'], ['Example'])
        self.assertEqual(query['unwatched'], ['0'])
        self.assertEqual(result['totalItems'], 12)
        item = result['items'][0]
        self.assertEqual((item['library'], item['artist'], item['album'], item['progressPercent']),
                         ('Music', 'Artist', 'Album', 50.0))
        self.assertTrue(item['watched'])

    async def test_media_type_validation_before_connection(self):
        with patch("modules.library.connect_to_plex") as connect:
            for args in ({}, {"media_type": "wrong"}, {"media_type": "movie", "limit": 0}):
                self.assertIn('error', json.loads(await library_get_contents(**args)))
            connect.assert_not_called()

    async def test_episode_type_in_named_library(self):
        result, calls = await self.contents('show', [{'ratingKey': '2', 'title': 'Episode',
            'type': 'episode', 'grandparentTitle': 'Show', 'parentIndex': 1, 'index': 2}], media_type='episode')
        self.assertEqual(parse_qs(urlparse(calls[1].args[1]).query)['type'], ['4'])
        self.assertEqual(result['items'][0]['show'], 'Show')
        self.assertEqual(result['items'][0]['episode'], 2)

    async def test_incompatible_filter_is_not_silently_ignored(self):
        plex=SimpleNamespace(_baseurl='http://plex/',_token='test')
        with patch('modules.library.connect_to_plex',return_value=plex), patch(
            'modules.library.async_get_json',new_callable=AsyncMock
        ) as request:
            result=json.loads(await library_get_contents(media_type='track',resolution='4k'))
            self.assertIn('Unsupported filters',result['error'])
            request.assert_not_awaited()

    async def test_invalid_resolution_rejected_before_connection(self):
        with patch('modules.library.connect_to_plex') as connect:
            result=json.loads(await library_get_contents(media_type='movie',resolution='bad-value'))
            self.assertIn('resolution must be',result['error'])
            connect.assert_not_called()

    async def test_unwatched_show_filter_uses_remaining_episodes(self):
        _,calls=await self.contents('show',[],unwatched=True)
        query=parse_qs(urlparse(calls[1].args[1]).query)
        self.assertEqual(query['show.unwatchedLeaves'],['1'])
        self.assertNotIn('unwatched',query)

    async def test_episode_parent_genre_filter(self):
        _,calls=await self.contents('show',[],media_type='episode',genre='Drama',year=2020)
        query=parse_qs(urlparse(calls[1].args[1]).query)
        self.assertEqual(query['show.genre'],['Drama'])
        self.assertEqual(query['year'],['2020'])
        self.assertNotIn('genre',query)

    async def test_unwatched_movies(self):
        result, calls = await self.contents(
            "movie", [{"ratingKey": "43", "title": "Unplayed"}], unwatched=True,
        )
        self.assertFalse(result["items"][0]["watched"])
        self.assertEqual(parse_qs(urlparse(calls[1].args[1]).query)["unwatched"], ["1"])

    async def test_movie_progress_is_independent_of_watched_state(self):
        for played in (0, 2):
            for position, expected_progress in ((0, 0), (3600000, 50)):
                with self.subTest(played=played, position=position):
                    result, calls = await self.contents("movie", [{
                        "ratingKey": "42", "title": "Movie", "viewCount": played,
                        "duration": 7200000, "viewOffset": position,
                    }], watched=bool(played), unwatched=not played)
                    item = result["items"][0]
                    self.assertEqual(item["watched"], bool(played))
                    self.assertEqual(item["inProgress"], position > 0)
                    self.assertEqual(item["progressPercent"], expected_progress)
                    # Progress comes from the library response, with no hub or
                    # per-movie lookup needed to expose it.
                    self.assertEqual(len(calls), 2)

    async def test_movie_progress_handles_missing_and_boundary_metadata(self):
        cases = [
            ({"duration": 1000}, False, 0),
            ({"duration": 1000, "viewOffset": None}, False, 0),
            ({"viewOffset": 500}, True, None),
            ({"duration": None, "viewOffset": 500}, True, None),
            ({"duration": 0, "viewOffset": 500}, True, None),
            ({"duration": 1000, "viewOffset": -100}, False, 0),
            ({"duration": 1000, "viewOffset": 1000}, True, 100),
            ({"duration": 1000, "viewOffset": 1500}, True, 100),
            ({"duration": 3000, "viewOffset": 1000}, True, 33.3),
        ]
        for metadata, expected_in_progress, expected_percent in cases:
            with self.subTest(metadata=metadata):
                result, _ = await self.contents("movie", [{"ratingKey": "42", **metadata}])
                item = result["items"][0]
                self.assertEqual(item["inProgress"], expected_in_progress)
                self.assertEqual(item["progressPercent"], expected_percent)

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

    async def test_watched_show_filter_uses_episode_completion_and_preserves_total(self):
        result, calls = await self.contents(
            "show", [{"ratingKey": "99", "title": "Complete"}],
            [{"MediaContainer": {"Metadata": [{"leafCount": 10, "viewedLeafCount": 10}]}}],
            total=339, watched=True, offset=2, limit=1,
        )
        self.assertEqual(result["items"][0]["watchStatus"], "watched")
        self.assertTrue(result["items"][0]["watched"])
        self.assertEqual(result["totalItems"], 339)
        self.assertEqual(result["size"], 1)
        self.assertEqual(parse_qs(urlparse(calls[1].args[1]).query)["show.unwatchedLeaves"], ["0"])

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
        self.assertIn("Partially watched shows are excluded", tool.description)
        self.assertIn("watchStatus", tool.description)
        self.assertIn("inProgress", tool.description)
        self.assertIn("progressPercent", tool.description)


if __name__ == "__main__":
    unittest.main()
