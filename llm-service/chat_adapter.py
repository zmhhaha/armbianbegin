"""Stateless Responses contract over an upstream Chat Completions provider.

The public contract stays Responses even when the selected provider only speaks
Chat Completions. Unsupported features fail explicitly; provider reasoning never
becomes answer text. A Chat SSE stream needs both a finish reason and DONE before
the bridge emits a successful Responses terminal event.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from responses_adapter import ResponsesProtocolError, ResponsesRequestError


def _object(value: Any, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - fields:
        raise ResponsesRequestError(f"unsupported {label} structure")
    return value


def _text(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise ResponsesRequestError(f"invalid {label}")
    return value


def _history_content(value: Any, role: str) -> tuple[Any, str | None]:
    if isinstance(value, str):
        return value, None
    if not isinstance(value, list):
        raise ResponsesRequestError("unsupported Responses message content")
    parts, refusals = [], []
    for part in value:
        if not isinstance(part, dict):
            raise ResponsesRequestError("invalid Responses message content part")
        kind = part.get("type")
        if kind in ("input_text", "output_text"):
            _object(part, {"type", "text", "annotations", "logprobs"}, "text content")
            if kind == "output_text" and role != "assistant":
                raise ResponsesRequestError("output_text requires assistant history")
            if part.get("annotations") or part.get("logprobs"):
                raise ResponsesRequestError("Chat cannot preserve annotated output history")
            parts.append({"type": "text", "text": _text(part.get("text"), "message text", empty=True)})
        elif kind == "input_image" and role == "user":
            _object(part, {"type", "image_url", "detail", "file_id"}, "image content")
            if part.get("file_id") is not None:
                raise ResponsesRequestError("Chat cannot resolve Responses image file IDs")
            image = {"url": _text(part.get("image_url"), "image URL")}
            if part.get("detail") is not None:
                if part["detail"] not in ("auto", "low", "high"):
                    raise ResponsesRequestError("unsupported image detail")
                image["detail"] = part["detail"]
            parts.append({"type": "image_url", "image_url": image})
        elif kind == "refusal" and role == "assistant":
            _object(part, {"type", "refusal"}, "refusal content")
            refusals.append(_text(part.get("refusal"), "refusal", empty=True))
        else:
            raise ResponsesRequestError("unsupported Responses content type")
    if any(part["type"] == "image_url" for part in parts):
        content = parts
    else:
        content = "".join(part["text"] for part in parts) if parts else None
    return content, "".join(refusals) if refusals else None


def _history(value: Any) -> list[dict]:
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    if not isinstance(value, list):
        raise ResponsesRequestError("Responses input must be text or an item list")
    messages: list[dict] = []
    call_ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ResponsesRequestError("invalid Responses input item")
        kind = item.get("type", "message")
        if kind == "message":
            _object(item, {"type", "role", "content", "id", "status", "phase"}, "input message")
            role = item.get("role")
            if role not in ("system", "developer", "user", "assistant"):
                raise ResponsesRequestError("unsupported Responses message role")
            if item.get("id") is not None:
                _text(item["id"], "message item ID")
            if item.get("status") is not None and item["status"] not in ("completed", "incomplete"):
                raise ResponsesRequestError("input message is not a finished history item")
            if item.get("phase") not in (None, "commentary", "final_answer"):
                raise ResponsesRequestError("unsupported message phase")
            content, refusal = _history_content(item.get("content"), role)
            message = {"role": role, "content": content}
            if refusal is not None:
                message["refusal"] = refusal
            messages.append(message)
        elif kind == "function_call":
            _object(item, {"type", "id", "call_id", "name", "arguments", "status", "namespace"}, "function call")
            if item.get("namespace") not in (None, ""):
                raise ResponsesRequestError("Chat cannot preserve function namespaces")
            call_id = _text(item.get("call_id"), "function call ID")
            if call_id in call_ids:
                raise ResponsesRequestError("duplicate function call ID")
            call_ids.add(call_id)
            call = {"id": call_id, "type": "function", "function": {
                "name": _text(item.get("name"), "function name"),
                "arguments": _text(item.get("arguments"), "function arguments", empty=True)}}
            if not messages or messages[-1]["role"] != "assistant":
                messages.append({"role": "assistant", "content": None})
            messages[-1].setdefault("tool_calls", []).append(call)
        elif kind == "function_call_output":
            _object(item, {"type", "id", "call_id", "output", "status"}, "function output")
            output = item.get("output")
            if not isinstance(output, str):
                output, refusal = _history_content(output, "tool")
                if refusal is not None or not isinstance(output, str):
                    raise ResponsesRequestError("unsupported function output content")
            messages.append({"role": "tool", "tool_call_id": _text(item.get("call_id"), "function call ID"), "content": output})
        else:
            raise ResponsesRequestError("unsupported Responses input item type")
    return messages


def _tools(value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise ResponsesRequestError("invalid Responses tools")
    result = []
    for tool in value:
        _object(tool, {"type", "name", "description", "parameters", "strict"}, "function tool")
        if tool.get("type") != "function":
            raise ResponsesRequestError("Chat supports only function tools")
        strict = tool.get("strict")
        if strict is not None and not isinstance(strict, bool):
            raise ResponsesRequestError("invalid function strict setting")
        function = {"name": _text(tool.get("name"), "function name"),
                    "strict": True if strict is None else strict}
        if tool.get("description") is not None:
            function["description"] = _text(tool["description"], "function description", empty=True)
        if tool.get("parameters") is not None:
            if not isinstance(tool["parameters"], dict):
                raise ResponsesRequestError("invalid function schema")
            function["parameters"] = copy.deepcopy(tool["parameters"])
        result.append({"type": "function", "function": function})
    return result


def _format(value: Any) -> dict:
    _object(value, {"format"}, "text settings")
    formatting = _object(value.get("format"), {"type", "name", "schema", "strict", "description"}, "text format")
    kind = formatting.get("type")
    if kind in ("text", "json_object") and set(formatting) == {"type"}:
        return {"type": kind}
    if kind != "json_schema":
        raise ResponsesRequestError("unsupported Responses text format")
    _text(formatting.get("name"), "schema name")
    if not isinstance(formatting.get("schema"), dict):
        raise ResponsesRequestError("invalid output schema")
    if formatting.get("description") is not None:
        _text(formatting["description"], "schema description", empty=True)
    if formatting.get("strict") is not None and not isinstance(formatting["strict"], bool):
        raise ResponsesRequestError("invalid output schema strict setting")
    return {"type": "json_schema", "json_schema": {key: copy.deepcopy(item) for key, item in formatting.items() if key != "type"}}


def to_chat_request(body: dict) -> tuple[list, dict]:
    """Return messages and Chat generation params for the supported Responses API."""
    _object(body, {"model", "input", "instructions", "temperature", "top_p", "max_output_tokens",
                   "tools", "tool_choice", "text", "stream", "store"}, "Responses request")
    if "store" in body and body["store"] is not False:
        raise ResponsesRequestError("gateway Responses requests require store=false")
    if "stream" in body and not isinstance(body["stream"], bool):
        raise ResponsesRequestError("invalid stream setting")
    if "model" in body:
        _text(body["model"], "model")
    messages = _history(body.get("input", []))
    if body.get("instructions") is not None:
        messages.insert(0, {"role": "system", "content": _text(body["instructions"], "instructions", empty=True)})
    params = {}
    for key in ("temperature", "top_p"):
        value = body.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= (2 if key == "temperature" else 1):
                raise ResponsesRequestError(f"invalid {key}")
            params[key] = value
    if body.get("max_output_tokens") is not None:
        count = body["max_output_tokens"]
        if type(count) is not int or count < 1:
            raise ResponsesRequestError("invalid max_output_tokens")
        params["max_tokens"] = count
    if body.get("tools") is not None:
        params["tools"] = _tools(body["tools"])
    if body.get("tool_choice") is not None:
        choice = body["tool_choice"]
        if isinstance(choice, str):
            if choice not in ("none", "auto", "required"):
                raise ResponsesRequestError("unsupported tool choice")
            params["tool_choice"] = choice
        else:
            _object(choice, {"type", "name"}, "tool choice")
            if choice.get("type") != "function":
                raise ResponsesRequestError("unsupported tool choice type")
            params["tool_choice"] = {"type": "function", "function": {"name": _text(choice.get("name"), "tool choice name")}}
    if body.get("text") is not None:
        params["response_format"] = _format(body["text"])
    return messages, params


def _protocol_text(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise ResponsesProtocolError(f"invalid Chat {label}")
    return value


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ResponsesProtocolError(f"invalid Chat {label}")
    return value


def _usage(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ResponsesProtocolError("invalid Chat usage")
    prompt = _count(value.get("prompt_tokens"), "prompt token count")
    completion = _count(value.get("completion_tokens"), "completion token count")
    input_details = value.get("prompt_tokens_details") or {}
    output_details = value.get("completion_tokens_details") or {}
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise ResponsesProtocolError("invalid Chat token details")
    return {"input_tokens": prompt, "output_tokens": completion,
            "total_tokens": _count(value.get("total_tokens", prompt + completion), "total token count"),
            "input_tokens_details": {"cached_tokens": _count(input_details.get("cached_tokens", value.get("prompt_cache_hit_tokens", 0)), "cached token count")},
            "output_tokens_details": {"reasoning_tokens": _count(output_details.get("reasoning_tokens", 0), "reasoning token count")}}


def _identifier(source: Any, prefix: str) -> str:
    if isinstance(source, str) and source:
        suffix = hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]
    else:
        suffix = uuid.uuid4().hex
    return prefix + suffix


def _base(data: Any) -> dict:
    if not isinstance(data, dict) or data.get("error") is not None:
        raise ResponsesProtocolError("Chat provider returned an error or invalid object")
    created = data.get("created", int(time.time()))
    _count(created, "creation timestamp")
    return {"id": _identifier(data.get("id"), "resp_"), "object": "response", "created_at": created,
            "model": _protocol_text(data.get("model"), "model"), "status": "in_progress", "error": None,
            "incomplete_details": None, "instructions": None, "metadata": {}, "output": [], "store": False,
            "parallel_tool_calls": True, "temperature": None, "top_p": None, "tool_choice": "auto", "tools": [], "usage": None}


def _status(finish: Any) -> tuple[str, dict | None]:
    if finish in ("stop", "tool_calls"):
        return "completed", None
    if finish == "length":
        return "incomplete", {"reason": "max_output_tokens"}
    if finish == "content_filter":
        return "incomplete", {"reason": "content_filter"}
    raise ResponsesProtocolError("Chat response has no supported finish reason")


def _annotations(value: Any) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ResponsesProtocolError("invalid Chat annotations")
    result = []
    for annotation in value:
        if not isinstance(annotation, dict) or annotation.get("type") != "url_citation" or not isinstance(annotation.get("url_citation"), dict):
            raise ResponsesProtocolError("unsupported Chat annotation")
        citation = annotation["url_citation"]
        start, end = _count(citation.get("start_index"), "citation start"), _count(citation.get("end_index"), "citation end")
        if start > end:
            raise ResponsesProtocolError("invalid Chat citation range")
        result.append({"type": "url_citation", "start_index": start, "end_index": end,
                       "url": _protocol_text(citation.get("url"), "citation URL"),
                       "title": _protocol_text(citation.get("title"), "citation title", empty=True)})
    return result


def _message_content(message: Any) -> list:
    if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
        raise ResponsesProtocolError("invalid Chat assistant message")
    allowed = {"role", "content", "refusal", "tool_calls", "reasoning_content", "annotations", "audio", "function_call"}
    if set(message) - allowed or message.get("audio") is not None or message.get("function_call") is not None:
        raise ResponsesProtocolError("unsupported Chat assistant message field")
    result = []
    if message.get("content") is not None:
        result.append({"type": "output_text", "text": _protocol_text(message["content"], "answer text", empty=True),
                       "annotations": _annotations(message.get("annotations")), "logprobs": []})
    elif message.get("annotations"):
        raise ResponsesProtocolError("Chat annotations have no answer text")
    if message.get("refusal") is not None:
        result.append({"type": "refusal", "refusal": _protocol_text(message["refusal"], "refusal", empty=True)})
    return result


def _function(call: Any, response_id: str, index: int, status: str) -> dict:
    if not isinstance(call, dict) or call.get("type") != "function" or not isinstance(call.get("function"), dict):
        raise ResponsesProtocolError("invalid Chat function call")
    function = call["function"]
    if set(call) - {"id", "type", "function"} or set(function) - {"name", "arguments"}:
        raise ResponsesProtocolError("unsupported Chat function call field")
    return {"type": "function_call", "id": _identifier(response_id + ":tool:" + str(index), "fc_"),
            "call_id": _protocol_text(call.get("id"), "function call ID"),
            "name": _protocol_text(function.get("name"), "function name"),
            "arguments": _protocol_text(function.get("arguments"), "function arguments", empty=True), "status": status}


def from_chat_response(data: dict) -> dict:
    """Convert a single Chat choice to a complete/incomplete Responses object."""
    response = _base(data)
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ResponsesProtocolError("Chat response must contain one choice")
    choice = choices[0]
    if choice.get("index", 0) != 0:
        raise ResponsesProtocolError("unsupported Chat choice index")
    status, details = _status(choice.get("finish_reason"))
    message = choice.get("message")
    content = _message_content(message)
    if content:
        response["output"].append({"type": "message", "id": _identifier(response["id"] + ":message", "msg_"),
                                   "role": "assistant", "status": status, "content": content})
    calls = message.get("tool_calls")
    if calls is not None:
        if not isinstance(calls, list):
            raise ResponsesProtocolError("invalid Chat tool calls")
        seen = set()
        for index, call in enumerate(calls):
            item = _function(call, response["id"], index, status)
            if item["call_id"] in seen:
                raise ResponsesProtocolError("duplicate Chat function call ID")
            seen.add(item["call_id"])
            response["output"].append(item)
    response.update(status=status, incomplete_details=details, usage=_usage(data.get("usage")))
    return response


async def _chat_events(lines: AsyncIterator[str]) -> AsyncIterator[dict | None]:
    fields = []

    def parse() -> dict | None:
        raw = "\n".join(fields)
        if raw == "[DONE]":
            return None
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise ResponsesProtocolError("invalid Chat SSE JSON") from error
        if not isinstance(data, dict):
            raise ResponsesProtocolError("invalid Chat SSE event")
        return data

    async for line in lines:
        if not isinstance(line, str):
            raise ResponsesProtocolError("invalid Chat SSE line")
        if line == "":
            if fields:
                yield parse()
            fields = []
        elif not line.startswith(":"):
            name, _, value = line.partition(":")
            if name == "data":
                fields.append(value[1:] if value.startswith(" ") else value)
    if fields:
        yield parse()


@dataclass
class _TextPart:
    kind: str
    index: int
    text: str = ""
    started: bool = False


@dataclass
class _Output:
    kind: str
    index: int
    item_id: str
    started: bool = False
    parts: dict[str, _TextPart] = field(default_factory=dict)
    pending_text: list[tuple[str, str]] = field(default_factory=list)
    annotations: list = field(default_factory=list)
    call_id: str | None = None
    name: str = ""
    arguments: str = ""
    sent_arguments: int = 0
    arguments_started: bool = False

    def snapshot(self, status: str, *, initial: bool = False) -> dict:
        if self.kind == "function_call":
            return {"type": "function_call", "id": self.item_id, "call_id": self.call_id,
                    "name": self.name, "arguments": "" if initial else self.arguments, "status": status}
        content = []
        if not initial:
            for part in self.parts.values():
                if part.kind == "content":
                    content.append({"type": "output_text", "text": part.text, "annotations": self.annotations, "logprobs": []})
                else:
                    content.append({"type": "refusal", "refusal": part.text})
        return {"type": "message", "id": self.item_id, "role": "assistant", "status": status, "content": content}


class _ChatStream:
    def __init__(self):
        self.response: dict | None = None
        self.source_id: str | None = None
        self.sequence = 0
        self.outputs: list[_Output] = []
        self.message: _Output | None = None
        self.tools: dict[int, _Output] = {}
        self.finish: str | None = None
        self.usage: dict | None = None

    def event(self, kind: str, **fields) -> bytes:
        data = {"type": kind, "sequence_number": self.sequence, **fields}
        self.sequence += 1
        return ("event: " + kind + "\ndata: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8")

    def header(self, data: dict) -> list[bytes]:
        if data.get("error") is not None:
            raise ResponsesProtocolError("Chat stream reported a provider failure")
        if self.response is None:
            self.response = _base(data)
            self.source_id = data.get("id")
            return [self.event("response.created", response=copy.deepcopy(self.response)),
                    self.event("response.in_progress", response=copy.deepcopy(self.response))]
        if data.get("id") and self.source_id and data["id"] != self.source_id:
            raise ResponsesProtocolError("Chat stream response ID changed")
        if data.get("model") and data["model"] != self.response["model"]:
            raise ResponsesProtocolError("Chat stream model changed")
        if data.get("created") is not None and data["created"] != self.response["created_at"]:
            raise ResponsesProtocolError("Chat stream creation timestamp changed")
        return []

    def text(self, kind: str, text: Any) -> None:
        text = _protocol_text(text, "text delta", empty=True)
        if self.message is None:
            self.message = _Output("message", len(self.outputs), _identifier(self.response["id"] + ":message", "msg_"))
            self.outputs.append(self.message)
        part = self.message.parts.setdefault(kind, _TextPart(kind, len(self.message.parts)))
        part.text += text
        self.message.pending_text.append((kind, text))

    def tool(self, delta: Any) -> None:
        if not isinstance(delta, dict) or set(delta) - {"index", "id", "type", "function"}:
            raise ResponsesProtocolError("invalid Chat function delta")
        index = delta.get("index")
        if type(index) is not int or index < 0:
            raise ResponsesProtocolError("invalid Chat function index")
        if index not in self.tools:
            if index != len(self.tools):
                raise ResponsesProtocolError("Chat function indices are not contiguous")
            state = _Output("function_call", len(self.outputs), _identifier(self.response["id"] + ":tool:" + str(index), "fc_"))
            self.tools[index] = state
            self.outputs.append(state)
        state = self.tools[index]
        if delta.get("type") is not None and delta["type"] != "function":
            raise ResponsesProtocolError("unsupported Chat tool delta type")
        if delta.get("id") is not None:
            call_id = _protocol_text(delta["id"], "function call ID")
            if state.call_id is not None and call_id != state.call_id:
                raise ResponsesProtocolError("Chat function call ID changed")
            if any(other.call_id == call_id and other is not state for other in self.tools.values()):
                raise ResponsesProtocolError("duplicate Chat function call ID")
            state.call_id = call_id
        function = delta.get("function")
        if function is not None:
            if not isinstance(function, dict) or set(function) - {"name", "arguments"}:
                raise ResponsesProtocolError("invalid Chat function delta structure")
            if function.get("name") is not None:
                name = _protocol_text(function["name"], "function name delta", empty=True)
                if state.started and name:
                    raise ResponsesProtocolError("Chat function name changed after arguments started")
                state.name += name
            if function.get("arguments") is not None:
                arguments = _protocol_text(function["arguments"], "function arguments delta", empty=True)
                state.arguments += arguments
                if arguments:
                    state.arguments_started = True

    def flush(self) -> list[bytes]:
        result = []
        for output in self.outputs:
            if not output.started:
                if output.kind == "function_call" and not (output.call_id and output.name and output.arguments_started):
                    break  # Preserve output order while a function name is arriving.
                output.started = True
                result.append(self.event("response.output_item.added", output_index=output.index,
                                         item=output.snapshot("in_progress", initial=True)))
            if output.kind == "function_call":
                delta = output.arguments[output.sent_arguments:]
                if delta:
                    result.append(self.event("response.function_call_arguments.delta", item_id=output.item_id,
                                             output_index=output.index, delta=delta))
                    output.sent_arguments = len(output.arguments)
            else:
                for kind, text in output.pending_text:
                    part = output.parts[kind]
                    if not part.started:
                        part.started = True
                        value = {"type": "output_text", "text": "", "annotations": [], "logprobs": []} if kind == "content" else {"type": "refusal", "refusal": ""}
                        result.append(self.event("response.content_part.added", item_id=output.item_id,
                                                 output_index=output.index, content_index=part.index, part=value))
                    if text:
                        fields = {"item_id": output.item_id, "output_index": output.index, "content_index": part.index, "delta": text}
                        if kind == "content":
                            fields["logprobs"] = []
                        result.append(self.event("response.output_text.delta" if kind == "content" else "response.refusal.delta", **fields))
                output.pending_text.clear()
        return result

    def consume(self, data: dict) -> list[bytes]:
        result = self.header(data)
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ResponsesProtocolError("Chat stream must contain at most one choice")
        if data.get("usage") is not None:
            self.usage = _usage(data["usage"])
        if not choices:
            return result
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
            raise ResponsesProtocolError("invalid Chat stream choice")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise ResponsesProtocolError("invalid Chat stream delta")
        if set(delta) - {"role", "content", "refusal", "tool_calls", "reasoning_content", "annotations", "audio", "function_call"}:
            raise ResponsesProtocolError("unsupported Chat stream delta field")
        if delta.get("role") not in (None, "assistant") or delta.get("audio") is not None or delta.get("function_call") is not None:
            raise ResponsesProtocolError("unsupported Chat stream delta type")
        if self.finish is not None and any(delta.get(key) for key in ("content", "refusal", "tool_calls")):
            raise ResponsesProtocolError("Chat stream data followed its finish reason")
        for kind in ("content", "refusal"):
            if delta.get(kind) is not None:
                self.text(kind, delta[kind])
        if delta.get("annotations") is not None:
            if self.message is None or "content" not in self.message.parts:
                raise ResponsesProtocolError("Chat annotations have no answer text")
            self.message.annotations.extend(_annotations(delta["annotations"]))
        calls = delta.get("tool_calls")
        if calls is not None:
            if not isinstance(calls, list):
                raise ResponsesProtocolError("invalid Chat stream tool calls")
            for call in calls:
                self.tool(call)
        if choice.get("finish_reason") is not None:
            _status(choice["finish_reason"])
            if self.finish is not None:
                raise ResponsesProtocolError("Chat stream repeated its finish reason")
            self.finish = choice["finish_reason"]
            for tool in self.tools.values():
                if not tool.call_id or not tool.name:
                    raise ResponsesProtocolError("Chat stream has an incomplete function identity")
                tool.arguments_started = True
        result.extend(self.flush())
        return result

    def terminal(self) -> list[bytes]:
        if self.response is None or self.finish is None:
            raise ResponsesProtocolError("Chat stream ended without a finish reason")
        status, details = _status(self.finish)
        result = self.flush()
        if any(not output.started for output in self.outputs):
            raise ResponsesProtocolError("Chat stream has incomplete output items")
        for output in self.outputs:
            if output.kind == "function_call":
                result.append(self.event("response.function_call_arguments.done", item_id=output.item_id,
                                         output_index=output.index, name=output.name, arguments=output.arguments))
            else:
                for part in output.parts.values():
                    fields = {"item_id": output.item_id, "output_index": output.index, "content_index": part.index}
                    if part.kind == "content":
                        for index, annotation in enumerate(output.annotations):
                            result.append(self.event("response.output_text.annotation.added", **fields,
                                                     annotation_index=index, annotation=annotation))
                        result.append(self.event("response.output_text.done", **fields, text=part.text, logprobs=[]))
                        value = {"type": "output_text", "text": part.text, "annotations": output.annotations, "logprobs": []}
                    else:
                        result.append(self.event("response.refusal.done", **fields, refusal=part.text))
                        value = {"type": "refusal", "refusal": part.text}
                    result.append(self.event("response.content_part.done", **fields, part=value))
            result.append(self.event("response.output_item.done", output_index=output.index, item=output.snapshot(status)))
        self.response.update(status=status, incomplete_details=details, usage=self.usage,
                             output=[output.snapshot(status) for output in self.outputs])
        result.append(self.event("response.completed" if status == "completed" else "response.incomplete",
                                 response=copy.deepcopy(self.response)))
        return result


async def from_chat_stream(lines: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Yield typed Responses SSE events; never report success for a truncated Chat stream."""
    state = _ChatStream()
    async for data in _chat_events(lines):
        if data is None:
            for event in state.terminal():
                yield event
            return
        for event in state.consume(data):
            yield event
    raise ResponsesProtocolError("Chat stream ended without DONE")
