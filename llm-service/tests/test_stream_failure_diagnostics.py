"""Failure diagnostics are private; partial SSE never gains retry or success."""
from __future__ import annotations

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


PRIVATE = "PRIVATE_PROMPT_TOOL_ARGUMENT_PATH_AND_TOKEN"
PUBLIC_FAILURE = "Responses stream reported a failure"
CALLER = "stream-diagnostics-test"


def sse(*events):
    return "".join("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n"
                   for event in events).encode()


def response():
    return {"id": "resp_diagnostics", "object": "response", "created_at": 123,
            "model": "gpt-6.1-sol", "status": "completed", "error": None,
            "output": [{"id": "msg_diagnostics", "type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "partial", "annotations": []}]}],
            "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}


class BrokenRead(httpx.AsyncByteStream):
    def __init__(self, prefix):
        self.prefix = prefix
        self.closed = False

    async def __aiter__(self):
        yield self.prefix
        raise httpx.ReadError(PRIVATE)

    async def aclose(self):
        self.closed = True


class StreamFailureDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        routing = json.loads((SERVICE_DIR / "config.example.json").read_text(encoding="utf-8"))
        # Tests cannot reach a real provider, even if transport patching regresses.
        for provider in routing["upstreams"].values():
            provider["base_url"] = "https://provider.invalid/v1"
        env = {"LLM_TOKEN_STREAM_DIAGNOSTICS_TEST": "diagnostics-test-token",
               "LLM_ALIASES": json.dumps(routing), "CUSTOM_API_KEY": "fake-key",
               "DEEPSEEK_API_KEY": "fake-key", "LLM_GUARD": ""}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("stream_diagnostics_app", SERVICE_DIR / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.client = TestClient(cls.module.app)

    def setUp(self):
        self.requests = []
        self.reset_counters()

    def reset_counters(self):
        for counters in (self.module._windows, self.module._usage, self.module._alias_usage,
                         self.module._route_usage, self.module._guard_stats):
            counters.clear()

    def transport(self, responder):
        original = httpx.AsyncClient

        def handler(request):
            self.requests.append(request)
            return responder(request)

        transport = httpx.MockTransport(handler)
        return patch.object(upstream.httpx, "AsyncClient",
                            lambda **kwargs: original(transport=transport, **kwargs))

    def post(self, api):
        history = ({"input": "synthetic request"} if api == "responses" else
                   {"messages": [{"role": "user", "content": "synthetic request"}]})
        return self.client.post("/v1/" + api,
            headers={"Authorization": "Bearer diagnostics-test-token"},
            json={"model": "llm-trusted", "stream": True, **history})

    def checked_request(self, api, responder):
        self.requests.clear()
        self.reset_counters()
        with self.assertLogs("llm-service", level="INFO") as captured, self.transport(responder):
            result = self.post(api)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(self.requests), 1, "started streams must never be retried")
        records = [json.loads(record.getMessage()) for record in captured.records]
        failures = [record for record in records if record["event"] == "upstream_stream_error"]
        self.assertEqual(len(failures), 1)
        self.assertFalse(any(record["event"] == "chat" for record in records))
        self.assertNotIn(PRIVATE, "\n".join(captured.output))
        self.assertLess(len(json.dumps(failures[0])), 4096)
        self.assertTrue(all(record.exc_info is None and not record.stack_info for record in captured.records))
        self.assertEqual(failures[0]["upstream_http_status"], 200)
        self.assertEqual(self.module._usage[CALLER]["requests"], 0)
        self.assertEqual(self.module._alias_usage["llm-trusted"]["requests"], 0)
        self.assertEqual(self.module._route_usage, {})
        self.assertNotIn("[DONE]", result.text)
        events = [json.loads(line[5:].strip()) for line in result.text.splitlines()
                  if line.startswith("data:")]
        self.assertFalse(any(event.get("type") in ("response.completed", "response.incomplete")
                             for event in events))
        self.assertFalse(any(choice.get("finish_reason") for event in events
                             for choice in event.get("choices", [])))
        return result, events, failures[0]

    def check_provider_failure(self, event, category="provider_error", code="unknown", error_type="unknown"):
        raw = sse(event)
        for api in ("responses", "chat/completions"):
            with self.subTest(api=api):
                result, events, failure = self.checked_request(api, lambda _: httpx.Response(
                    200, content=raw, headers={"content-type": "text/event-stream"}))
                self.assertEqual({key: failure[key] for key in
                    ("failure_category", "upstream_event", "provider_error_code", "provider_error_type")},
                    {"failure_category": category, "upstream_event": event["type"],
                     "provider_error_code": code, "provider_error_type": error_type})
                expected = ({"type": "error", "code": "upstream_error", "message": PUBLIC_FAILURE,
                             "param": None, "sequence_number": 0} if api == "responses" else
                            {"error": {"type": "upstream_error", "message": PUBLIC_FAILURE}})
                self.assertEqual(events, [expected], "private diagnostics must not change public SSE")
                self.assertNotIn(PRIVATE, result.text)

    def test_known_provider_codes_survive_only_in_operator_diagnostics(self):
        for code in ("server_error", "rate_limit_exceeded"):
            with self.subTest(code=code):
                self.check_provider_failure({"type": "error", "code": code, "message": PRIVATE,
                    "param": PRIVATE, PRIVATE: PRIVATE}, code=code)
        for code in ("context_length_exceeded", "image_parse_error"):
            with self.subTest(code=code):
                self.check_provider_failure({"type": "response.failed", "response": {
                    "id": PRIVATE, "error": {"code": code, "type": "invalid_request_error",
                    "message": PRIVATE, "param": PRIVATE}, "output": [{PRIVATE: PRIVATE}]}},
                    code=code, error_type="invalid_request_error")

    def test_cancelled_missing_and_malformed_provider_errors_are_distinct(self):
        cases = [
            ({"type": "response.cancelled", "response": {"error": {"message": PRIVATE}}}, "provider_cancelled"),
            ({"type": "response.cancelled", "response": PRIVATE}, "provider_cancelled"),
            ({"type": "response.failed", "response": {}}, "provider_error_missing"),
            ({"type": "response.failed", "response": {"error": None}}, "provider_error_missing"),
            ({"type": "response.failed", "response": PRIVATE}, "provider_error_malformed"),
            ({"type": "response.failed", "response": []}, "provider_error_malformed"),
        ]
        cases.extend(({"type": "response.failed", "response": {"error": value}}, "provider_error_malformed")
                     for value in (PRIVATE, [], False, 123))
        for event, category in cases:
            with self.subTest(category=category, event_type=event["type"]):
                self.check_provider_failure(event, category=category)

    def test_unknown_sensitive_oversized_and_nonstring_fields_are_not_logged(self):
        for value in (PRIVATE, PRIVATE * 4096, "server_error\n" + PRIVATE,
                      "context_length_exceeded_" + PRIVATE, {PRIVATE: PRIVATE}, [PRIVATE], None, 503, True):
            with self.subTest(value_type=type(value).__name__):
                self.check_provider_failure({"type": "error", "code": value, "message": PRIVATE})
                self.check_provider_failure({"type": "response.failed", "response": {
                    "error": {"code": value, "type": value, "message": PRIVATE}}})

    def test_failure_after_partial_output_cannot_retry_or_consume_later_success(self):
        final = response()
        raw = sse({"type": "response.created", "sequence_number": 0,
                   "response": {**final, "status": "in_progress", "output": []}},
                  {"type": "response.output_text.delta", "sequence_number": 1,
                   "output_index": 0, "content_index": 0, "delta": "partial"},
                  {"type": "response.failed", "sequence_number": 2, "response": {
                   "error": {"code": "server_error", "type": "server_error", "message": PRIVATE}}},
                  {"type": "response.completed", "sequence_number": 3, "response": final})
        for api in ("responses", "chat/completions"):
            with self.subTest(api=api):
                result, events, failure = self.checked_request(api, lambda _: httpx.Response(
                    200, content=raw, headers={"content-type": "text/event-stream"}))
                self.assertIn("partial", result.text)
                self.assertNotIn(PRIVATE, result.text)
                self.assertEqual(failure["provider_error_code"], "server_error")
                if api == "responses":
                    self.assertEqual(events[-1]["sequence_number"], 2)
                    self.assertEqual(events[-1]["type"], "error")
                else:
                    self.assertEqual(events[-1]["error"]["message"], PUBLIC_FAILURE)

    def test_malformed_and_truncated_sse_are_protocol_errors(self):
        for raw in (b"event: error\ndata: {invalid JSON}\n\n", sse({"type": "response.created",
                    "response": {**response(), "status": "in_progress", "output": []}})):
            for api in ("responses", "chat/completions"):
                with self.subTest(api=api, raw_size=len(raw)):
                    _, _, failure = self.checked_request(api, lambda _: httpx.Response(
                        200, content=raw, headers={"content-type": "text/event-stream"}))
                    self.assertEqual(failure["failure_category"], "protocol_error")
                    self.assertEqual(failure["upstream_event"], "unknown")
                    self.assertEqual(failure["provider_error_code"], "unknown")

    def test_read_failure_is_distinct_without_logging_transport_exception_text(self):
        prefix = sse({"type": "response.created", "response": {
            **response(), "status": "in_progress", "output": []}})
        for api in ("responses", "chat/completions"):
            with self.subTest(api=api):
                body = BrokenRead(prefix)
                _, _, failure = self.checked_request(api, lambda _: httpx.Response(
                    200, stream=body, headers={"content-type": "text/event-stream"}))
                self.assertEqual(failure["failure_category"], "transport_error")
                self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main()
