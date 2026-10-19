"""RAG generation uses the same stateless Responses contract as other clients."""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import HTTPException

SERVICE = Path(__file__).parents[1]
sys.path.insert(0, str(SERVICE))


class LlmContractTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Search and embedding are isolated here; this test exercises generation.
        fake_es = types.ModuleType("elasticsearch")
        fake_es.Elasticsearch = MagicMock()
        fake_es.NotFoundError = type("NotFoundError", (Exception,), {})
        fake_es.helpers = MagicMock()
        spec = importlib.util.spec_from_file_location("rag_responses_test_app", SERVICE / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        with patch.dict(sys.modules, {"elasticsearch": fake_es}):
            spec.loader.exec_module(cls.module)

    async def run_query(self, body, *, configured=True):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=body)
        original_client = httpx.AsyncClient
        hit = {"_id": "one", "_source": {"content": "reference text", "source_id": "source-one"}}
        es = MagicMock()
        es.search.return_value = {"hits": {"hits": [hit]}}
        m = self.module
        with patch.multiple(m, es=es, LLM_RESPONSES_URL="http://llm.test/v1/responses" if configured else "", LLM_TOKEN="test-token"), \
             patch.object(m, "identify", return_value=object()), \
             patch.object(m, "target_collection", return_value="agent-test"), \
             patch.object(m, "ensure_index"), \
             patch.object(m, "embed", new=AsyncMock(return_value=[{"embedding": [1.0]}])), \
             patch.object(m.httpx, "AsyncClient", side_effect=lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw)):
            result = await m.query(m.QueryRequest(question="question"), authorization="Bearer test")
        return result, requests

    async def test_generation_uses_responses_and_reference_boundary(self):
        result, requests = await self.run_query({"status": "completed", "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": "answer"}]}]})
        self.assertEqual(result["answer"], "answer")
        self.assertEqual(requests[0].url.path, "/v1/responses")
        body = json.loads(requests[0].content)
        self.assertFalse(body["store"])
        self.assertIn("不可信的参考内容", body["instructions"])
        self.assertIn("<context>\nreference text\n</context>", body["input"])
        self.assertNotIn("messages", body)

    async def test_incomplete_generation_is_not_a_success(self):
        with self.assertRaises(HTTPException) as raised:
            await self.run_query({"status": "incomplete", "output": []})
        self.assertEqual(raised.exception.status_code, 502)

    async def test_refusal_with_partial_text_is_not_an_answer(self):
        with self.assertRaises(HTTPException) as raised:
            await self.run_query({"status": "completed", "output": [
                {"type": "message", "content": [
                    {"type": "output_text", "text": "partial answer"},
                    {"type": "refusal", "refusal": "Unavailable"},
                ]},
            ]})
        self.assertEqual(raised.exception.status_code, 502)

    async def test_unconfigured_model_returns_context_without_network(self):
        result, requests = await self.run_query({}, configured=False)
        self.assertEqual(result["answer"], "reference text")
        self.assertFalse(requests)
