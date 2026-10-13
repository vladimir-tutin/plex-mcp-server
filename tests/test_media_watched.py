import json
import unittest
from unittest.mock import patch

from plexapi.exceptions import NotFound  # type: ignore

from modules import mcp, media


class FakeMedia:
    def __init__(self, watched=False, supported=True):
        self.ratingKey = 42
        self.title = "Test Movie"
        self.type = "movie"
        self.viewCount = 1 if watched else 0
        self._watched = watched
        if not supported:
            self.markPlayed = None
            self.markUnplayed = None

    @property
    def isPlayed(self):
        return self._watched

    def markPlayed(self):
        self._watched = True
        self.viewCount = 1

    def markUnplayed(self):
        self._watched = False
        self.viewCount = 0


class FakeContainer:
    """A show, season or album whose state is its watched child count."""

    def __init__(self, media_type, watched_count, total_count=4):
        self.ratingKey = 42
        self.title = "Test Container"
        self.type = media_type
        self.viewedLeafCount = watched_count
        self.leafCount = total_count
        self.viewCount = watched_count

    @property
    def isPlayed(self):
        # Deliberately mimics plexapi: shows/seasons need every child watched,
        # albums count as played after any single play.
        if self.type == "album":
            return self.viewCount > 0
        return self.viewedLeafCount == self.leafCount

    def markPlayed(self):
        self.viewedLeafCount = self.viewCount = self.leafCount

    def markUnplayed(self):
        self.viewedLeafCount = self.viewCount = 0


class FakePlex:
    def __init__(self, media=None, error=None, persist=True):
        self.media = media
        self.error = error
        self.persist = persist
        self.fetch_count = 0

    def fetchItem(self, media_id):
        self.fetch_count += 1
        if self.error:
            raise self.error
        if not self.persist and self.fetch_count > 1:
            return FakeMedia(watched=False)
        return self.media


class MediaSetWatchedStatusTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, plex, watched, **extra):
        with patch.object(media, "connect_to_plex"), patch.object(
            media, "server_for_user", return_value=plex
        ):
            return json.loads(await media.media_set_watched_status(42, watched, **extra))

    async def test_tool_is_registered(self):
        tools = await mcp.list_tools()

        self.assertIn("media_set_watched_status", [tool.name for tool in tools])

    async def test_marks_unplayed_item_watched(self):
        result = await self.call(FakePlex(FakeMedia(watched=False)), True)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["watched"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["view_count"], 1)

    async def test_marks_played_item_unwatched(self):
        result = await self.call(FakePlex(FakeMedia(watched=True)), False)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["watched"])
        self.assertTrue(result["changed"])

    async def test_is_idempotent(self):
        plex = FakePlex(FakeMedia(watched=True))

        result = await self.call(plex, True)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["changed"])
        self.assertEqual(plex.fetch_count, 2)

    async def test_rejects_unsupported_media(self):
        result = await self.call(FakePlex(FakeMedia(supported=False)), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("does not support", result["message"])

    async def test_reports_missing_media(self):
        for plex in (FakePlex(None), FakePlex(error=NotFound("missing"))):
            with self.subTest(plex=plex):
                result = await self.call(plex, True)

                self.assertEqual(result["status"], "error")
                self.assertIn("was not found", result["message"])

    async def test_reports_plex_errors(self):
        result = await self.call(FakePlex(error=RuntimeError("request failed")), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("request failed", result["message"])

    async def test_detects_failed_persistence(self):
        result = await self.call(FakePlex(FakeMedia(watched=False), persist=False), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("did not persist", result["message"])

    async def test_partly_watched_containers_are_updated(self):
        # Regression: plexapi's isPlayed made these silent no-ops.
        cases = [("show", False), ("season", False), ("album", True), ("album", False), ("show", True)]
        for media_type, watched in cases:
            with self.subTest(media_type=media_type, watched=watched):
                item = FakeContainer(media_type, watched_count=2)

                result = await self.call(FakePlex(item), watched)

                self.assertEqual(result["status"], "success")
                self.assertTrue(result["changed"])
                self.assertEqual(result["previous_watch_status"], "partial")
                self.assertEqual(result["watch_status"], "watched" if watched else "unwatched")
                self.assertEqual(result["watched_count"], 4 if watched else 0)
                self.assertEqual(result["total_count"], 4)

    async def test_artist_state_is_summed_from_albums(self):
        albums = [FakeContainer("album", 2, 2), FakeContainer("album", 1, 3)]
        artist = FakeContainer("artist", watched_count=3, total_count=5)
        artist.albums = lambda: albums

        def mark_all(played):
            for album in albums:
                album.viewedLeafCount = album.leafCount if played else 0
        artist.markPlayed = lambda: mark_all(True)
        artist.markUnplayed = lambda: mark_all(False)

        result = await self.call(FakePlex(artist), True)

        self.assertEqual(result["previous_watch_status"], "partial")
        self.assertTrue(result["changed"])
        self.assertEqual((result["watch_status"], result["watched_count"], result["total_count"]),
                         ("watched", 5, 5))

    async def test_containers_already_in_state_are_not_rewritten(self):
        for media_type, count, watched in [("show", 4, True), ("season", 0, False), ("album", 4, True)]:
            with self.subTest(media_type=media_type, watched=watched):
                result = await self.call(FakePlex(FakeContainer(media_type, count)), watched)

                self.assertEqual(result["status"], "success")
                self.assertFalse(result["changed"])

    async def test_details_report_container_watch_state(self):
        item = FakeContainer("season", watched_count=1, total_count=3)

        details = media.get_media_details(item)

        self.assertEqual(details["watch_status"], "partial")
        self.assertFalse(details["watched"])
        self.assertEqual((details["watched_count"], details["total_count"]), (1, 3))

    async def test_username_selects_that_users_server(self):
        selected = FakePlex(FakeMedia(watched=False))
        with patch.object(media, "connect_to_plex") as connect, patch.object(
            media, "server_for_user", return_value=selected
        ) as resolve:
            result = json.loads(await media.media_set_watched_status(42, True, username="test-user"))

        resolve.assert_called_once_with(connect.return_value, username="test-user")
        self.assertEqual(result["status"], "success")
        self.assertEqual(selected.fetch_count, 2)


if __name__ == "__main__":
    unittest.main()
