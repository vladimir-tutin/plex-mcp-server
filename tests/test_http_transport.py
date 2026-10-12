import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from starlette.testclient import TestClient
import plex_mcp_server as server


class HTTPTransportTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.object(server, 'oauth_config', SimpleNamespace(
            enabled=False, server_url='https://plex.example.test'))
        self.config.start()
        self.addCleanup(self.config.stop)

    def client(self):
        return TestClient(server.create_streamable_http_app(server.mcp._mcp_server),
                          base_url='http://localhost')

    def initialize(self, client, **headers):
        return client.post('/mcp', headers={
            'Accept': 'application/json, text/event-stream', **headers}, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-03-26', 'capabilities': {},
                    'clientInfo': {'name': 'transport-test', 'version': '1'}}})

    def test_no_oauth_initialize_and_list_tools(self):
        with patch.object(server, 'validate_token') as validate, self.client() as client:
            response = self.initialize(client)
            self.assertEqual(response.status_code, 200)
            headers = {'Accept': 'application/json, text/event-stream',
                       'Mcp-Session-Id': response.headers['mcp-session-id'],
                       'MCP-Protocol-Version': '2025-03-26'}
            response = client.post('/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            self.assertEqual(response.status_code, 202)
            response = client.post('/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
            self.assertEqual(response.status_code, 200)
            data = json.loads(next(line[6:] for line in response.text.splitlines()
                                   if line.startswith('data: ')))
            self.assertIn('library_list', [t['name'] for t in data['result']['tools']])
            validate.assert_not_called()

    def test_untrusted_host_and_origin_rejected(self):
        with self.client() as client:
            self.assertEqual(self.initialize(client, Host='evil.test').status_code, 421)
            self.assertEqual(self.initialize(client, Origin='https://evil.test').status_code, 403)

    def test_sse_routes_also_reject_untrusted_host(self):
        # DNS-rebinding protection must cover the legacy SSE endpoints too, in both
        # the combined HTTP app and the standalone SSE app. A bad Host must be
        # rejected before session lookup (which would otherwise answer 404).
        apps = [server.create_streamable_http_app(server.mcp._mcp_server),
                server.create_starlette_app(server.mcp._mcp_server)]
        for app in apps:
            with self.subTest(app=app), TestClient(app, base_url='http://localhost') as client:
                self.assertEqual(client.get('/sse', headers={'Host': 'evil.test'}).status_code, 421)
                post = client.post('/messages/?session_id=' + '0' * 32,
                                   headers={'Host': 'evil.test'}, json={})
                self.assertEqual(post.status_code, 421)
                good = client.post('/messages/?session_id=' + '0' * 32, json={})
                self.assertEqual(good.status_code, 404)

    def test_post_to_sse_is_method_not_allowed(self):
        # Claude.ai probes the configured URL with a Streamable HTTP POST and only
        # falls back to classic SSE on a 405; a 200 event stream here hangs the client.
        for app in [server.create_streamable_http_app(server.mcp._mcp_server),
                    server.create_starlette_app(server.mcp._mcp_server)]:
            with self.subTest(app=app), TestClient(app, base_url='http://localhost') as client:
                self.assertEqual(client.post('/sse', json={}).status_code, 405)

    def test_allowed_hosts_env_permits_lan_address(self):
        with patch.dict('os.environ', {'MCP_ALLOWED_HOSTS': '10.0.1.67:3002'}), self.client() as client:
            self.assertEqual(self.initialize(client, Host='10.0.1.67:3002').status_code, 200)
            self.assertEqual(client.post('/messages/?session_id=' + '0' * 32,
                                         headers={'Host': '10.0.1.67:3002'}, json={}).status_code, 404)

    def test_oauth_protects_both_transports(self):
        server.oauth_config.enabled = True
        with self.client() as client:
            self.assertEqual(self.initialize(client).status_code, 401)
            self.assertEqual(client.get('/sse').status_code, 401)

    def test_discovery_under_path_prefix_does_not_require_token(self):
        server.oauth_config.enabled = True
        with TestClient(server.create_streamable_http_app(server.mcp._mcp_server),
                        base_url='http://localhost', root_path='/plex') as client:
            response = client.get('/.well-known/oauth-protected-resource')
            self.assertEqual(response.status_code, 200)
