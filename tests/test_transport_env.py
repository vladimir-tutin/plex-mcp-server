import contextlib
import io
import os
import unittest
from unittest.mock import patch

import plex_mcp_server as server


class TransportEnvironmentTests(unittest.TestCase):
    def test_transport_defaults_environment_and_cli_precedence(self):
        for value, flags, expected in (
            (None, [], 'sse'),
            ('sse', [], 'sse'),
            ('streamable-http', [], 'streamable-http'),
            ('stdio', [], 'stdio'),
            ('sse', ['--transport', 'streamable-http'], 'streamable-http'),
            ('invalid', ['--transport', 'stdio'], 'stdio'),
        ):
            with self.subTest(value=value, flags=flags), patch.dict(os.environ, {}, clear=True), \
                    patch('sys.argv', ['plex-mcp-server', *flags]), \
                    patch.object(server, 'init_environment', return_value=False), \
                    patch.object(server.oauth_config, 'reload'), \
                    patch.object(server, 'create_starlette_app') as sse, \
                    patch.object(server, 'create_streamable_http_app') as http, \
                    patch.object(server.uvicorn, 'run'), patch.object(server.mcp, 'run') as stdio, \
                    contextlib.redirect_stderr(io.StringIO()):
                if value is not None:
                    os.environ['MCP_TRANSPORT'] = value
                server.main()
                self.assertEqual(sse.called, expected == 'sse')
                self.assertEqual(http.called, expected == 'streamable-http')
                self.assertEqual(stdio.called, expected == 'stdio')

    def test_invalid_environment_fails_before_starting(self):
        with patch.dict(os.environ, {'MCP_TRANSPORT': 'invalid'}), \
                patch('sys.argv', ['plex-mcp-server']), \
                patch.object(server, 'init_environment', return_value=False), \
                patch.object(server.uvicorn, 'run') as run, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            server.main()
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()
