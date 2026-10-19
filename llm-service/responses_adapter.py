"""Translate the supported Chat Completions contract to a stateless Responses call.

Unsupported request features are rejected before contacting the provider. Protocol
errors intentionally contain no provider payload, tool arguments, or prompt text.
The streaming adapter requires a terminal Responses event before emitting DONE.
"""
from __future__ import annotations

import copy
import json
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


class ResponsesRequestError(ValueError):
    """A Chat request cannot be represented without changing its meaning."""


class ResponsesProtocolError(RuntimeError):
    """The provider returned an invalid or unsupported Responses response."""


_PROXY_ITEM_METADATA = {"metadata", "internal_chat_message_metadata_passthrough"}


def _sanitize_output_item(item: Any) -> None:
    if isinstance(item, dict):
        for name in _PROXY_ITEM_METADATA:
            item.pop(name, None)


def _sanitize_response_output(data: dict) -> None:
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            _sanitize_output_item(item)


def sanitize_response(data: dict) -> dict:
    """Copy a native response and remove only known proxy item metadata.

    Response-level metadata and all standard/unknown semantic fields survive.
    Protocol validation remains separate; this does not repair invalid output.
    """
    if not isinstance(data, dict):
        raise ResponsesProtocolError("invalid Responses response")
    result = copy.deepcopy(data)
    _sanitize_response_output(result)
    return result


def sanitize_event(event: dict) -> dict | None:
    """Copy a public SSE event; omit the proxy's metadata-only control event."""
    if not isinstance(event, dict):
        raise ResponsesProtocolError("invalid Responses event")
    if event.get("type") == "response.metadata":
        return None
    result = copy.deepcopy(event)
    if result.get("type") in ("response.output_item.added", "response.output_item.done"):
        _sanitize_output_item(result.get("item"))
    if isinstance(result.get("response"), dict):
        _sanitize_response_output(result["response"])
    return result


