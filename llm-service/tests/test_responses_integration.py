"""Exercise the public Chat endpoint through the real upstream adapter."""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVICE_DIR))
import upstream
from config import load_config


def response_body(text='hello'):
    return {'id': 'resp_1', 'object': 'response', 'created_at': 123,
            'model': 'gpt-6-astra', 'status': 'completed',
            'output': [{'id': 'msg_1', 'type': 'message', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
            'usage': {'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10}}


def sse(*events):
    return ''.join('data: '+json.dumps(event)+'\n\n' for event in events).encode()


class ResponsesIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((SERVICE_DIR / 'config.example.json').read_text())
        env = {'LLM_TOKEN_RESPONSES_TEST': 'test-token', 'LLM_ALIASES': json.dumps(cls.data),
               'CUSTOM_API_KEY': 'custom-test', 'DEEPSEEK_API_KEY': 'deepseek-test', 'LLM_GUARD': ''}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location('responses_test_app', SERVICE_DIR / 'app.py')
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.client = TestClient(cls.module.app)
        cls.headers = {'Authorization': 'Bearer test-token'}

    def setUp(self):
        self.module._windows.clear()
        self.module._usage.clear()
        self.module._alias_usage.clear()
        self.module._route_usage.clear()
        self.module._guard_stats.clear()
        self.requests = []

    def transport(self, responder):
        original = httpx.AsyncClient
        def handler(request):
            self.requests.append((str(request.url), json.loads(request.content)))
            return responder(request)
        transport = httpx.MockTransport(handler)
        return patch.object(upstream.httpx, 'AsyncClient',
                            lambda **kwargs: original(transport=transport, **kwargs))

    def post(self, model='llm-trusted', **kwargs):
        return self.client.post('/v1/chat/completions', headers=self.headers,
            json={'model': model, 'messages': [{'role': 'user', 'content': 'hi'}], **kwargs})

    def test_custom_uses_responses_and_returns_chat_usage(self):
        with self.transport(lambda _: httpx.Response(200, json=response_body())):
            result = self.post(max_tokens=128)
        self.assertEqual(result.status_code, 200, result.text)
        url, body = self.requests[0]
        self.assertTrue(url.endswith('/v1/responses'))
        self.assertNotIn('messages', body)
        self.assertFalse(body['store'])
        self.assertEqual(body['max_output_tokens'], 128)
        self.assertEqual(result.json()['choices'][0]['message']['content'], 'hello')
        self.assertEqual(self.module._usage['responses-test']['prompt_tokens'], 7)
        self.assertEqual(self.module.ALIASES['llm-trusted'].wire_api, 'responses')

    def test_deepseek_chat_payload_and_stream_bytes_are_preserved(self):
        raw = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        with self.transport(lambda _: httpx.Response(200, content=raw,
                headers={'content-type': 'text/event-stream'})):
            result = self.post('deepseek-trusted', stream=True, stop=['END'], seed=12, n=2)
        self.assertEqual(result.content, raw)
        url, body = self.requests[0]
        self.assertTrue(url.endswith('/chat/completions'))
        self.assertEqual(body['stream_options'], {'include_usage': True})
        self.assertEqual((body['stop'], body['seed'], body['n']), (['END'], 12, 2))
        self.assertIn('messages', body)
        self.assertNotIn('input', body)

    def test_active_switch_restores_chat_without_client_changes(self):
        switched = {**self.data, 'active_upstream': 'deepseek'}
        with patch.dict(os.environ, {'LLM_ALIASES': json.dumps(switched)}):
            routes, _ = load_config()
        chat = {'choices': [{'message': {'role': 'assistant', 'content': 'deepseek'}}]}
        with patch.object(self.module, 'ALIASES', routes), self.transport(
                lambda _: httpx.Response(200, json=chat)):
            result = self.post()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), chat)
        self.assertTrue(self.requests[0][0].endswith('/chat/completions'))

    def test_unsupported_custom_params_rejected_before_network(self):
        with self.transport(lambda _: self.fail('unsupported request reached upstream')):
            for options in ({'n': 2}, {'stop': ['END']}, {'seed': 12}, {'presence_penalty': .1}):
                with self.subTest(options=options):
                    result = self.post(**options)
                    self.assertEqual(result.status_code, 400, result.text)
        self.assertFalse(self.requests)

    def test_invalid_response_is_502_and_upstream_4xx_passes_through(self):
        for body in ({'status': 'failed'}, {'status': 'completed', 'output': 'bad'}, []):
            with self.subTest(body=body), self.transport(lambda _: httpx.Response(200, json=body)):
                result = self.post()
                self.assertEqual(result.status_code, 502, result.text)
        with self.transport(lambda _: httpx.Response(400, json={'error': {'message': 'bad input'}})):
            self.assertEqual(self.post().status_code, 400)

    def test_stream_translates_content_and_records_final_usage(self):
        final = response_body()
        raw = sse({'type': 'response.created', 'response': {**final, 'output': [], 'status': 'in_progress'}},
                  {'type': 'response.output_text.delta', 'output_index': 0,
                   'content_index': 0, 'delta': 'hello'},
                  {'type': 'response.completed', 'response': final})
        with self.transport(lambda _: httpx.Response(200, content=raw,
                headers={'content-type': 'text/event-stream'})):
            result = self.post(stream=True)
        self.assertEqual(result.status_code, 200)
        self.assertIn('[DONE]', result.text)
        self.assertNotIn('response.completed', result.text)
        self.assertEqual(self.module._usage['responses-test']['completion_tokens'], 3)
        self.assertTrue(self.requests[0][1]['stream'])
        self.assertNotIn('stream_options', self.requests[0][1])

    def test_truncated_stream_reports_error_without_success_usage(self):
        raw = sse({'type': 'response.output_text.delta', 'output_index': 0,
                   'content_index': 0, 'delta': 'partial'})
        with self.transport(lambda _: httpx.Response(200, content=raw,
                headers={'content-type': 'text/event-stream'})):
            result = self.post(stream=True)
        self.assertIn('"error"', result.text)
        self.assertNotIn('[DONE]', result.text)
        self.assertEqual(self.module._usage['responses-test']['requests'], 0)

    def test_guard_hardens_messages_before_responses_conversion(self):
        captured = {}
        def responder(request):
            body = json.loads(request.content)
            captured.update(body)
            return httpx.Response(200, json=response_body())
        with self.transport(responder):
            result = self.post('llm-guarded')
        self.assertEqual(result.status_code, 200, result.text)
        content = json.dumps(captured['input'])
        self.assertIn('<<<UNTRUSTED_USER_DATA>>>', content)
        self.assertIn('<<<END_UNTRUSTED_USER_DATA>>>', content)
