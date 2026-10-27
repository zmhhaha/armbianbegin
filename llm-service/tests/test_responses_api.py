"""Public Responses requests traverse the actual routing, guard and wire adapters."""
from __future__ import annotations

import importlib.util
import copy
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
from config import load_config, load_guard_config


def native_response(text="hello"):
    return {
        "id": "resp_native", "object": "response", "created_at": 1720000000,
        "model": "gpt-6.1-sol", "status": "completed", "error": None,
        "incomplete_details": None,
        "output": [{"id": "msg_native", "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}],
        "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18,
                  "input_tokens_details": {"cached_tokens": 4},
                  "output_tokens_details": {"reasoning_tokens": 3}},
    }


def chat_response(text="hello", *, calls=None, finish="stop"):
    message = {"role": "assistant", "content": text}
    if calls is not None:
        message["tool_calls"] = calls
    return {"id": "chatcmpl_deepseek", "object": "chat.completion", "created": 1720000000,
            "model": "deepseek-v4-flash", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
                      "prompt_cache_hit_tokens": 4, "completion_tokens_details": {"reasoning_tokens": 3}}}


def proxy_tool_response():
    result = native_response("查询天气")
    result["metadata"] = {"purpose": "caller-visible-response-metadata"}
    result["output"][0]["phase"] = "commentary"
    result["output"].append({"type": "function_call", "id": "fc_proxy", "call_id": "call_proxy", "name": "lookup",
                             "namespace": None, "arguments": '{"q":"天气"}', "status": "completed"})
    for item in result["output"]:
        item["metadata"] = {"proxy_internal": "private-value"}
        item["internal_chat_message_metadata_passthrough"] = {"proxy_internal": "private-value"}
    return result


def chat_chunk(delta=None, *, finish=None, usage=None):
    return {"id": "chatcmpl_deepseek", "object": "chat.completion.chunk", "created": 1720000000,
            "model": "deepseek-v4-flash", "choices": [] if usage is not None else [
                {"index": 0, "delta": delta or {}, "finish_reason": finish}],
            **({"usage": usage} if usage is not None else {})}


