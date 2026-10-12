import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.responses import Response
from starlette.testclient import TestClient

import plex_mcp_server as server


class OAuthLoggingTests(unittest.TestCase):
    def test_token_proxy_preserves_response_without_logging_credentials(self):
        for status, payload in [
            (200, {"access_token": "secret-access", "refresh_token": "secret-refresh",
                   "id_token": "secret-id"}),
            (400, {"error": "invalid_grant", "error_description": "secret-provider-detail"}),
        ]:
            with self.subTest(status=status):
                discovery = AsyncMock()
                discovery.status = 200
                discovery.json.return_value = {"token_endpoint": "https://issuer.test/token"}
                token_response = AsyncMock()
                token_response.status = status
                token_response.headers = {"Content-Type": "application/json"}
                body = json.dumps(payload)
                token_response.text.return_value = body

                session = MagicMock()
                session.get.return_value.__aenter__ = AsyncMock(return_value=discovery)
                session.post.return_value.__aenter__ = AsyncMock(return_value=token_response)
                factory = MagicMock()
                factory.return_value.__aenter__ = AsyncMock(return_value=session)
                config = SimpleNamespace(enabled=True, issuer="https://issuer.test", server_url="")
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(server, "oauth_config", config), patch(
                    "aiohttp.ClientSession", factory
                ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    app = server.create_starlette_app(server.mcp._mcp_server)
                    with TestClient(app) as client:
                        response = client.post(
                            "/token", content="code=secret-code&client_secret=secret-client",
                            headers={"Content-Type": "application/x-www-form-urlencoded",
                                     "Authorization": "Basic secret-basic"},
                        )
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.text, body)
                self.assertEqual(response.headers["content-type"], "application/json")
                forwarded = session.post.call_args.kwargs
                self.assertEqual(forwarded["data"], b"code=secret-code&client_secret=secret-client")
                self.assertEqual(forwarded["headers"]["authorization"], "Basic secret-basic")
                logs = stdout.getvalue() + stderr.getvalue()
                self.assertNotIn("secret-", logs)
                self.assertIn(f"Response status: {status}", logs)

    def test_invalid_token_does_not_log_or_return_validation_details(self):
        async def downstream(scope, receive, send):
            raise AssertionError("Invalid credentials reached the protected app")

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(server, "oauth_config", SimpleNamespace(enabled=True)), patch.object(
            server, "validate_token", side_effect=ValueError("secret-validation-detail")
        ), patch.object(server, "get_www_authenticate_header", return_value="Bearer"), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            client = TestClient(server.OAuthMiddleware(downstream))
            response = client.get("/protected", headers={"Authorization": "Bearer secret-access"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.text, "Invalid token")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertNotIn("secret-", stdout.getvalue() + stderr.getvalue())

    def test_valid_token_preserves_identity_without_logging_it(self):
        async def downstream(scope, receive, send):
            self.assertEqual(scope["oauth_user"]["sub"], "secret-subject")
            await Response("OK")(scope, receive, send)

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(server, "oauth_config", SimpleNamespace(enabled=True)), patch.object(
            server, "validate_token", return_value={"sub": "secret-subject"}
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            client = TestClient(server.OAuthMiddleware(downstream))
            response = client.get("/protected", headers={"Authorization": "Bearer secret-access"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("secret-", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
