import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from aiohttp import web
from cryptography.hazmat.primitives.asymmetric import rsa

from modules import auth


class OAuthValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk['kid'] = 'test-key'
        self.requests = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.fail_keys = False

        async def discovery(request):
            self.requests.append('discovery')
            self.started.set()
            await self.release.wait()
            return web.json_response({'jwks_uri': self.issuer + '/keys'})

        async def keys(request):
            self.requests.append('keys')
            if self.fail_keys:
                return web.Response(status=503)
            return web.json_response({'keys': [self.jwk]})

        app = web.Application()
        app.router.add_get('/.well-known/openid-configuration', discovery)
        app.router.add_get('/keys', keys)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.issuer = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        self.config = patch.object(auth, 'oauth_config', SimpleNamespace(
            issuer=self.issuer, jwks_cache_ttl=3600, audience='', is_valid=lambda: True))
        self.cache = patch.object(auth, 'jwks_cache', auth.JWKSCache())
        self.config.start()
        self.cache.start()
        auth._discovery_cache.clear()

    async def asyncTearDown(self):
        self.release.set()
        await self.runner.cleanup()
        self.config.stop()
        self.cache.stop()
        auth._discovery_cache.clear()

    def token(self, **overrides):
        claims = {'iss': self.issuer, 'sub': 'test-user', 'exp': time.time() + 60}
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'test-key'})

    async def test_valid_signature_and_cached_metadata(self):
        for _ in range(2):
            self.assertEqual((await auth.validate_token(self.token()))['sub'], 'test-user')
        self.assertEqual(self.requests, ['discovery', 'keys'])

    async def test_invalid_tokens_still_rejected(self):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        bad_signature = jwt.encode(
            {'iss': self.issuer, 'exp': time.time() + 60}, other_key,
            algorithm='RS256', headers={'kid': 'test-key'})
        for token in [self.token(exp=0), self.token(iss='https://wrong.test'),
                      bad_signature, 'malformed']:
            with self.subTest(token_kind=token[:10]), self.assertRaises(ValueError):
                await auth.validate_token(token)

    async def test_slow_discovery_does_not_block_event_loop(self):
        self.release.clear()
        task = asyncio.create_task(auth.validate_token(self.token()))
        try:
            await asyncio.wait_for(self.started.wait(), timeout=2)
            self.assertFalse(task.done())
            self.release.set()
            self.assertEqual((await asyncio.wait_for(task, timeout=2))['sub'], 'test-user')
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_audience_enforced_only_when_configured(self):
        # Unset: tokens for any client of this issuer pass (backwards compatible).
        self.assertEqual((await auth.validate_token(self.token(aud='other-client')))['sub'], 'test-user')
        # Set: only tokens minted for our client ID are accepted.
        auth.oauth_config.audience = 'plex-client'
        self.assertEqual((await auth.validate_token(self.token(aud='plex-client')))['sub'], 'test-user')
        for aud in ['other-client', ['other-client', 'another'], None]:
            with self.subTest(aud=aud), self.assertRaises(ValueError):
                await auth.validate_token(self.token(aud=aud) if aud is not None else self.token())

    async def test_key_server_failure_fails_closed(self):
        self.fail_keys = True
        with self.assertRaises(ValueError):
            await auth.validate_token(self.token())

    async def test_expired_cache_refetches_keys(self):
        await auth.validate_token(self.token())
        auth.jwks_cache._ttl_seconds = 0
        await auth.validate_token(self.token())
        self.assertEqual(self.requests, ['discovery', 'keys', 'keys'])
