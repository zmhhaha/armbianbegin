"""The public Responses contract must survive a DeepSeek Chat upstream."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from chat_adapter import from_chat_response, from_chat_stream, to_chat_request  # noqa: E402
from responses_adapter import ResponsesProtocolError, ResponsesRequestError  # noqa: E402


def chat_response(*, text="您好", calls=None, finish="stop", usage=None):
    message = {"role": "assistant", "content": text}
    if calls is not None:
        message["tool_calls"] = calls
    return {
        "id": "chatcmpl_123", "object": "chat.completion", "created": 1720000000,
        "model": "deepseek-chat", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage or {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
                           "prompt_tokens_details": {"cached_tokens": 4},
                           "completion_tokens_details": {"reasoning_tokens": 3}},
    }


def call(call_id="call_a", name="lookup", arguments='{"q":"天气"}'):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def chunk(delta=None, *, finish=None, usage=None):
    result = {
        "id": "chatcmpl_123", "object": "chat.completion.chunk", "created": 1720000000,
        "model": "deepseek-chat", "choices": [] if usage is not None else [
            {"index": 0, "delta": delta or {}, "finish_reason": finish}],
    }
    if usage is not None:
        result["usage"] = usage
    return result


async def chat_lines(chunks, *, done=True):
    yield ": heartbeat"
    yield ""
    for part in chunks:
        yield "data: " + json.dumps(part, ensure_ascii=False)
        yield ""
    if done:
        yield "data: [DONE]"
        yield ""


def events_of(wire):
    events = []
    for frame in b"".join(wire).decode("utf-8").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:"))
        if data:
            events.append(json.loads(data))
    return events


class ResponsesToChatRequestTests(unittest.TestCase):
    def test_string_input_and_instructions_preserve_role_order_and_parameters(self):
        body = {"model": "llm-trusted", "input": "你好", "instructions": "请用中文",
                "temperature": 0.2, "top_p": 0.9, "max_output_tokens": 512, "store": False}
        original = copy.deepcopy(body)
        messages, params = to_chat_request(body)
        self.assertEqual(messages, [{"role": "system", "content": "请用中文"}, {"role": "user", "content": "你好"}])
        self.assertEqual(params["max_tokens"], 512)
        self.assertEqual(params["temperature"], 0.2)
        self.assertEqual(params["top_p"], 0.9)
        for response_only in ("input", "instructions", "max_output_tokens", "store"):
            self.assertNotIn(response_only, params)
        self.assertEqual(body, original)

    def test_image_input_and_assistant_text_become_chat_content(self):
        messages, _ = to_chat_request({"model": "llm-trusted", "input": [
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "识别图片"},
                {"type": "input_image", "image_url": "https://example.invalid/a.png", "detail": "low"},
            ]},
            {"role": "assistant", "content": "我看到了图片"},
        ]})
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], [
            {"type": "text", "text": "识别图片"},
            {"type": "image_url", "image_url": {"url": "https://example.invalid/a.png", "detail": "low"}},
        ])
        self.assertEqual(messages[-1], {"role": "assistant", "content": "我看到了图片"})

    def test_parallel_function_history_preserves_call_identity_and_tool_output_order(self):
        messages, _ = to_chat_request({"model": "llm-trusted", "input": [
            {"role": "user", "content": "同时查询两个城市"},
            {"type": "function_call", "call_id": "call_a", "name": "weather", "arguments": '{"city":"北京"}'},
            {"type": "function_call", "call_id": "call_b", "name": "weather", "arguments": '{"city":"上海"}'},
            {"type": "function_call_output", "call_id": "call_b", "output": "上海晴"},
            {"type": "function_call_output", "call_id": "call_a", "output": "北京雨"},
            {"role": "assistant", "content": "两地天气不同"},
            {"role": "user", "content": "哪个适合出行"},
        ]})
        calls = [tool for message in messages for tool in message.get("tool_calls", [])]
        self.assertEqual([tool["id"] for tool in calls], ["call_a", "call_b"])
        self.assertTrue(all(message["role"] == "assistant" for message in messages if message.get("tool_calls")))
        self.assertEqual(calls[0]["function"], {"name": "weather", "arguments": '{"city":"北京"}'})
        outputs = [message for message in messages if message["role"] == "tool"]
        self.assertEqual([(message["tool_call_id"], message["content"]) for message in outputs], [("call_b", "上海晴"), ("call_a", "北京雨")])
        self.assertEqual(messages[-2:], [{"role": "assistant", "content": "两地天气不同"}, {"role": "user", "content": "哪个适合出行"}])

    def test_flattened_tools_choice_and_json_schema_restore_chat_shapes(self):
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
        _, params = to_chat_request({"model": "llm-trusted", "input": "回答", "tools": [
            {"type": "function", "name": "lookup", "description": "查询", "parameters": schema, "strict": False},
            {"type": "function", "name": "strict_lookup", "parameters": schema, "strict": True},
        ], "tool_choice": {"type": "function", "name": "lookup"},
            "text": {"format": {"type": "json_schema", "name": "answer", "strict": True, "schema": schema}}})
        self.assertEqual(params["tools"][0], {"type": "function", "function": {"name": "lookup", "description": "查询", "parameters": schema, "strict": False}})
        self.assertTrue(params["tools"][1]["function"]["strict"])
        self.assertEqual(params["tool_choice"], {"type": "function", "function": {"name": "lookup"}})
        self.assertEqual(params["response_format"], {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}})

    def test_stateless_contract_rejects_state_and_features_without_chat_equivalent(self):
        for fields in (
            {"store": True}, {"previous_response_id": "resp_previous"}, {"conversation": "conv_1"},
            {"background": True}, {"include": ["reasoning.encrypted_content"]},
            {"reasoning": {"effort": "high"}}, {"mystery": 1},
            {"tools": [{"type": "web_search_preview"}]},
        ):
            with self.subTest(fields=fields), self.assertRaises(ResponsesRequestError):
                to_chat_request({"model": "llm-trusted", "input": "你好", **fields})

    def test_unknown_input_content_and_malformed_functions_are_rejected(self):
        for input_items in (
            [{"role": "user", "content": [{"type": "input_audio", "data": "secret"}]}],
            [{"type": "function_call", "call_id": "call_1", "name": "lookup", "arguments": {}}],
            [{"type": "function_call_output", "output": "missing call id"}],
            [{"type": "unrecognized", "content": "must not be lost"}],
        ):
            with self.subTest(input_items=input_items), self.assertRaises(ResponsesRequestError):
                to_chat_request({"model": "llm-trusted", "input": input_items})


class ChatToResponsesResultTests(unittest.TestCase):
    def test_text_identity_and_usage_details_use_responses_shape(self):
        data = from_chat_response(chat_response())
        self.assertEqual(data["object"], "response")
        self.assertTrue(data["id"])
        self.assertEqual(data["created_at"], 1720000000)
        self.assertEqual(data["model"], "deepseek-chat")
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["output"][0]["type"], "message")
        self.assertEqual(data["output"][0]["role"], "assistant")
        self.assertEqual(data["output"][0]["content"][0]["type"], "output_text")
        self.assertEqual(data["output"][0]["content"][0]["text"], "您好")
        self.assertEqual(data["usage"]["input_tokens"], 11)
        self.assertEqual(data["usage"]["output_tokens"], 7)
        self.assertEqual(data["usage"]["total_tokens"], 18)
        self.assertEqual(data["usage"]["input_tokens_details"]["cached_tokens"], 4)
        self.assertEqual(data["usage"]["output_tokens_details"]["reasoning_tokens"], 3)

    def test_parallel_calls_remain_function_items_and_reasoning_is_not_answer_text(self):
        source = chat_response(text=None, calls=[call(), call("call_b", "second", '{"q":"b"}')], finish="tool_calls")
        source["choices"][0]["message"]["reasoning_content"] = "provider reasoning"
        data = from_chat_response(source)
        self.assertEqual(data["status"], "completed")
        items = [item for item in data["output"] if item["type"] == "function_call"]
        self.assertEqual([item["call_id"] for item in items], ["call_a", "call_b"])
        self.assertEqual(items[0]["name"], "lookup")
        self.assertEqual(items[0]["arguments"], '{"q":"天气"}')
        self.assertNotIn("provider reasoning", json.dumps(data))

    def test_refusal_and_incomplete_reasons_are_not_replaced_with_completed_text(self):
        refused = chat_response(text=None)
        refused["choices"][0]["message"]["refusal"] = "不能协助"
        output = from_chat_response(refused)["output"]
        self.assertEqual(output[0]["content"][0], {"type": "refusal", "refusal": "不能协助"})
        for finish, reason in (("length", "max_output_tokens"), ("content_filter", "content_filter")):
            with self.subTest(finish=finish):
                data = from_chat_response(chat_response(finish=finish))
                self.assertEqual(data["status"], "incomplete")
                self.assertEqual(data["incomplete_details"]["reason"], reason)

    def test_deepseek_native_cache_count_has_a_standard_responses_location(self):
        data = from_chat_response(chat_response(usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
                                                       "prompt_cache_hit_tokens": 4, "prompt_cache_miss_tokens": 7}))
        self.assertEqual(data["usage"]["input_tokens_details"]["cached_tokens"], 4)

    def test_malformed_successes_do_not_become_empty_completed_responses(self):
        missing_choices = chat_response()
        missing_choices.pop("choices")
        missing_message = chat_response()
        missing_message["choices"][0].pop("message")
        unknown_finish = chat_response(finish="unknown")
        bad_function = chat_response(text=None, calls=[call(arguments={})], finish="tool_calls")
        multiple_choices = chat_response()
        multiple_choices["choices"].append({"index": 1, "message": {"role": "assistant", "content": "another"}, "finish_reason": "stop"})
        for data in ({}, [], missing_choices, missing_message, unknown_finish, bad_function, multiple_choices):
            with self.subTest(data=data), self.assertRaises(ResponsesProtocolError):
                from_chat_response(data)


class ChatToResponsesStreamTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, chunks, *, done=True):
        return [part async for part in from_chat_stream(chat_lines(chunks, done=done))]

    async def test_unicode_text_stream_has_typed_events_and_terminal_usage(self):
        usage = chat_response()["usage"]
        wire = await self.collect([
            chunk({"role": "assistant", "content": ""}), chunk({"reasoning_content": "provider private reasoning"}),
            chunk({"content": "您"}), chunk({"content": "好"}),
            chunk(finish="stop"), chunk(usage=usage),
        ])
        self.assertTrue(all(isinstance(part, bytes) for part in wire))
        self.assertNotIn(b"provider private reasoning", b"".join(wire))
        events = events_of(wire)
        self.assertEqual(events[0]["type"], "response.created")
        deltas = [event["delta"] for event in events if event["type"] == "response.output_text.delta"]
        self.assertEqual("".join(deltas), "您好")
        terminal = [event for event in events if event["type"] == "response.completed"]
        self.assertEqual(len(terminal), 1)
        self.assertEqual(events[-1], terminal[0])
        data = terminal[0]["response"]
        self.assertEqual(data["output"][0]["content"][0]["text"], "您好")
        self.assertEqual(data["usage"]["input_tokens"], 11)
        self.assertEqual(data["usage"]["output_tokens_details"]["reasoning_tokens"], 3)
        types = [event["type"] for event in events]
        self.assertLess(types.index("response.output_item.added"), types.index("response.output_text.delta"))
        self.assertIn("response.output_text.done", types)
        self.assertIn("response.output_item.done", types)

    async def test_tool_names_argument_fragments_and_parallel_identity_are_preserved(self):
        wire = await self.collect([
            chunk({"role": "assistant"}),
            chunk({"tool_calls": [{"index": 0, "id": "call_a", "type": "function", "function": {"name": "look", "arguments": ""}}]}),
            chunk({"tool_calls": [{"index": 1, "id": "call_b", "type": "function", "function": {"name": "second", "arguments": '{"q":'}}]}),
            chunk({"tool_calls": [{"index": 0, "function": {"name": "up", "arguments": '{"q":"'}}]}),
            chunk({"tool_calls": [{"index": 1, "function": {"arguments": '"b"}'}}]}),
            chunk({"tool_calls": [{"index": 0, "function": {"arguments": '天气"}'}}]}),
            chunk(finish="tool_calls"), chunk(usage=chat_response()["usage"]),
        ])
        events = events_of(wire)
        terminal = events[-1]
        self.assertEqual(terminal["type"], "response.completed")
        functions = [item for item in terminal["response"]["output"] if item["type"] == "function_call"]
        self.assertEqual([(item["call_id"], item["name"], item["arguments"]) for item in functions], [
            ("call_a", "lookup", '{"q":"天气"}'), ("call_b", "second", '{"q":"b"}'),
        ])
        for index, function_item in enumerate(functions):
            added = [event for event in events if event["type"] == "response.output_item.added" and event["item"].get("call_id") == function_item["call_id"]]
            self.assertEqual(len(added), 1)
            item_id = added[0]["item"]["id"]
            self.assertEqual(added[0]["output_index"], index)
            arguments = "".join(event["delta"] for event in events if event["type"] == "response.function_call_arguments.delta" and event["item_id"] == item_id)
            self.assertEqual(arguments, function_item["arguments"])
            done = [event for event in events if event["type"] == "response.function_call_arguments.done" and event["item_id"] == item_id]
            self.assertEqual(len(done), 1)
            self.assertEqual(done[0]["arguments"], function_item["arguments"])

    async def test_length_finish_is_an_incomplete_responses_terminal(self):
        events = events_of(await self.collect([chunk({"content": "partial"}), chunk(finish="length")]))
        self.assertEqual(events[-1]["type"], "response.incomplete")
        self.assertEqual(events[-1]["response"]["incomplete_details"]["reason"], "max_output_tokens")
        self.assertFalse(any(event["type"] == "response.completed" for event in events))

    async def test_missing_done_missing_finish_and_provider_errors_never_emit_success_terminal(self):
        cases = [([], False), ([chunk({"content": "partial"})], False),
                 ([chunk({"content": "partial"}), chunk(finish="stop")], False),
                 ([chunk({"content": "partial"})], True),
                 ([{"error": {"message": "upstream secret", "code": "server_error"}}], True)]
        for chunks, done in cases:
            wire = []
            with self.subTest(chunks=chunks, done=done):
                with self.assertRaises(ResponsesProtocolError):
                    async for part in from_chat_stream(chat_lines(chunks, done=done)):
                        wire.append(part)
                self.assertFalse(any(event["type"] in ("response.completed", "response.incomplete") for event in events_of(wire)))
                self.assertNotIn(b"upstream secret", b"".join(wire))

    async def test_malformed_json_is_not_ignored(self):
        async def broken_lines():
            for line in ("data: {not json}", "", "data: [DONE]", ""):
                yield line
        with self.assertRaises(ResponsesProtocolError):
            _ = [part async for part in from_chat_stream(broken_lines())]


if __name__ == "__main__":
    unittest.main()
