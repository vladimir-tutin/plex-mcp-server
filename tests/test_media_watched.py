import asyncio
import json
import unittest
from unittest.mock import patch

from modules import mcp
from modules.media import media_set_watched_status


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


def call_tool(plex, watched):
    with patch("modules.media.connect_to_plex", return_value=plex):
        return json.loads(asyncio.run(media_set_watched_status(42, watched)))


class MediaSetWatchedStatusTests(unittest.TestCase):
    def test_tool_is_registered(self):
        tools = asyncio.run(mcp.list_tools())

        self.assertIn("media_set_watched_status", [tool.name for tool in tools])

    def test_marks_unplayed_item_watched(self):
        media = FakeMedia(watched=False)

        result = call_tool(FakePlex(media), True)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["watched"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["view_count"], 1)

    def test_marks_played_item_unwatched(self):
        media = FakeMedia(watched=True)

        result = call_tool(FakePlex(media), False)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["watched"])
        self.assertTrue(result["changed"])

    def test_is_idempotent(self):
        plex = FakePlex(FakeMedia(watched=True))

        result = call_tool(plex, True)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["changed"])
        self.assertEqual(plex.fetch_count, 2)

    def test_rejects_unsupported_media(self):
        result = call_tool(FakePlex(FakeMedia(supported=False)), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("does not support", result["message"])

    def test_reports_missing_media(self):
        result = call_tool(FakePlex(None), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("was not found", result["message"])

    def test_reports_plex_errors(self):
        result = call_tool(FakePlex(error=RuntimeError("request failed")), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("request failed", result["message"])

    def test_detects_failed_persistence(self):
        result = call_tool(FakePlex(FakeMedia(watched=False), persist=False), True)

        self.assertEqual(result["status"], "error")
        self.assertIn("did not persist", result["message"])


if __name__ == "__main__":
    unittest.main()
