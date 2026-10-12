import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules.profiles import server_for_user, ProfileAccessError
from modules import user


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.target = Mock(id=42, username=None, title="Eric")
        self.target.get_token.return_value = "profile-token"
        self.account = Mock(id=1, username="owner", title="Owner")
        self.account.users.return_value = [self.target]
        self.plex = Mock(machineIdentifier="server-id", _baseurl="http://plex.test")
        self.plex.myPlexAccount.return_value = self.account

    def test_default_does_not_switch(self):
        self.assertIs(server_for_user(self.plex), self.plex)
        self.plex.myPlexAccount.assert_not_called()

    def test_owner_and_id_precedence(self):
        self.assertIs(server_for_user(self.plex, user_id=1, username="Eric"), self.plex)

    def test_managed_title_and_shared_user(self):
        for home in (True, False):
            self.target.home = home
            with patch("modules.profiles.PlexServer") as server:
                self.assertIs(server_for_user(self.plex, username="eric"), server.return_value)
                server.assert_called_once_with("http://plex.test", token="profile-token", timeout=15)

    def test_missing_token_never_connects_as_owner(self):
        self.target.get_token.return_value = None
        with patch("modules.profiles.PlexServer") as server:
            with self.assertRaises(ProfileAccessError):
                server_for_user(self.plex, user_id=42)
            server.assert_not_called()

    def test_unknown_and_ambiguous_users(self):
        with self.assertRaises(ProfileAccessError):
            server_for_user(self.plex, user_id=99)
        self.account.users.return_value.append(Mock(id=43, username="Eric", title="Eric"))
        with self.assertRaises(ProfileAccessError):
            server_for_user(self.plex, username="Eric")

    def test_errors_do_not_expose_tokens(self):
        self.target.get_token.side_effect = RuntimeError("secret-token")
        with self.assertRaises(ProfileAccessError) as error:
            server_for_user(self.plex, user_id=42)
        self.assertNotIn("secret-token", str(error.exception))


class ContinueWatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_profile_results(self):
        selected = Mock()
        selected.continueWatching.return_value = [SimpleNamespace(type="movie", title="Example", ratingKey=12, year=2020, viewOffset=50, duration=100)]
        with patch.object(user, "connect_to_plex") as connect, patch.object(user, "server_for_user", return_value=selected) as resolve:
            result = json.loads(await user.user_get_continue_watching(username="Eric"))
            resolve.assert_called_once_with(connect.return_value, username="Eric", user_id=None)
            self.assertEqual(result["items"][0]["progress"], 50)
            connect.return_value.continueWatching.assert_not_called()

    async def test_failed_selection_returns_error(self):
        with patch.object(user, "connect_to_plex"), patch.object(user, "server_for_user", side_effect=ProfileAccessError("Unavailable")):
            self.assertEqual(json.loads(await user.user_get_continue_watching(user_id=42))["status"], "error")