def _request_object(value: Any, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ResponsesRequestError(f"unsupported {label} structure")
    return value


def _string(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise ResponsesRequestError(f"invalid {label}")
    return value


def _content(value: Any, role: str) -> list[dict]:
    if isinstance(value, str):
        parts = [{"type": "text", "text": value}]
    elif isinstance(value, list) and value:
        parts = value
    else:
        raise ResponsesRequestError("unsupported message content")
    result = []
    for part in parts:
        if not isinstance(part, dict):
            raise ResponsesRequestError("unsupported message content part")
        if part.get("type") == "text":
            _request_object(part, {"type", "text"}, "text content")
            text = _string(part.get("text"), "message text", empty=True)
            # Assistant text is flattened to EasyInputMessage's string form
            # below: some providers reject its otherwise typed input_text list.
            result.append({"type": "input_text", "text": text})
        elif part.get("type") == "image_url" and role == "user":
            _request_object(part, {"type", "image_url"}, "image content")
            image = _request_object(part.get("image_url"), {"url", "detail"}, "image URL")
            item = {"type": "input_image", "image_url": _string(image.get("url"), "image URL")}
            if "detail" in image:
                if image["detail"] not in ("auto", "low", "high"):
                    raise ResponsesRequestError("unsupported image detail")
                item["detail"] = image["detail"]
            result.append(item)
        else:
            raise ResponsesRequestError("unsupported message content type")
    return result


def _messages(messages: Any) -> list[dict]:
    # Configuration validation also uses an empty history to validate defaults.
    # The public ChatRequest independently requires at least one message.
    if not isinstance(messages, list):
        raise ResponsesRequestError("messages must be a list")
    result = []
    call_ids: set[str] = set()
    for message in messages:
        if not isinstance(message, dict):
            raise ResponsesRequestError("invalid message")
        role = message.get("role")
        if role in ("user", "system", "developer"):
            _request_object(message, {"role", "content"}, "message")
            result.append({"type": "message", "role": role, "content": _content(message.get("content"), role)})
        elif role == "assistant":
            _request_object(message, {"role", "content", "tool_calls", "refusal"}, "assistant message")
            content = [] if message.get("content") is None else _content(message["content"], role)
            if message.get("refusal") is not None:
                raise ResponsesRequestError("Responses cannot represent Chat refusal history without output item metadata")
            if content:
                result.append({"type": "message", "role": role,
                               "content": "".join(part["text"] for part in content)})
            calls = message.get("tool_calls")
            if calls is not None:
                if not isinstance(calls, list) or not calls:
                    raise ResponsesRequestError("invalid assistant tool calls")
                for call in calls:
                    _request_object(call, {"id", "type", "function"}, "tool call")
                    if call.get("type") != "function":
                        raise ResponsesRequestError("unsupported tool call type")
                    function = _request_object(call.get("function"), {"name", "arguments"}, "function call")
                    call_id = _string(call.get("id"), "tool call ID")
                    if call_id in call_ids:
                        raise ResponsesRequestError("duplicate tool call ID")
                    call_ids.add(call_id)
                    result.append({"type": "function_call", "call_id": call_id,
                                   "name": _string(function.get("name"), "function name"),
                                   "arguments": _string(function.get("arguments"), "function arguments", empty=True)})
            if not content and not calls:
                raise ResponsesRequestError("assistant message has no supported content")
        elif role == "tool":
            _request_object(message, {"role", "content", "tool_call_id"}, "tool message")
            output = message.get("content")
            if not isinstance(output, str):
                # Responses supports content arrays for function output as well.
                output = _content(output, "tool")
            result.append({"type": "function_call_output",
                           "call_id": _string(message.get("tool_call_id"), "tool call ID"), "output": output})
        else:
            raise ResponsesRequestError("unsupported message role")
    return result


def _tools(value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise ResponsesRequestError("invalid tools")
    result = []
    for tool in value:
        _request_object(tool, {"type", "function"}, "tool")
        if tool.get("type") != "function":
            raise ResponsesRequestError("unsupported tool type")
        function = _request_object(tool.get("function"), {"name", "description", "parameters", "strict"}, "function tool")
        strict = function.get("strict")
        if strict is not None and not isinstance(strict, bool):
            raise ResponsesRequestError("invalid function strict setting")
        item = {"type": "function", "name": _string(function.get("name"), "function name"),
                "strict": strict if strict is not None else False,
                "parameters": None}
        for key in ("description", "parameters"):
            if key in function and function[key] is not None:
                if key == "description":
                    _string(function[key], "function description", empty=True)
                elif not isinstance(function[key], dict):
                    raise ResponsesRequestError("invalid function parameters")
                item[key] = copy.deepcopy(function[key])
        result.append(item)
    return result


def _tool_choice(value: Any) -> str | dict:
    if isinstance(value, str):
        if value not in ("none", "auto", "required"):
            raise ResponsesRequestError("unsupported tool choice")
        return value
    _request_object(value, {"type", "function"}, "tool choice")
    if value.get("type") != "function":
        raise ResponsesRequestError("unsupported tool choice type")
    function = _request_object(value.get("function"), {"name"}, "tool choice function")
    return {"type": "function", "name": _string(function.get("name"), "tool choice name")}


def _format(value: Any) -> dict:
    _request_object(value, {"type", "json_schema"}, "response format")
    kind = value.get("type")
    if kind in ("text", "json_object") and set(value) == {"type"}:
        return {"type": kind}
    if kind != "json_schema":
        raise ResponsesRequestError("unsupported response format")
    schema = _request_object(value.get("json_schema"), {"name", "schema", "description", "strict"}, "JSON schema format")
    _string(schema.get("name"), "JSON schema name")
    if not isinstance(schema.get("schema"), dict):
        raise ResponsesRequestError("invalid response JSON schema")
    if "description" in schema:
        _string(schema["description"], "JSON schema description", empty=True)
    if schema.get("strict") is not None and not isinstance(schema["strict"], bool):
        raise ResponsesRequestError("invalid response JSON schema strict setting")
    return {"type": "json_schema", **copy.deepcopy(schema)}


def build_request(model: str, messages: list, params: dict, *, stream: bool = False) -> dict:
    """Build a Responses request, rejecting Chat features without an equivalent."""
    _string(model, "model")
    _request_object(params, {"temperature", "top_p", "max_tokens", "tools", "tool_choice", "response_format", "n",
                             "stop", "presence_penalty", "frequency_penalty", "seed"}, "generation parameters")
    if not isinstance(stream, bool):
        raise ResponsesRequestError("invalid stream setting")
    body = {"model": model, "input": _messages(messages), "store": False, "stream": stream}
    for key, value in params.items():
        if value is None:
            continue
        if key in ("stop", "presence_penalty", "frequency_penalty", "seed"):
            raise ResponsesRequestError(f"Responses does not support {key}")
        if key == "n":
            if type(value) is not int or value != 1:
                raise ResponsesRequestError("Responses supports only n=1")
        elif key in ("temperature", "top_p"):
            upper = 2 if key == "temperature" else 1
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper:
                raise ResponsesRequestError(f"invalid {key}")
            body[key] = value
        elif key == "max_tokens":
            if type(value) is not int or value < 1:
                raise ResponsesRequestError("invalid max_tokens")
            body["max_output_tokens"] = value
        elif key == "tools":
            body["tools"] = _tools(value)
        elif key == "tool_choice":
            body["tool_choice"] = _tool_choice(value)
        elif key == "response_format":
            body["text"] = {"format": _format(value)}
    return body


def _protocol_string(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise ResponsesProtocolError(f"invalid Responses {label}")
    return value


def _identity(data: Any) -> dict:
    if not isinstance(data, dict) or data.get("object", "response") != "response":
        raise ResponsesProtocolError("invalid Responses object")
    created = data.get("created_at")
    if type(created) is not int or created < 0:
        raise ResponsesProtocolError("invalid Responses creation timestamp")
    return {"id": _protocol_string(data.get("id"), "response ID"), "created": created,
            "model": _protocol_string(data.get("model"), "model")}


def _usage(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ResponsesProtocolError("invalid Responses usage")
    result = {}
    for source, target in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"), ("total_tokens", "total_tokens")):
        count = value.get(source)
        if type(count) is not int or count < 0:
            raise ResponsesProtocolError("invalid Responses token count")
        result[target] = count
    for source, target in (("input_tokens_details", "prompt_tokens_details"), ("output_tokens_details", "completion_tokens_details")):
        details = value.get(source)
        if details is not None:
            if not isinstance(details, dict) or any(type(count) is not int or count < 0 for count in details.values()):
                raise ResponsesProtocolError("invalid Responses token details")
            result[target] = copy.deepcopy(details)
    return result


def _annotation(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("type") != "url_citation":
        raise ResponsesProtocolError("unsupported Responses annotation")
    citation = {}
    for key in ("start_index", "end_index"):
        if type(value.get(key)) is not int or value[key] < 0:
            raise ResponsesProtocolError("invalid Responses citation offsets")
        citation[key] = value[key]
    for key in ("url", "title"):
        citation[key] = _protocol_string(value.get(key), "citation", empty=key == "title")
    return {"type": "url_citation", "url_citation": citation}


def _part(part: Any) -> tuple[str, str, list]:
    if not isinstance(part, dict):
        raise ResponsesProtocolError("invalid Responses content part")
    if part.get("type") == "output_text":
        annotations = part.get("annotations", [])
        if not isinstance(annotations, list):
            raise ResponsesProtocolError("invalid Responses annotations")
        return "content", _protocol_string(part.get("text"), "output text", empty=True), [_annotation(a) for a in annotations]
    if part.get("type") == "refusal":
        return "refusal", _protocol_string(part.get("refusal"), "refusal", empty=True), []
    raise ResponsesProtocolError("unsupported Responses content type")


def _offset_annotations(annotations: list, offset: int) -> list:
    """Responses citation offsets are local to a part; Chat content is joined."""
    result = []
    for annotation in annotations:
        citation = dict(annotation["url_citation"])
        citation["start_index"] += offset
        citation["end_index"] += offset
        result.append({"type": "url_citation", "url_citation": citation})
    return result


def _finish(data: dict, has_calls: bool) -> str:
    if data.get("error") is not None:
        raise ResponsesProtocolError("Responses provider reported a failure")
    status = data.get("status")
    if status == "completed":
        return "tool_calls" if has_calls else "stop"
    if status == "incomplete":
        details = data.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        if reason == "max_output_tokens":
            return "length"
        if reason == "content_filter":
            return "content_filter"
        raise ResponsesProtocolError("unsupported Responses incomplete reason")
    raise ResponsesProtocolError("Responses response did not finish successfully")


def translate_response(data: Any) -> dict:
    """Convert a terminal Responses object to a single Chat choice."""
    identity = _identity(data)
    output = data.get("output")
    if not isinstance(output, list):
        raise ResponsesProtocolError("invalid Responses output")
    texts, refusals, calls, annotations = [], [], [], []
    text_length = 0
    call_ids = set()
    for item in output:
        if not isinstance(item, dict):
            raise ResponsesProtocolError("invalid Responses output item")
        kind = item.get("type")
        if kind == "message":
            if item.get("role") != "assistant" or not isinstance(item.get("content"), list):
                raise ResponsesProtocolError("invalid Responses output message")
            for part in item["content"]:
                field_name, text, citations = _part(part)
                (texts if field_name == "content" else refusals).append(text)
                annotations.extend(_offset_annotations(citations, text_length))
                if field_name == "content":
                    text_length += len(text)
        elif kind == "function_call":
            call_id = _protocol_string(item.get("call_id"), "function call ID")
            if call_id in call_ids:
                raise ResponsesProtocolError("duplicate Responses function call ID")
            call_ids.add(call_id)
            calls.append({"id": call_id, "type": "function", "function": {
                "name": _protocol_string(item.get("name"), "function name"),
                "arguments": _protocol_string(item.get("arguments"), "function arguments", empty=True)}})
        elif kind != "reasoning":
            raise ResponsesProtocolError("unsupported Responses output type")
    message: dict = {"role": "assistant", "content": "".join(texts) if texts else None}
    if refusals:
        message["refusal"] = "".join(refusals)
    if calls:
        message["tool_calls"] = calls
    if annotations:
        message["annotations"] = annotations
    result = {**identity, "object": "chat.completion", "choices": [
        {"index": 0, "message": message, "finish_reason": _finish(data, bool(calls))}]}
    usage = _usage(data.get("usage"))
    if usage is not None:
        result["usage"] = usage
    return result


@dataclass
class _PartState:
    kind: str
    position: tuple[int, int]
    text: str = ""
    annotations: list = field(default_factory=list)
    content_offset: int | None = None


@dataclass
class _ItemState:
    kind: str
    output_index: int
    item_id: str | None = None
    parts: dict[int, _PartState] = field(default_factory=dict)
    call_id: str | None = None
    name: str | None = None
    arguments: str = ""
    sent_arguments: str = ""
    tool_index: int | None = None


class _Stream:
    def __init__(self):
        self.identity: dict | None = None
        self.started = False
        self.items: dict[int, _ItemState] = {}
        self.item_ids: dict[str, int] = {}
        self.tool_indices: list[int] = []
        self.last_text_position: dict[str, tuple[int, int]] = {}
        self.content_length = 0

    def header(self, response: Any) -> None:
        identity = _identity(response)
        if self.identity is not None and self.identity != identity:
            raise ResponsesProtocolError("Responses stream identity changed")
        self.identity = identity

    def chunk(self, delta: dict | None = None, *, finish: str | None = None, usage: dict | None = None) -> bytes:
        if self.identity is None:
            raise ResponsesProtocolError("Responses stream has no response identity")
        chunk = {**self.identity, "object": "chat.completion.chunk", "choices": [] if usage is not None else [
            {"index": 0, "delta": delta or {}, "finish_reason": finish}]}
        if usage is not None:
            chunk["usage"] = usage
        return ("data: " + json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8")

    def start(self) -> list[bytes]:
        if self.started:
            return []
        self.started = True
        return [self.chunk({"role": "assistant"})]

    def item(self, index: Any, kind: str, item_id: Any = None) -> _ItemState:
        if type(index) is not int or index < 0:
            raise ResponsesProtocolError("invalid Responses output index")
        state = self.items.setdefault(index, _ItemState(kind, index))
        if state.kind != kind:
            raise ResponsesProtocolError("Responses output item type changed")
        if item_id is not None:
            _protocol_string(item_id, "output item ID")
            if state.item_id is not None and state.item_id != item_id:
                raise ResponsesProtocolError("Responses output item ID changed")
            if item_id in self.item_ids and self.item_ids[item_id] != index:
                raise ResponsesProtocolError("duplicate Responses output item ID")
            self.item_ids[item_id] = index
            state.item_id = item_id
        return state

    def part(self, state: _ItemState, index: Any, kind: str) -> _PartState:
        if type(index) is not int or index < 0:
            raise ResponsesProtocolError("invalid Responses content index")
        part = state.parts.setdefault(index, _PartState(kind, (state.output_index, index)))
        if part.kind != kind:
            raise ResponsesProtocolError("Responses content type changed")
        return part

    def text(self, event: dict, kind: str, *, done: bool = False) -> list[bytes]:
        state = self.item(event.get("output_index"), "message", event.get("item_id"))
        part = self.part(state, event.get("content_index"), kind)
        text = _protocol_string(event.get(("text" if kind == "content" else "refusal") if done else "delta"),
                                "text delta", empty=True)
        if done:
            return self.fill_part(part, text)
        part.text += text
        return self.emit_part(part, text)

    def position(self, part: _PartState) -> None:
        last = self.last_text_position.get(part.kind)
        if last is not None and part.position < last:
            raise ResponsesProtocolError("Responses text arrived out of output order")
        self.last_text_position[part.kind] = part.position
        if part.kind == "content" and part.content_offset is None:
            part.content_offset = self.content_length

    def emit_part(self, part: _PartState, text: str) -> list[bytes]:
        if not text:
            return []
        self.position(part)
        if part.kind == "content":
            self.content_length += len(text)
        return [self.chunk({part.kind: text})]

    def emit_annotations(self, part: _PartState, annotations: list) -> list[bytes]:
        if not annotations:
            return []
        if part.content_offset is None:
            # An annotation may arrive before its text. Reserve that position so
            # later text cannot silently insert a prefix and invalidate offsets.
            self.position(part)
        return [self.chunk({"annotations": _offset_annotations(annotations, part.content_offset)})]

    def fill_part(self, part: _PartState, full: str) -> list[bytes]:
        if not full.startswith(part.text):
            raise ResponsesProtocolError("Responses text snapshot disagrees with its deltas")
        missing = full[len(part.text):]
        part.text = full
        return self.emit_part(part, missing)

    def fill_annotations(self, part: _PartState, annotations: list) -> list[bytes]:
        if annotations[:len(part.annotations)] != part.annotations:
            raise ResponsesProtocolError("Responses annotation snapshot changed")
        missing = annotations[len(part.annotations):]
        part.annotations = annotations
        return self.emit_annotations(part, missing)

    def call_chunks(self, output_index: int, state: _ItemState) -> list[bytes]:
        if state.call_id is None or state.name is None:
            return []  # A later item snapshot must supply the function identity.
        result = []
        if state.tool_index is None:
            if self.tool_indices and self.tool_indices[-1] > output_index:
                raise ResponsesProtocolError("Responses function call order changed")
            if any(item.call_id == state.call_id and item is not state for item in self.items.values()):
                raise ResponsesProtocolError("duplicate Responses function call ID")
            state.tool_index = len(self.tool_indices)
            self.tool_indices.append(output_index)
            result.append(self.chunk({"tool_calls": [{"index": state.tool_index, "id": state.call_id,
                                                       "type": "function", "function": {"name": state.name, "arguments": ""}}]}))
        if not state.arguments.startswith(state.sent_arguments):
            raise ResponsesProtocolError("Responses function argument snapshot changed")
        missing = state.arguments[len(state.sent_arguments):]
        if missing:
            result.append(self.chunk({"tool_calls": [{"index": state.tool_index, "function": {"arguments": missing}}]}))
            state.sent_arguments = state.arguments
        return result

    def snapshot(self, output_index: Any, value: Any, *, complete: bool) -> list[bytes]:
        if not isinstance(value, dict):
            raise ResponsesProtocolError("invalid Responses output item snapshot")
        kind = value.get("type")
        if kind == "reasoning":
            self.item(output_index, kind, value.get("id"))
            return []
        if kind not in ("message", "function_call"):
            raise ResponsesProtocolError("unsupported Responses output type")
        state = self.item(output_index, kind, value.get("id"))
        if kind == "function_call":
            call_id = _protocol_string(value.get("call_id"), "function call ID")
            name = _protocol_string(value.get("name"), "function name")
            if (state.call_id is not None and state.call_id != call_id) or (state.name is not None and state.name != name):
                raise ResponsesProtocolError("Responses function identity changed")
            state.call_id, state.name = call_id, name
            arguments = _protocol_string(value.get("arguments"), "function arguments", empty=True)
            # output_item.added normally has empty arguments; it must not reset
            # already received deltas if a provider sends metadata late.
            if complete or arguments:
                if not arguments.startswith(state.arguments):
                    raise ResponsesProtocolError("Responses function argument snapshot disagrees with its deltas")
                state.arguments = arguments
            return self.call_chunks(output_index, state)
        if value.get("role") != "assistant" or not isinstance(value.get("content"), list):
            raise ResponsesProtocolError("invalid Responses output message")
        result = []
        for index, value_part in enumerate(value["content"]):
            part_kind, text, annotations = _part(value_part)
            part = self.part(state, index, part_kind)
            if complete or text:
                result.extend(self.fill_part(part, text))
            result.extend(self.fill_annotations(part, annotations))
        if complete and any(index >= len(value["content"]) for index in state.parts):
            raise ResponsesProtocolError("Responses message snapshot lost a content part")
        return result

    def content_snapshot(self, event: dict) -> list[bytes]:
        state = self.item(event.get("output_index"), "message", event.get("item_id"))
        kind, text, annotations = _part(event.get("part"))
        part = self.part(state, event.get("content_index"), kind)
        result = self.fill_part(part, text) if event["type"].endswith(".done") or text else []
        result.extend(self.fill_annotations(part, annotations))
        return result

    def arguments(self, event: dict, *, done: bool) -> list[bytes]:
        index = event.get("output_index")
        state = self.item(index, "function_call", event.get("item_id"))
        text = _protocol_string(event.get("arguments" if done else "delta"), "function argument delta", empty=True)
        if done:
            if not text.startswith(state.arguments):
                raise ResponsesProtocolError("Responses function arguments disagree with their deltas")
            state.arguments = text
        else:
            state.arguments += text
        return self.call_chunks(index, state)

    def terminal(self, event: dict) -> list[bytes]:
        response = event.get("response")
        self.header(response)
        expected = "completed" if event["type"] == "response.completed" else "incomplete"
        if response.get("status") != expected:
            raise ResponsesProtocolError("Responses terminal event status mismatch")
        translated = translate_response(response)  # Validate before emitting a success finish.
        output = response["output"]
        if any(index >= len(output) for index in self.items):
            raise ResponsesProtocolError("Responses terminal snapshot lost an output item")
        result = self.start()
        for index, item in enumerate(output):
            result.extend(self.snapshot(index, item, complete=True))
        result.append(self.chunk(finish=translated["choices"][0]["finish_reason"]))
        if "usage" in translated:
            result.append(self.chunk(usage=translated["usage"]))
        result.append(b"data: [DONE]\n\n")
        return result


async def _events(lines: AsyncIterator[str]) -> AsyncIterator[dict]:
    data: list[str] = []
    event_name: str | None = None

    def parse() -> dict:
        try:
            value = json.loads("\n".join(data))
        except (ValueError, TypeError) as error:
            raise ResponsesProtocolError("invalid Responses SSE JSON") from error
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ResponsesProtocolError("invalid Responses SSE event")
        if event_name and event_name != value["type"]:
            raise ResponsesProtocolError("Responses SSE event type mismatch")
        return value

    async for line in lines:
        if not isinstance(line, str):
            raise ResponsesProtocolError("invalid Responses SSE line")
        if line == "":
            if data:
                yield parse()
            data, event_name = [], None
            continue
        if line.startswith(":"):
            continue
        name, separator, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "data":
            data.append(value if separator else "")
        elif name == "event":
            event_name = value
        # SSE id/retry and unrecognized framing fields do not carry model data.
    if data:
        # A final event need not end with an extra empty line.
        yield parse()


_REASONING_EVENTS = {
    "response.reasoning_summary_part.added", "response.reasoning_summary_part.done",
    "response.reasoning_summary_text.delta", "response.reasoning_summary_text.done",
    "response.reasoning_text.delta", "response.reasoning_text.done",
}


async def translate_stream(lines: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Translate Responses SSE lines into Chat SSE, failing closed on truncation."""
    stream = _Stream()
    async for event in _events(lines):
        kind = event["type"]
        if kind == "response.metadata":
            continue  # Relay control metadata carries no assistant output.
        if kind in ("error", "response.failed", "response.cancelled"):
            raise ResponsesProtocolError("Responses stream reported a failure")
        if kind in ("response.completed", "response.incomplete"):
            for chunk in stream.terminal(event):
                yield chunk
            return
        if kind in ("response.created", "response.in_progress", "response.queued"):
            stream.header(event.get("response"))
            chunks = stream.start()
        else:
            if stream.identity is None:
                raise ResponsesProtocolError("Responses stream data preceded its identity")
            if kind in ("response.output_item.added", "response.output_item.done"):
                chunks = stream.snapshot(event.get("output_index"), event.get("item"), complete=kind.endswith(".done"))
            elif kind in ("response.output_text.delta", "response.output_text.done"):
                chunks = stream.text(event, "content", done=kind.endswith(".done"))
            elif kind in ("response.refusal.delta", "response.refusal.done"):
                chunks = stream.text(event, "refusal", done=kind.endswith(".done"))
            elif kind in ("response.function_call_arguments.delta", "response.function_call_arguments.done"):
                chunks = stream.arguments(event, done=kind.endswith(".done"))
            elif kind in ("response.content_part.added", "response.content_part.done"):
                chunks = stream.content_snapshot(event)
            elif kind == "response.output_text.annotation.added":
                state = stream.item(event.get("output_index"), "message", event.get("item_id"))
                part = stream.part(state, event.get("content_index"), "content")
                annotation_index = event.get("annotation_index")
                if type(annotation_index) is not int or annotation_index != len(part.annotations):
                    raise ResponsesProtocolError("invalid Responses annotation order")
                annotation = _annotation(event.get("annotation"))
                part.annotations.append(annotation)
                chunks = stream.emit_annotations(part, [annotation])
            elif kind in _REASONING_EVENTS:
                chunks = []  # Reasoning is not assistant answer text.
            else:
                raise ResponsesProtocolError("unsupported Responses SSE event type")
        for chunk in chunks:
            yield chunk
    raise ResponsesProtocolError("Responses stream ended without a terminal event")
