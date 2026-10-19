"""Wire-contract tests for the custom Responses upstream / Chat client bridge."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from responses_adapter import (  # noqa: E402
    ResponsesProtocolError,
    ResponsesRequestError,
    build_request,
    translate_response,
    translate_stream,
)


def message(text="你好", *, item_id="msg_1"):
    return {
        "type": "message", "id": item_id, "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def function(call_id="call_1", *, name="lookup", arguments='{"q":"天气"}', item_id="fc_1"):
    return {
        "type": "function_call", "id": item_id, "call_id": call_id, "name": name,
        "arguments": arguments, "status": "completed",
    }


def citation(start, end, url="https://example.invalid/source"):
    return {"type": "url_citation", "start_index": start, "end_index": end, "url": url, "title": "Source"}


def response(output=None, *, status="completed", incomplete_details=None):
    return {
        "id": "resp_123", "object": "response", "created_at": 1720000000,
        "model": "gpt-6-astra", "status": status,
        "output": [message()] if output is None else output,
        "incomplete_details": incomplete_details, "error": None,
        "usage": {
            "input_tokens": 11, "output_tokens": 7, "total_tokens": 18,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens_details": {"reasoning_tokens": 3},
        },
    }


async def lines_of(events, *, multiline=False):
    """An httpx aiter_lines source, including SSE framing and ignored fields."""
    yield ": keepalive"
    yield ""
    for event in events:
        yield "event: " + event["type"]
        raw = json.dumps(event, ensure_ascii=False)
        if multiline:
            # SSE permits multiple data fields, joined with a newline. Split at
            # JSON punctuation rather than within a string value.
            split = raw.index(",") + 1
            yield "data: " + raw[:split]
            yield "data: " + raw[split:]
        else:
            yield "data: " + raw
        yield ""


def chat_chunks(wire):
    result = []
    for frame in b"".join(wire).decode("utf-8").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:"))
        if data and data != "[DONE]":
            result.append(json.loads(data))
    return result


class ResponsesRequestTests(unittest.TestCase):
    def test_request_preserves_roles_and_parameter_meaning_without_mutating_input(self):
        messages = [
            {"role": "system", "content": "守住边界"},
            {"role": "developer", "content": "输出中文"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "您好"},
        ]
        params = {"temperature": 0.2, "top_p": 0.8, "max_tokens": 512, "n": 1}
        original = copy.deepcopy((messages, params))
        body = build_request("gpt-6-astra", messages, params)
        self.assertEqual(body["model"], "gpt-6-astra")
        self.assertEqual([item["role"] for item in body["input"]], ["system", "developer", "user", "assistant"])
        self.assertEqual(body["input"][2]["content"], [{"type": "input_text", "text": "你好"}])
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["top_p"], 0.8)
        self.assertEqual(body["max_output_tokens"], 512)
        self.assertFalse(body["store"])
        self.assertFalse(body["stream"])
        for old_field in ("messages", "max_tokens", "stream_options", "n"):
            self.assertNotIn(old_field, body)
        self.assertEqual((messages, params), original)

    def test_image_and_parallel_tool_history_keep_call_identity_and_order(self):
        body = build_request("gpt-6-astra", [
            {"role": "user", "content": [
                {"type": "text", "text": "查看图片"},
                {"type": "image_url", "image_url": {"url": "https://example.invalid/a.png", "detail": "low"}},
            ]},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_a", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"a"}'}},
                {"id": "call_b", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"b"}'}},
            ]},
            {"role": "tool", "tool_call_id": "call_b", "content": "结果乙"},
            {"role": "tool", "tool_call_id": "call_a", "content": "结果甲"},
        ], {})
        self.assertEqual(body["input"][0]["content"][1], {
            "type": "input_image", "image_url": "https://example.invalid/a.png", "detail": "low",
        })
        items = body["input"][1:]
        self.assertEqual([item["type"] for item in items], [
            "function_call", "function_call", "function_call_output", "function_call_output",
        ])
        self.assertEqual([item["call_id"] for item in items], ["call_a", "call_b", "call_b", "call_a"])
        self.assertEqual(items[-1]["output"], "结果甲")

    def test_assistant_history_with_text_and_tool_calls_uses_easy_input_messages(self):
        for assistant_content in ("我先查询天气", [{"type": "text", "text": "我先查询"}, {"type": "text", "text": "天气"}]):
            with self.subTest(content=assistant_content):
                body = build_request("model", [
                    {"role": "user", "content": "查一下天气"},
                    {"role": "assistant", "content": assistant_content, "tool_calls": [
                        {"id": "call_weather", "type": "function", "function": {"name": "weather", "arguments": '{"city":"北京"}'}},
                    ]},
                    {"role": "tool", "tool_call_id": "call_weather", "content": "晴"},
                ], {})
                items = body["input"]
                self.assertEqual([item["type"] for item in items], ["message", "message", "function_call", "function_call_output"])
                self.assertEqual(items[1]["role"], "assistant")
                self.assertEqual(items[1]["content"], "我先查询天气")
                self.assertEqual(items[2]["call_id"], "call_weather")
                self.assertEqual(items[3], {"type": "function_call_output", "call_id": "call_weather", "output": "晴"})

    def test_functions_keep_chat_non_strict_default_and_explicit_strict_setting(self):
        body = build_request("model", [{"role": "user", "content": "运行"}], {
            "tools": [
                {"type": "function", "function": {"name": "lookup", "description": "查询", "parameters": {"type": "object"}}},
                {"type": "function", "function": {"name": "strict_lookup", "strict": True, "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
            ],
            "tool_choice": {"type": "function", "function": {"name": "lookup"}},
        })
        self.assertEqual(body["tools"][0]["type"], "function")
        self.assertEqual(body["tools"][0]["name"], "lookup")
        self.assertFalse(body["tools"][0]["strict"])
        self.assertTrue(body["tools"][1]["strict"])
        self.assertEqual(body["tool_choice"], {"type": "function", "name": "lookup"})
        self.assertNotIn("function", body["tools"][0])

    def test_structured_output_schema_is_flattened_into_text_format(self):
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
        body = build_request("model", [{"role": "user", "content": "回答"}], {
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}},
        }, stream=True)
        self.assertEqual(body["text"]["format"], {"type": "json_schema", "name": "answer", "strict": True, "schema": schema})
        self.assertTrue(body["stream"])
        self.assertNotIn("response_format", body)
        self.assertNotIn("stream_options", body)

    def test_json_object_and_string_tool_choice_keep_their_meaning(self):
        body = build_request("model", [{"role": "user", "content": "JSON"}], {
            "response_format": {"type": "json_object"}, "tool_choice": "none",
        })
        self.assertEqual(body["text"]["format"], {"type": "json_object"})
        self.assertEqual(body["tool_choice"], "none")

    def test_unrepresentable_parameters_are_rejected_instead_of_silently_dropped(self):
        for params in ({"stop": ["END"]}, {"seed": 42}, {"n": 2}, {"presence_penalty": 0.5}, {"frequency_penalty": 1}, {"mystery": "x"}):
            with self.subTest(params=params), self.assertRaises(ResponsesRequestError):
                build_request("model", [{"role": "user", "content": "hi"}], params)

    def test_unsupported_message_content_and_tools_are_rejected(self):
        cases = [
            ([{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "AAAA", "format": "wav"}}]}], {}),
            ([{"role": "user", "content": "hi", "unknown": "lost"}], {}),
            ([{"role": "function", "name": "legacy", "content": "old"}], {}),
            ([{"role": "tool", "content": "missing call id"}], {}),
            ([{"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "f", "arguments": {}}}]}], {}),
            ([{"role": "assistant", "content": None, "refusal": "不能协助"}], {}),
            ([{"role": "user", "content": "hi"}], {"tools": [{"type": "web_search"}]}),
            ([{"role": "user", "content": "hi"}], {"response_format": {"type": "unrecognized"}}),
        ]
        for messages, params in cases:
            with self.subTest(messages=messages, params=params), self.assertRaises(ResponsesRequestError):
                build_request("model", messages, params)


class ResponsesResultTests(unittest.TestCase):
    def test_completed_text_and_token_detail_are_chat_compatible(self):
        data = translate_response(response())
        self.assertEqual(data["id"], "resp_123")
        self.assertEqual(data["object"], "chat.completion")
        self.assertEqual(data["created"], 1720000000)
        self.assertEqual(data["model"], "gpt-6-astra")
        self.assertEqual(data["choices"][0]["message"]["content"], "你好")
        self.assertEqual(data["choices"][0]["finish_reason"], "stop")
        self.assertEqual(data["usage"]["prompt_tokens"], 11)
        self.assertEqual(data["usage"]["completion_tokens"], 7)
        self.assertEqual(data["usage"]["total_tokens"], 18)
        self.assertEqual(data["usage"]["prompt_tokens_details"]["cached_tokens"], 4)
        self.assertEqual(data["usage"]["completion_tokens_details"]["reasoning_tokens"], 3)

    def test_reasoning_items_are_not_exposed_as_answer_and_function_calls_keep_call_id(self):
        data = translate_response(response([
            {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "private"}]},
            function("call_1"), function("call_2", name="lookup_two", item_id="fc_2"),
        ]))
        choice = data["choices"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertIn(choice["message"]["content"], (None, ""))
        calls = choice["message"]["tool_calls"]
        self.assertEqual([item["id"] for item in calls], ["call_1", "call_2"])
        self.assertEqual(calls[0]["function"], {"name": "lookup", "arguments": '{"q":"天气"}'})
        self.assertNotIn("private", json.dumps(data))

    def test_refusal_is_preserved_as_refusal_not_happy_path_text(self):
        item = message()
        item["content"] = [{"type": "refusal", "refusal": "无法协助"}]
        choice = translate_response(response([item]))["choices"][0]
        self.assertEqual(choice["message"]["refusal"], "无法协助")
        self.assertIn(choice["message"]["content"], (None, ""))

    def test_citation_offsets_follow_concatenated_text_across_parts_and_messages(self):
        first = message("one")
        first["content"].append({"type": "output_text", "text": "two", "annotations": [citation(0, 3, "https://example.invalid/two")]})
        second = message("XYZ", item_id="msg_2")
        second["content"][0]["annotations"] = [citation(1, 3, "https://example.invalid/yz")]
        result = translate_response(response([first, second]))["choices"][0]["message"]
        self.assertEqual(result["content"], "onetwoXYZ")
        self.assertEqual([(a["url_citation"]["start_index"], a["url_citation"]["end_index"]) for a in result["annotations"]], [(3, 6), (7, 9)])

    def test_incomplete_reasons_map_to_chat_finish_reasons(self):
        for reason, expected in (("max_output_tokens", "length"), ("content_filter", "content_filter")):
            with self.subTest(reason=reason):
                data = response(status="incomplete", incomplete_details={"reason": reason})
                self.assertEqual(translate_response(data)["choices"][0]["finish_reason"], expected)

    def test_failed_and_nonterminal_or_malformed_success_objects_are_errors(self):
        cases = [
            {}, [], response(status="failed"), response(status="in_progress"),
            response([{"type": "mystery", "text": "must not disappear"}]),
            response([{"type": "message", "id": "msg_bad", "role": "assistant", "content": [{"type": "mystery", "text": "lost"}]}]),
            response([function(arguments={})]),
            response(status="incomplete", incomplete_details={"reason": "unknown"}),
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ResponsesProtocolError):
                translate_response(data)


class ResponsesStreamTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, events, **kwargs):
        return [part async for part in translate_stream(lines_of(events, **kwargs))]

    async def test_sse_multiline_data_unicode_and_final_usage(self):
        initial = response([], status="in_progress")
        events = [
            {"type": "response.created", "response": initial},
            {"type": "response.output_item.added", "output_index": 0, "item": {**message(""), "status": "in_progress"}},
            {"type": "response.content_part.added", "item_id": "msg_1", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "你"},
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "好"},
            {"type": "response.output_text.done", "item_id": "msg_1", "output_index": 0, "content_index": 0, "text": "你好"},
            {"type": "response.output_item.done", "output_index": 0, "item": message()},
            {"type": "response.completed", "response": response()},
        ]
        wire = await self.collect(events, multiline=True)
        self.assertTrue(all(isinstance(part, bytes) for part in wire))
        chunks = chat_chunks(wire)
        text = "".join(choice["delta"].get("content", "") for chunk in chunks for choice in chunk.get("choices", []))
        self.assertEqual(text, "你好")
        self.assertTrue(all(chunk["object"] == "chat.completion.chunk" for chunk in chunks))
        self.assertTrue(any(choice["delta"].get("role") == "assistant" for chunk in chunks for choice in chunk.get("choices", [])))
        terminal = [choice["finish_reason"] for chunk in chunks for choice in chunk.get("choices", []) if choice.get("finish_reason")]
        self.assertEqual(terminal, ["stop"])
        usages = [chunk["usage"] for chunk in chunks if chunk.get("usage")]
        self.assertEqual(len(usages), 1)
        self.assertEqual(usages[0]["prompt_tokens"], 11)
        self.assertEqual(usages[0]["completion_tokens_details"]["reasoning_tokens"], 3)
        self.assertEqual(b"".join(wire).count(b"data: [DONE]"), 1)
        self.assertTrue(b"".join(wire).endswith(b"data: [DONE]\n\n"))

    async def test_parallel_function_deltas_and_terminal_snapshot_do_not_duplicate_arguments(self):
        call_a = function("call_a", item_id="fc_a", arguments='{"q":"a"}')
        call_b = function("call_b", item_id="fc_b", name="second", arguments='{"q":"b"}')
        events = [{"type": "response.created", "response": response([], status="in_progress")}]
        for index, call in enumerate((call_a, call_b)):
            events.append({"type": "response.output_item.added", "output_index": index, "item": {**call, "arguments": "", "status": "in_progress"}})
        for index, call in enumerate((call_a, call_b)):
            events.append({"type": "response.function_call_arguments.delta", "item_id": call["id"], "output_index": index, "delta": '{"q":'})
        for index, call in enumerate((call_a, call_b)):
            events.append({"type": "response.function_call_arguments.delta", "item_id": call["id"], "output_index": index, "delta": '"a"}' if index == 0 else '"b"}'})
            events.append({"type": "response.function_call_arguments.done", "item_id": call["id"], "output_index": index, "arguments": call["arguments"]})
            events.append({"type": "response.output_item.done", "output_index": index, "item": call})
        events.append({"type": "response.completed", "response": response([call_a, call_b])})
        wire = await self.collect(events)
        calls = {}
        for chunk in chat_chunks(wire):
            for choice in chunk.get("choices", []):
                for delta in choice["delta"].get("tool_calls", []):
                    call = calls.setdefault(delta["index"], {"arguments": "", "name": ""})
                    if delta.get("id"):
                        call["id"] = delta["id"]
                    call["name"] += delta.get("function", {}).get("name", "")
                    call["arguments"] += delta.get("function", {}).get("arguments", "")
        self.assertEqual(calls, {
            0: {"id": "call_a", "name": "lookup", "arguments": '{"q":"a"}'},
            1: {"id": "call_b", "name": "second", "arguments": '{"q":"b"}'},
        })
        endings = [choice.get("finish_reason") for chunk in chat_chunks(wire) for choice in chunk.get("choices", []) if choice.get("finish_reason")]
        self.assertEqual(endings, ["tool_calls"])

    async def test_terminal_snapshot_recovers_missing_deltas_once(self):
        events = [
            {"type": "response.created", "response": response([], status="in_progress")},
            {"type": "response.output_item.added", "output_index": 0, "item": {**message(""), "status": "in_progress"}},
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "你"},
            {"type": "response.completed", "response": response([message("你好世界")])},
        ]
        wire = await self.collect(events)
        text = "".join(choice["delta"].get("content", "") for chunk in chat_chunks(wire) for choice in chunk.get("choices", []))
        self.assertEqual(text, "你好世界")

    async def test_tool_indices_are_compact_when_reasoning_and_messages_precede_functions(self):
        reasoning = {"type": "reasoning", "id": "rs_1", "summary": []}
        call = function("call_after_text", item_id="fc_after_text", arguments='{"q":"ok"}')
        wire = await self.collect([
            {"type": "response.created", "response": response([], status="in_progress")},
            {"type": "response.output_item.added", "output_index": 0, "item": reasoning},
            {"type": "response.output_item.added", "output_index": 1, "item": {**message(""), "content": [], "status": "in_progress"}},
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 1, "content_index": 0, "delta": "先查询"},
            {"type": "response.output_item.added", "output_index": 2, "item": {**call, "arguments": "", "status": "in_progress"}},
            {"type": "response.function_call_arguments.delta", "item_id": call["id"], "output_index": 2, "delta": call["arguments"]},
            {"type": "response.completed", "response": response([reasoning, message("先查询"), call])},
        ])
        deltas = [delta for chunk in chat_chunks(wire) for choice in chunk.get("choices", []) for delta in choice["delta"].get("tool_calls", [])]
        self.assertTrue(deltas)
        self.assertTrue(all(delta["index"] == 0 for delta in deltas))
        self.assertEqual("".join(delta.get("function", {}).get("arguments", "") for delta in deltas), call["arguments"])
        self.assertEqual([delta["id"] for delta in deltas if "id" in delta], ["call_after_text"])

    async def test_snapshot_disagreement_is_an_error_without_a_success_terminal(self):
        prefix = {"type": "response.created", "response": response([], status="in_progress")}
        cases = [
            [prefix,
             {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "already emitted"},
             {"type": "response.completed", "response": response([message("different final output")])}],
            [prefix,
             {"type": "response.output_item.added", "output_index": 0, "item": function(arguments="")},
             {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "output_index": 0, "delta": '{"q":'},
             {"type": "response.completed", "response": response([function(arguments='{"other":1}')])}],
            [prefix,
             {"type": "response.output_item.added", "output_index": 0, "item": {**message(""), "status": "in_progress"}},
             {"type": "response.refusal.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "changed content kind"}],
        ]
        for events in cases:
            wire = []
            with self.subTest(events=events):
                with self.assertRaises(ResponsesProtocolError):
                    async for part in translate_stream(lines_of(events)):
                        wire.append(part)
                self.assertNotIn(b"[DONE]", b"".join(wire))
                self.assertFalse(any(choice.get("finish_reason") for chunk in chat_chunks(wire) for choice in chunk.get("choices", [])))

    async def test_late_snapshot_cannot_insert_earlier_message_or_part_before_emitted_text(self):
        prefix = {"type": "response.created", "response": response([], status="in_progress")}
        empty = {**message(""), "content": [], "status": "in_progress"}
        final_parts = message("A")
        final_parts["content"].append({"type": "output_text", "text": "B", "annotations": []})
        cases = [
            [prefix,
             {"type": "response.output_item.added", "output_index": 0, "item": empty},
             {"type": "response.output_item.added", "output_index": 1, "item": {**empty, "id": "msg_2"}},
             {"type": "response.output_text.delta", "item_id": "msg_2", "output_index": 1, "content_index": 0, "delta": "B"},
             {"type": "response.completed", "response": response([message("A"), message("B", item_id="msg_2")])}],
            [prefix,
             {"type": "response.output_item.added", "output_index": 0, "item": empty},
             {"type": "response.content_part.added", "item_id": "msg_1", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
             {"type": "response.content_part.added", "item_id": "msg_1", "output_index": 0, "content_index": 1, "part": {"type": "output_text", "text": "", "annotations": []}},
             {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 1, "delta": "B"},
             {"type": "response.completed", "response": response([final_parts])}],
        ]
        for events in cases:
            wire = []
            with self.subTest(events=events):
                with self.assertRaises(ResponsesProtocolError):
                    async for part in translate_stream(lines_of(events)):
                        wire.append(part)
                self.assertNotIn(b"[DONE]", b"".join(wire))
                self.assertFalse(any(choice.get("finish_reason") for chunk in chat_chunks(wire) for choice in chunk.get("choices", [])))

    async def test_stream_citation_offsets_remain_global_even_when_annotations_arrive_late(self):
        first = message("one")
        first["content"][0]["annotations"] = [citation(0, 3, "https://example.invalid/one")]
        first["content"].append({"type": "output_text", "text": "two", "annotations": [citation(0, 3, "https://example.invalid/two")]})
        second = message("XYZ", item_id="msg_2")
        second["content"][0]["annotations"] = [citation(1, 3, "https://example.invalid/yz")]
        events = [
            {"type": "response.created", "response": response([], status="in_progress")},
            {"type": "response.output_item.added", "output_index": 0, "item": {**message(""), "content": [], "status": "in_progress"}},
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "one"},
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 1, "delta": "two"},
            {"type": "response.output_text.annotation.added", "item_id": "msg_1", "output_index": 0, "content_index": 1, "annotation_index": 0, "annotation": citation(0, 3, "https://example.invalid/two")},
            {"type": "response.output_text.annotation.added", "item_id": "msg_1", "output_index": 0, "content_index": 0, "annotation_index": 0, "annotation": citation(0, 3, "https://example.invalid/one")},
            {"type": "response.output_item.added", "output_index": 1, "item": {**message("", item_id="msg_2"), "content": [], "status": "in_progress"}},
            {"type": "response.output_text.delta", "item_id": "msg_2", "output_index": 1, "content_index": 0, "delta": "XYZ"},
            {"type": "response.output_text.annotation.added", "item_id": "msg_2", "output_index": 1, "content_index": 0, "annotation_index": 0, "annotation": citation(1, 3, "https://example.invalid/yz")},
            {"type": "response.completed", "response": response([first, second])},
        ]
        wire = await self.collect(events)
        chunks = chat_chunks(wire)
        self.assertEqual("".join(choice["delta"].get("content", "") for chunk in chunks for choice in chunk.get("choices", [])), "onetwoXYZ")
        annotations = [a["url_citation"] for chunk in chunks for choice in chunk.get("choices", []) for a in choice["delta"].get("annotations", [])]
        self.assertEqual(len(annotations), 3)
        offsets = {a["url"]: (a["start_index"], a["end_index"]) for a in annotations}
        self.assertEqual(offsets, {
            "https://example.invalid/one": (0, 3),
            "https://example.invalid/two": (3, 6),
            "https://example.invalid/yz": (7, 9),
        })

    async def test_refusal_delta_and_incomplete_terminal_keep_semantics(self):
        refused = message()
        refused["content"] = [{"type": "refusal", "refusal": "无法协助"}]
        wire = await self.collect([
            {"type": "response.created", "response": response([], status="in_progress")},
            {"type": "response.output_item.added", "output_index": 0, "item": {**message(""), "content": [], "status": "in_progress"}},
            {"type": "response.refusal.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "无法"},
            {"type": "response.incomplete", "response": response([refused], status="incomplete", incomplete_details={"reason": "max_output_tokens"})},
        ])
        chunks = chat_chunks(wire)
        refusal = "".join(choice["delta"].get("refusal", "") for chunk in chunks for choice in chunk.get("choices", []))
        self.assertEqual(refusal, "无法协助")
        self.assertEqual([choice["finish_reason"] for chunk in chunks for choice in chunk.get("choices", []) if choice.get("finish_reason")], ["length"])

    async def test_failure_and_early_eof_never_emit_success_finish_or_done(self):
        cases = [
            [],
            [{"type": "response.created", "response": response([], status="in_progress")}],
            [{"type": "error", "code": "server_error", "message": "failed"}],
            [{"type": "response.failed", "response": response(status="failed")}],
        ]
        for events in cases:
            wire = []
            with self.subTest(events=events):
                with self.assertRaises(ResponsesProtocolError):
                    async for part in translate_stream(lines_of(events)):
                        wire.append(part)
                self.assertNotIn(b"[DONE]", b"".join(wire))
                self.assertFalse(any(choice.get("finish_reason") for chunk in chat_chunks(wire) for choice in chunk.get("choices", [])))

    async def test_malformed_json_is_a_protocol_error(self):
        async def broken_lines():
            for line in ("event: response.completed", "data: {not json}", ""):
                yield line
        with self.assertRaises(ResponsesProtocolError):
            _ = [part async for part in translate_stream(broken_lines())]


if __name__ == "__main__":
    unittest.main()
