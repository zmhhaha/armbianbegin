import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVICE_DIR))

ALIASES = (
    '{"aliases":{'
    '"chat-guarded":{"tier":"guarded","provider":"deepseek","base_url":"https://up.invalid/v1",'
    '"model":"real-model","api_key_env":"TEST_KEY"},'
    '"chat-tools":{"tier":"trusted","provider":"deepseek","base_url":"https://up.invalid/v1",'
    '"model":"real-model","api_key_env":"TEST_KEY"}'
    '},'
    '"limits":{"requests_per_minute_per_caller":2}}'
)


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "model": "real-model",
            "usage": {"prompt_tokens": 3, "completion_tokens": 5},
            "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        }


class LlmServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {"LLM_SERVICE_TOKEN": "tok", "LLM_ALIASES": ALIASES, "TEST_KEY": "k"}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("llm_app", SERVICE_DIR / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules["llm_app"] = cls.module  # pydantic 解析注解需要模块已在 sys.modules
        spec.loader.exec_module(cls.module)
        cls.client = TestClient(cls.module.app)
        cls.headers = {"Authorization": "Bearer tok", "X-Caller": "test-agent"}

    def setUp(self):
        # 每个用例重置限流窗口与用量，避免相互影响
        self.module._windows.clear()
        self.module._usage.clear()

    def _patch_forward(self):
        module = self.module

        async def fake_forward(aliases, alias_name, messages, params):
            return alias_name, FakeResponse()

        return patch.object(module, "forward", fake_forward)

    def test_health_and_models(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        response = self.client.get("/v1/models", headers=self.headers)
        self.assertEqual([item["id"] for item in response.json()["data"]], ["chat-guarded", "chat-tools"])

    def test_chat_resolves_alias_and_records_usage(self):
        with self._patch_forward():
            response = self.client.post(
                "/v1/chat/completions",
                headers=self.headers,
                json={"model": "chat-tools", "messages": [{"role": "user", "content": "hi"}], "temperature": 0.5},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "real-model")
        usage = self.client.get("/v1/usage", headers=self.headers).json()["usage"]
        self.assertEqual(usage["requests"], 1)
        self.assertEqual(usage["completion_tokens"], 5)

    def test_forwards_tools_to_upstream(self):
        """函数调用相关字段（tools/tool_choice）必须透传给上游：CrewAI 的网页工具依赖它。"""
        captured = {}

        async def recording_forward(aliases, alias_name, messages, params):
            captured.update(params)
            return alias_name, FakeResponse()

        with patch.object(self.module, "forward", recording_forward):
            response = self.client.post(
                "/v1/chat/completions",
                headers=self.headers,
                json={
                    "model": "chat-tools",
                    "messages": [{"role": "user", "content": "hi"}],
                    "tools": [{"type": "function", "function": {"name": "web_search"}}],
                    "tool_choice": "auto",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("tool_choice"), "auto")
        self.assertEqual(captured["tools"][0]["function"]["name"], "web_search")

    def test_capability_can_forbid_tools(self):
        """guarded 档位（用户可写 prompt 的服务）禁用函数调用与 response_format。"""
        response = self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={
                "model": "chat-guarded",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "function", "function": {"name": "web_search"}}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not allow tools", response.json()["detail"])

    def test_rejects_unknown_alias(self):
        response = self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={"model": "not-configured", "messages": [{"role": "user", "content": "hi"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_caller_controlled_routing(self):
        for extra in ({"base_url": "https://evil.invalid/v1"}, {"api_key": "x"}, {"provider": "openai"}):
            body = {"model": "chat-default", "messages": [{"role": "user", "content": "hi"}], **extra}
            response = self.client.post("/v1/chat/completions", headers=self.headers, json=body)
            self.assertEqual(response.status_code, 422, extra)

    def test_requires_internal_token(self):
        body = {"model": "chat-tools", "messages": [{"role": "user", "content": "hi"}]}
        self.assertEqual(self.client.post("/v1/chat/completions", json=body).status_code, 401)
        self.assertEqual(
            self.client.post("/v1/chat/completions", headers={"Authorization": "Bearer wrong"}, json=body).status_code,
            401,
        )

    def test_rejects_stream_and_rate_limits(self):
        body = {"model": "chat-tools", "messages": [{"role": "user", "content": "hi"}]}
        with self._patch_forward():
            self.assertEqual(
                self.client.post("/v1/chat/completions", headers=self.headers, json={**body, "stream": True}).status_code,
                400,
            )
            self.assertEqual(self.client.post("/v1/chat/completions", headers=self.headers, json=body).status_code, 200)
            self.assertEqual(self.client.post("/v1/chat/completions", headers=self.headers, json=body).status_code, 200)
            limited = self.client.post("/v1/chat/completions", headers=self.headers, json=body)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "60")


if __name__ == "__main__":
    unittest.main()
