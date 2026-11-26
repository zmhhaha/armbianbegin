"""Verify model-read tolerance and control I/O bounds on actual HTTPX requests."""
import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).parents[1]))
from config import Alias
import upstream


class UpstreamTimeoutTests(unittest.TestCase):
    def test_buffered_and_streamed_calls_share_bounded_phase_timeouts(self):
        for seconds, expected in (
            (600, {'connect': 10.0, 'read': 600, 'write': 60.0, 'pool': 30.0}),
            (120, {'connect': 10.0, 'read': 120, 'write': 60.0, 'pool': 30.0}),
            (2.5, {'connect': 2.5, 'read': 2.5, 'write': 2.5, 'pool': 2.5}),
        ):
            for streaming in (False, True):
                with self.subTest(seconds=seconds, streaming=streaming):
                    alias = Alias(name='test', provider='test', base_url='https://provider.invalid/v1',
                                  model='test-model', api_key_env='TEST_MODEL_KEY',
                                  timeout_seconds=seconds, max_retries=0)
                    seen = []

                    def handle(request):
                        seen.append(request.extensions['timeout'])
                        if streaming:
                            return httpx.Response(200, content=b'data: [DONE]\n\n',
                                                  headers={'content-type': 'text/event-stream'})
                        return httpx.Response(200, json={'choices': []})

                    original = httpx.AsyncClient
                    transport = httpx.MockTransport(handle)

                    async def exercise():
                        if streaming:
                            response = await upstream.open_stream({'test': alias}, 'test', [], {})
                            try:
                                self.assertEqual(b''.join([chunk async for chunk in response.aiter()]),
                                                 b'data: [DONE]\n\n')
                            finally:
                                await response.aclose()
                        else:
                            response = await upstream.forward({'test': alias}, 'test', [], {})
                            self.assertEqual(response.status_code, 200)

                    with patch.dict(os.environ, {'TEST_MODEL_KEY': 'fake-key'}), patch.object(
                        upstream.httpx, 'AsyncClient',
                        lambda **kwargs: original(transport=transport, **kwargs),
                    ):
                        asyncio.run(exercise())
                    self.assertEqual(seen, [expected])


if __name__ == '__main__':
    unittest.main()
