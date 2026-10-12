import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules import mcp, playlist
from modules.profiles import ProfileAccessError


class PlaylistProfileTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, name, arguments):
        content, _ = await mcp.call_tool(name, arguments)
        return json.loads(content[0].text)

    async def test_all_registered_tools_accept_username_and_report_failed_access(self):
        arguments = {
            "playlist_list": {},
            "playlist_create": {"playlist_title": "Test", "item_titles": ["Example"]},
            "playlist_get_contents": {"playlist_id": 42},
            "playlist_edit": {"playlist_id": 42, "new_title": "Updated"},
            "playlist_add_to": {"playlist_id": 42, "item_ids": [1]},
            "playlist_remove_from": {"playlist_id": 42, "item_titles": ["Example"]},
            "playlist_delete": {"playlist_id": 42},
            "playlist_upload_poster": {"playlist_id": 42, "poster_filepath": "test.png"},
            "playlist_copy_to_user": {"playlist_id": 42, "source_username": "Source"},
        }
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        for name, args in arguments.items():
            with self.subTest(tool=name):
                self.assertIn("username", tools[name].inputSchema["properties"])
                with patch.object(playlist, "connect_to_plex") as connect, patch.object(
                    playlist, "server_for_user", side_effect=ProfileAccessError("User unavailable")
                ) as resolve:
                    result = await self.call(name, dict(args, username="Target"))
                    self.assertIn("User unavailable", json.dumps(result))
                    resolve.assert_called_once_with(
                        connect.return_value,
                        username="Source" if name == "playlist_copy_to_user" else "Target",
                    )
                    connect.return_value.playlists.assert_not_called()
                    connect.return_value.fetchItem.assert_not_called()

    async def test_delete_uses_only_selected_users_playlists(self):
        selected = Mock()
        target = Mock(ratingKey="42", title="Selected playlist")
        selected.playlists.return_value = [target]
        with patch.object(playlist, "connect_to_plex") as connect, patch.object(
            playlist, "server_for_user", return_value=selected
        ):
            result = await self.call("playlist_delete", {"username": "Target", "playlist_id": 42})
            self.assertTrue(result["deleted"])
            target.delete.assert_called_once_with()
            # An ID outside this user's playlist list must never become a media delete.
            result = await self.call("playlist_delete", {"username": "Target", "playlist_id": 99})
            self.assertIn("error", result)
            self.assertEqual(target.delete.call_count, 1)
            selected.fetchItem.assert_not_called()
            connect.return_value.playlists.assert_not_called()

    async def test_copy_resolves_source_and_destination_from_admin(self):
        source, destination = Mock(), Mock()
        target = Mock(ratingKey="42", title="Source playlist")
        target.items.return_value = [SimpleNamespace(ratingKey=7)]
        source.playlists.return_value = [target]
        with patch.object(playlist, "connect_to_plex") as connect, patch.object(
            playlist, "server_for_user", side_effect=[source, destination]
        ) as resolve:
            result = await self.call("playlist_copy_to_user", {
                "source_username": "Source", "username": "Destination", "playlist_id": 42,
            })
            self.assertEqual(result["status"], "success")
            self.assertEqual([call.kwargs["username"] for call in resolve.call_args_list],
                             ["Source", "Destination"])
            self.assertTrue(all(call.args[0] is connect.return_value for call in resolve.call_args_list))
            destination.fetchItem.assert_called_once_with(7)
            destination.createPlaylist.assert_called_once_with(
                title="Source playlist", items=[destination.fetchItem.return_value]
            )

    async def test_omitting_username_keeps_configured_account(self):
        with patch.object(playlist, "connect_to_plex") as connect:
            connect.return_value.playlists.return_value = []
            self.assertEqual(await self.call("playlist_list", {}), [])
            connect.return_value.myPlexAccount.assert_not_called()