def native_sse(*events):
    return "".join("event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                   for event in events).encode("utf-8")


def chat_sse(*chunks, done=True):
    raw = "".join("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in chunks)
    return (raw + ("data: [DONE]\n\n" if done else "")).encode("utf-8")


def decoded_events(result):
    return [json.loads(line[5:].strip()) for line in result.text.splitlines() if line.startswith("data:")]


class PublicResponsesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing = json.loads((SERVICE_DIR / "config.example.json").read_text(encoding="utf-8"))
        env = {"LLM_TOKEN_RESPONSES_API_TEST": "responses-api-token", "LLM_ALIASES": json.dumps(cls.routing),
               "CUSTOM_API_KEY": "custom-test", "DEEPSEEK_API_KEY": "deepseek-test", "LLM_GUARD": ""}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("responses_api_test_app", SERVICE_DIR / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.client = TestClient(cls.module.app)
        cls.headers = {"Authorization": "Bearer responses-api-token"}

    def setUp(self):
        for counters in (self.module._windows, self.module._usage, self.module._alias_usage,
                         self.module._route_usage, self.module._guard_stats):
            counters.clear()
        self.requests = []

    def transport(self, responder):
        original = httpx.AsyncClient

        def handler(request):
            self.requests.append((str(request.url), json.loads(request.content)))
            return responder(request)

        transport = httpx.MockTransport(handler)
        return patch.object(upstream.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))

    def post(self, model="llm-trusted", **fields):
        return self.client.post("/v1/responses", headers=self.headers,
                                json={"model": model, "input": "你好", "store": False, **fields})

    def test_custom_upstream_preserves_native_responses_and_token_details(self):
        native = native_response("native output")
        with self.transport(lambda _: httpx.Response(200, json=native)):
            result = self.post(instructions="answer in Chinese", max_output_tokens=128)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), native)
        url, body = self.requests[0]
        self.assertTrue(url.endswith("/v1/responses"))
        self.assertEqual(body["model"], "gpt-6.1-sol")
        self.assertEqual(body["max_output_tokens"], 128)
        self.assertFalse(body["store"])
        self.assertNotIn("messages", body)
        self.assertEqual(body["instructions"], "answer in Chinese")
        self.assertEqual(body["input"], "你好")
        self.assertEqual(self.module._usage["responses-api-test"]["prompt_tokens"], 11)
        self.assertTrue(result.headers.get("x-llm-route-revision"))

    def test_deepseek_upstream_receives_chat_and_returns_responses(self):
        with self.transport(lambda _: httpx.Response(200, json=chat_response("deepseek output"))):
            result = self.post("deepseek-trusted", instructions="use Chinese", max_output_tokens=128)
        self.assertEqual(result.status_code, 200, result.text)
        url, body = self.requests[0]
        self.assertTrue(url.endswith("/v1/chat/completions"))
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["max_tokens"], 128)
        self.assertNotIn("input", body)
        self.assertEqual(body["messages"], [{"role": "system", "content": "use Chinese"}, {"role": "user", "content": "你好"}])
        response = result.json()
        self.assertEqual(response["object"], "response")
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["output"][0]["content"][0]["text"], "deepseek output")
        self.assertEqual(response["usage"]["input_tokens_details"]["cached_tokens"], 4)

    def test_native_proxy_output_is_replayable_across_upstreams(self):
        native = proxy_tool_response()
        with self.transport(lambda _: httpx.Response(200, json=native)):
            result = self.post(tools=[{"type": "function", "name": "lookup", "strict": False}])
        self.assertEqual(result.status_code, 200, result.text)
        output = result.json()["output"]
        self.assertEqual(result.json()["metadata"], native["metadata"])
        for item in output:
            self.assertNotIn("metadata", item)
            self.assertNotIn("internal_chat_message_metadata_passthrough", item)
        self.assertIn("metadata", native["output"][0])
        history = [{"role": "user", "content": "天气如何"}, *output,
                   {"type": "function_call_output", "call_id": "call_proxy", "output": "晴天"}]
        for alias, body in (("llm-trusted", native_response("天气晴朗")),
                            ("deepseek-trusted", chat_response("天气晴朗"))):
            with self.subTest(alias=alias), self.transport(lambda _: httpx.Response(200, json=body)):
                replay = self.post(alias, input=history)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json()["output"][0]["content"][0]["text"], "天气晴朗")

    def test_native_stream_filters_proxy_metadata_from_items_and_terminal(self):
        final = proxy_tool_response()
        events = [{"type": "response.metadata", "metadata": {"proxy_internal": "private-value"}},
                  {"type": "response.created", "response": {**final, "status": "in_progress", "output": []}}]
        for index, item in enumerate(final["output"]):
            events.extend([
                {"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress"}},
                {"type": "response.output_item.done", "output_index": index, "item": item},
            ])
        events.append({"type": "response.completed", "response": final})
        raw = native_sse(*events)
        with self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
            result = self.post(stream=True)
        self.assertEqual(result.status_code, 200, result.text)
        public_events = decoded_events(result)
        self.assertFalse(any(event["type"] == "response.metadata" for event in public_events))
        self.assertNotIn("private-value", result.text)
        for event in public_events:
            if "item" in event:
                self.assertNotIn("metadata", event["item"])
                self.assertNotIn("internal_chat_message_metadata_passthrough", event["item"])
        terminal = public_events[-1]
        self.assertEqual(terminal["type"], "response.completed")
        self.assertEqual(terminal["response"]["metadata"], final["metadata"])
        history = [{"role": "user", "content": "天气如何"}, *terminal["response"]["output"],
                   {"type": "function_call_output", "call_id": "call_proxy", "output": "晴天"}]
        with self.transport(lambda _: httpx.Response(200, json=native_response("天气晴朗"))):
            replay = self.post(input=history)
        self.assertEqual(replay.status_code, 200, replay.text)

    def test_public_sanitizers_only_remove_known_item_extensions_without_mutation(self):
        from responses_adapter import sanitize_event, sanitize_response
        original = proxy_tool_response()
        original["output"][0]["unknown_semantic_field"] = {"metadata": "preserve-me"}
        pristine = copy.deepcopy(original)
        result = sanitize_response(original)
        self.assertEqual(original, pristine)
        self.assertEqual(result["metadata"], original["metadata"])
        self.assertEqual(result["output"][0]["unknown_semantic_field"], {"metadata": "preserve-me"})
        result["output"][0]["content"][0]["text"] = "changed copy"
        self.assertEqual(original, pristine)
        event = {"type": "response.output_item.done", "output_index": 0, "item": original["output"][0]}
        clean_event = sanitize_event(event)
        self.assertNotIn("metadata", clean_event["item"])
        clean_event["item"]["content"].clear()
        self.assertEqual(original, pristine)
        self.assertIsNone(sanitize_event({"type": "response.metadata"}))
        unknown = {"type": "response.unknown", "unknown_semantic_field": {"metadata": "preserve-me"}}
        self.assertEqual(sanitize_event(unknown), unknown)

    def test_deepseek_function_call_round_trip_keeps_public_responses_contract(self):
        function = {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"天气"}'}}
        with self.transport(lambda _: httpx.Response(200, json=chat_response(None, calls=[function], finish="tool_calls"))):
            result = self.post("deepseek-trusted", tools=[{"type": "function", "name": "lookup", "strict": False,
                                                          "parameters": {"type": "object"}}],
                               tool_choice={"type": "function", "name": "lookup"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.requests[0][1]["tools"][0]["function"]["name"], "lookup")
        output = result.json()["output"][0]
        self.assertEqual((output["type"], output["call_id"], output["arguments"]), ("function_call", "call_1", '{"q":"天气"}'))
        history = [{"role": "user", "content": "天气如何"}, *result.json()["output"],
                   {"type": "function_call_output", "call_id": "call_1", "output": "晴天"}]
        with self.transport(lambda _: httpx.Response(200, json=chat_response("天气晴朗"))):
            second = self.post("deepseek-trusted", input=history)
        self.assertEqual(second.status_code, 200, second.text)
        sent = self.requests[-1][1]["messages"]
        self.assertEqual(sent[1]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(sent[2], {"role": "tool", "tool_call_id": "call_1", "content": "晴天"})

    def test_official_sdk_complete_output_can_be_replayed_with_tool_results(self):
        try:
            from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
        except ImportError:
            self.skipTest("optional official OpenAI SDK is unavailable")
        function = ResponseFunctionToolCall(
            type="function_call", id="fc_sdk", call_id="call_sdk", name="lookup",
            arguments='{"q":"天气"}', status="completed",
        ).model_dump()
        self.assertIn("namespace", function)
        self.assertIsNone(function["namespace"])
        for phase in (None, "commentary", "final_answer"):
            message = ResponseOutputMessage(
                id="msg_sdk", type="message", role="assistant", status="completed", phase=phase,
                content=[ResponseOutputText(type="output_text", text="查询天气", annotations=[])],
            ).model_dump()
            self.assertIn("phase", message)
            self.assertIn("logprobs", message["content"][0])
            history = [{"role": "user", "content": "天气如何"}, message, function,
                       {"type": "function_call_output", "call_id": "call_sdk", "output": "晴天"}]
            with self.subTest(phase=phase), self.transport(lambda _: httpx.Response(200, json=chat_response("天气晴朗"))):
                result = self.post("deepseek-trusted", input=history)
            self.assertEqual(result.status_code, 200, result.text)
            sent = self.requests[-1][1]["messages"]
            self.assertEqual(sent[1]["content"], "查询天气")
            self.assertEqual(sent[1]["tool_calls"][0]["id"], "call_sdk")
            self.assertEqual(sent[2], {"role": "tool", "tool_call_id": "call_sdk", "content": "晴天"})

    def test_deprecated_chat_stream_ignores_only_known_relay_metadata(self):
        final = native_response("metadata-safe")
        raw = native_sse(
            {"type": "response.metadata", "metadata": {"route": "relay"}},
            {"type": "response.created", "response": {**final, "status": "in_progress", "output": []}},
            {"type": "response.metadata", "metadata": {"route": "relay"}},
            {"type": "response.completed", "response": final},
        )
        with self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
            result = self.client.post("/v1/chat/completions", headers=self.headers,
                                      json={"model": "llm-trusted", "messages": [{"role": "user", "content": "hello"}], "stream": True})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("metadata-safe", result.text)
        self.assertIn("data: [DONE]", result.text)
        self.assertNotIn('"error"', result.text)

    def test_switching_active_upstream_keeps_the_same_public_responses_request(self):
        for active, expected_suffix, answer in (("custom", "/v1/responses", "custom"),
                                                ("deepseek", "/v1/chat/completions", "deepseek")):
            with self.subTest(active=active), patch.dict(os.environ, {"LLM_ALIASES": json.dumps({**self.routing, "active_upstream": active})}):
                routes, _ = load_config()
                upstream_body = native_response(answer) if active == "custom" else chat_response(answer)
                with patch.object(self.module, "ALIASES", routes), self.transport(lambda _: httpx.Response(200, json=upstream_body)):
                    result = self.post()
                self.assertEqual(result.status_code, 200, result.text)
                self.assertTrue(self.requests[-1][0].endswith(expected_suffix))
                self.assertEqual(result.json()["object"], "response")
                self.assertEqual(result.json()["output"][0]["content"][0]["text"], answer)

    def test_custom_stream_is_typed_responses_and_records_usage(self):
        final = native_response("hello")
        raw = native_sse({"type": "response.created", "response": {**final, "status": "in_progress", "output": []}},
                         {"type": "response.output_text.delta", "item_id": "msg_native", "output_index": 0, "content_index": 0, "delta": "hello"},
                         {"type": "response.completed", "response": final})
        with self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
            result = self.post(stream=True)
        self.assertEqual(result.status_code, 200, result.text)
        events = decoded_events(result)
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual(events[-1]["response"], final)
        self.assertNotIn("[DONE]", result.text)
        self.assertEqual(self.module._usage["responses-api-test"]["completion_tokens"], 7)

    def test_deepseek_stream_becomes_typed_responses_with_final_usage(self):
        raw = chat_sse(chat_chunk({"role": "assistant", "content": "您"}), chat_chunk({"content": "好"}),
                       chat_chunk(finish="stop"), chat_chunk(usage=chat_response()["usage"]))
        with self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
            result = self.post("deepseek-trusted", stream=True)
        self.assertEqual(result.status_code, 200, result.text)
        events = decoded_events(result)
        self.assertEqual(events[0]["type"], "response.created")
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual("".join(event["delta"] for event in events if event["type"] == "response.output_text.delta"), "您好")
        self.assertEqual(events[-1]["response"]["usage"]["input_tokens"], 11)
        self.assertEqual(self.requests[0][1]["stream_options"], {"include_usage": True})
        self.assertEqual(self.module._usage["responses-api-test"]["completion_tokens"], 7)

    def test_deepseek_streamed_function_arguments_have_stable_ids(self):
        raw = chat_sse(chat_chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":'}}]}),
                       chat_chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"weather"}'}}]}),
                       chat_chunk(finish="tool_calls"), chat_chunk(usage=chat_response()["usage"]))
        with self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
            result = self.post("deepseek-trusted", stream=True, tools=[{"type": "function", "name": "lookup", "strict": False}])
        self.assertEqual(result.status_code, 200, result.text)
        events = decoded_events(result)
        self.assertEqual(events[-1]["type"], "response.completed")
        function = events[-1]["response"]["output"][0]
        self.assertEqual((function["call_id"], function["arguments"]), ("call_1", '{"q":"weather"}'))
        deltas = [event for event in events if event["type"] == "response.function_call_arguments.delta"]
        self.assertTrue(all(event["item_id"] == function["id"] for event in deltas))

    def test_large_terminal_snapshots_keep_usage_outside_the_tail_window(self):
        answer = "中" * 20000
        native = native_response(answer)
        native_raw = native_sse({"type": "response.completed", "response": native})
        chat_raw = chat_sse(chat_chunk({"content": answer}), chat_chunk(finish="stop"), chat_chunk(usage=chat_response()["usage"]))
        for alias, raw in (("llm-trusted", native_raw), ("deepseek-trusted", chat_raw)):
            with self.subTest(alias=alias):
                self.module._usage.clear()
                with self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
                    result = self.post(alias, stream=True)
                self.assertEqual(result.status_code, 200, result.text[:1000])
                self.assertEqual(decoded_events(result)[-1]["type"], "response.completed")
                self.assertEqual(self.module._usage["responses-api-test"], {"requests": 1, "prompt_tokens": 11, "completion_tokens": 7})

    def test_truncated_streams_emit_error_without_success_or_usage(self):
        native = native_response()
        custom_raw = native_sse({"type": "response.created", "response": {**native, "status": "in_progress", "output": []}})
        deepseek_raw = chat_sse(chat_chunk({"content": "partial"}), chat_chunk(finish="stop"), done=False)
        for alias, raw in (("llm-trusted", custom_raw), ("deepseek-trusted", deepseek_raw)):
            with self.subTest(alias=alias), self.transport(lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
                result = self.post(alias, stream=True)
            events = decoded_events(result)
            self.assertEqual(events[-1]["type"], "error")
            self.assertFalse(any(event["type"] in ("response.completed", "response.incomplete") for event in events))
            self.assertEqual(self.module._usage["responses-api-test"]["requests"], 0)

    def test_authentication_prevents_upstream_access(self):
        with self.transport(lambda _: self.fail("unauthenticated request reached upstream")):
            for headers in ({}, {"Authorization": "Bearer invalid"}):
                result = self.client.post("/v1/responses", headers=headers, json={"model": "llm-trusted", "input": "hello"})
                self.assertEqual(result.status_code, 401, result.text)
        self.assertFalse(self.requests)

    def test_rate_limit_is_shared_with_the_deprecated_chat_entrypoint(self):
        with patch.object(self.module, "RPM_LIMIT", 1), self.transport(lambda _: httpx.Response(200, json=native_response())):
            first = self.post()
            second = self.client.post("/v1/chat/completions", headers=self.headers,
                                      json={"model": "llm-trusted", "messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 429, second.text)
        self.assertEqual(len(self.requests), 1)

    def test_guarded_requests_apply_prompt_guards_and_enforce_tier_limits(self):
        with self.transport(lambda _: httpx.Response(200, json=native_response())):
            result = self.post("llm-guarded")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("<<<UNTRUSTED_USER_DATA>>>", json.dumps(self.requests[0][1]["input"]))
        with self.transport(lambda _: self.fail("guarded capability rejection reached upstream")):
            too_many_tokens = self.post("llm-guarded", max_output_tokens=2049)
            tools = self.post("llm-guarded", tools=[{"type": "function", "name": "lookup", "strict": False}])
        self.assertEqual(too_many_tokens.status_code, 400, too_many_tokens.text)
        self.assertEqual(tools.status_code, 400, tools.text)

    def test_canary_rejection_preserves_responses_safety_behavior(self):
        with patch.dict(os.environ, {"LLM_GUARD": json.dumps({"canary_action": "reject"})}):
            guard = load_guard_config()
        with patch.object(self.module, "GUARD", guard), patch.object(self.module, "new_canary", return_value="CANARY_API_TEST"), self.transport(
                lambda _: httpx.Response(200, json=native_response("CANARY_API_TEST"))):
            result = self.post("llm-guarded")
        self.assertEqual(result.status_code, 502, result.text)
        self.assertEqual(self.module._guard_stats["responses-api-test"]["canary_leaks"], 1)
        self.assertEqual(self.module._usage["responses-api-test"]["requests"], 0)

    def test_canary_rejection_scans_large_terminal_before_trimming_the_tail(self):
        with patch.dict(os.environ, {"LLM_GUARD": json.dumps({"canary_action": "reject"})}):
            guard = load_guard_config()
        raw = native_sse({"type": "response.completed", "response": native_response("CANARY_API_TEST" + "中" * 20000)})
        with patch.object(self.module, "GUARD", guard), patch.object(self.module, "new_canary", return_value="CANARY_API_TEST"), self.transport(
                lambda _: httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})):
            result = self.post("llm-guarded", stream=True)
        self.assertEqual(result.status_code, 200)
        self.assertFalse("CANARY_API_TEST" in result.text, "canary escaped through a large terminal frame")
        self.assertFalse(any(event["type"] == "response.completed" for event in decoded_events(result)))
        self.assertEqual(self.module._guard_stats["responses-api-test"]["canary_leaks"], 1)
        self.assertEqual(self.module._usage["responses-api-test"]["requests"], 0)

    def test_state_and_unsupported_structures_are_rejected_before_upstream(self):
        with self.transport(lambda _: self.fail("invalid Responses request reached upstream")):
            for fields in ({"store": True}, {"previous_response_id": "resp_old"}, {"conversation": "conv_old"},
                           {"reasoning": {"effort": "high"}}, {"tools": [{"type": "web_search"}]},
                           {"input": [{"type": "function_call", "call_id": "call_1", "name": "lookup", "arguments": "{}", "namespace": "external"}]},
                           {"input": [{"role": "assistant", "content": "history", "phase": "unknown"}]},
                           {"input": [{"type": "unknown", "text": "must not disappear"}]},
                           {"input": [{"role": "user", "content": [{"type": "input_audio", "data": "hidden"}]}]},
                           {"text": {"format": {"type": "unknown"}}}):
                with self.subTest(fields=fields):
                    result = self.post(**fields)
                    self.assertIn(result.status_code, (400, 422), result.text)
        self.assertFalse(self.requests)


if __name__ == "__main__":
    unittest.main()
