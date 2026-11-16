"""Restricted, self-contained Responses histories without a Chat round trip.

The Chat-shaped view below is used only for the existing tier/guard checks.
The validated native body, including phases and tool image results, is forwarded
separately. No provider conversation or file ID is resolved here. Existing user
image URLs stay opaque; the newly supported tool images must be inline data.
"""
from __future__ import annotations

import copy
import re

from chat_adapter import to_chat_request
from guard import CANARY_PREFIX, DECLARATION, USER_CLOSE, USER_OPEN
from responses_adapter import ResponsesRequestError


def _object(value, fields, label):
    if not isinstance(value, dict) or set(value) - set(fields):
        raise ResponsesRequestError(f"unsupported native {label} structure")


def _string(value, label, *, empty=False):
    if not isinstance(value, str) or (not empty and not value):
        raise ResponsesRequestError(f"invalid native {label}")


def _identity(item):
    if item.get('id') is not None:
        _string(item['id'], 'item ID')
    if item.get('status') not in (None, 'completed', 'incomplete'):
        raise ResponsesRequestError('native input item must be finished history')


def _parts(parts, role, *, tool_output=False):
    if not isinstance(parts, list) or not 1 <= len(parts) <= 200:
        raise ResponsesRequestError('native content requires 1..200 parts')
    for part in parts:
        if not isinstance(part, dict):
            raise ResponsesRequestError('invalid native content part')
        kind = part.get('type')
        if kind in ('input_text', 'output_text'):
            fields = {'type', 'text'} if tool_output else {'type', 'text', 'annotations', 'logprobs'}
            _object(part, fields, 'text part')
            if kind == 'output_text' and (tool_output or role != 'assistant'):
                raise ResponsesRequestError('output_text requires assistant history')
            _string(part.get('text'), 'text', empty=True)
            if part.get('annotations') not in (None, []) or part.get('logprobs') not in (None, []):
                raise ResponsesRequestError('annotated native input is unsupported')
        elif kind == 'input_image' and (role == 'user' or tool_output):
            _object(part, {'type', 'image_url', 'detail'}, 'image part')
            image = part.get('image_url')
            _string(image, 'image URL')
            # User images retain the published URL contract. Tool images are
            # the new capability, restricted to self-contained image data.
            if tool_output and not re.fullmatch(
                    r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}', image):
                raise ResponsesRequestError('native images require inline image data')
            if part.get('detail') not in (None, 'auto', 'low', 'high', 'original'):
                raise ResponsesRequestError('unsupported native image detail')
        elif kind == 'refusal' and role == 'assistant' and not tool_output:
            _object(part, {'type', 'refusal'}, 'refusal part')
            _string(part.get('refusal'), 'refusal', empty=True)
        else:
            raise ResponsesRequestError('unsupported native content part type')


def _reasoning(item):
    """Validate a complete replay item, not an external reasoning reference."""
    _object(item, {'type', 'id', 'status', 'summary', 'encrypted_content', 'content'}, 'reasoning item')
    _identity(item)
    for field, kind in (('summary', 'summary_text'), ('content', 'reasoning_text')):
        if field not in item or (field == 'content' and item[field] is None):
            continue
        parts = item[field]
        if not isinstance(parts, list) or len(parts) > 200:
            raise ResponsesRequestError('native reasoning requires bounded text parts')
        for part in parts:
            _object(part, {'type', 'text'}, 'reasoning text part')
            if part.get('type') != kind:
                raise ResponsesRequestError('unsupported native reasoning text type')
            _string(part.get('text'), 'reasoning text', empty=True)
    if item.get('encrypted_content') is not None:
        _string(item['encrypted_content'], 'encrypted reasoning')
    if not (isinstance(item.get('summary'), list) or isinstance(item.get('content'), list)
            or isinstance(item.get('encrypted_content'), str)):
        raise ResponsesRequestError('native reasoning requires self-contained data')


def prepare(body):
    """Validate native history; return its separate tier/guard view and params.

    Generation settings retain the current public Responses contract. This does
    not add reasoning/include/parallel or other engine-specific request fields.
    """
    # Reuse the current generation-parameter validation on a synthetic text input,
    # never on the history that will be sent over the wire.
    _, params = to_chat_request({**body, 'input': ''})
    value = body.get('input')
    if isinstance(value, str):
        view = [{'role': 'user', 'content': value}]
    elif isinstance(value, list):
        if not value or len(value) > 200:
            raise ResponsesRequestError('native history requires 1..200 items')
        view, call_ids = [], set()
        for item in value:
            if not isinstance(item, dict):
                raise ResponsesRequestError('invalid native input item')
            kind = item.get('type', 'message')
            if kind == 'message':
                _object(item, {'type', 'id', 'role', 'content', 'status', 'phase'}, 'message')
                role = item.get('role')
                if role not in ('user', 'assistant', 'system', 'developer'):
                    raise ResponsesRequestError('unsupported native message role')
                _identity(item)
                if item.get('phase') not in (None, 'commentary', 'final_answer'):
                    raise ResponsesRequestError('unsupported native assistant phase')
                if item.get('phase') is not None and role != 'assistant':
                    raise ResponsesRequestError('phase requires assistant history')
                content = item.get('content')
                if not isinstance(content, str):
                    _parts(content, role)
                    content = '\n'.join(part['text'] for part in content
                        if part.get('type') in ('input_text', 'output_text'))
                view.append({'role': role, 'content': content})
            elif kind == 'function_call':
                _object(item, {'type', 'id', 'call_id', 'name', 'arguments', 'status', 'namespace'}, 'function call')
                _identity(item)
                if item.get('namespace') not in (None, ''):
                    raise ResponsesRequestError('external function namespaces are unsupported')
                for field in ('call_id', 'name', 'arguments'):
                    _string(item.get(field), field, empty=field == 'arguments')
                if item['call_id'] in call_ids:
                    raise ResponsesRequestError('duplicate native function call ID')
                call_ids.add(item['call_id'])
                view.append({'role': 'assistant', 'content': ''})
            elif kind == 'function_call_output':
                _object(item, {'type', 'id', 'call_id', 'output', 'status'}, 'function output')
                _identity(item)
                _string(item.get('call_id'), 'function call ID')
                if item['call_id'] not in call_ids:
                    raise ResponsesRequestError('native tool output requires its preceding call')
                output = item.get('output')
                if not isinstance(output, str):
                    _parts(output, 'tool', tool_output=True)
                view.append({'role': 'tool', 'content': ''})
            elif kind == 'reasoning':
                _reasoning(item)
                # Count the native item for tier limits without turning private
                # reasoning into user/assistant answer text or guard input.
                view.append({'role': 'assistant', 'content': ''})
            else:
                raise ResponsesRequestError('unsupported native input item type')
    else:
        raise ResponsesRequestError('native input requires text or self-contained items')
    if body.get('instructions') is not None:
        view.insert(0, {'role': 'system', 'content': body['instructions']})
    return view, params


def harden(body, *, spotlight, canary):
    """Harden only user text/instructions; preserve native tool/image history."""
    result = copy.deepcopy(body)

    def wrap(text):
        return f'{USER_OPEN}\n{text}\n{USER_CLOSE}' if text else text

    if spotlight:
        if isinstance(result['input'], str):
            result['input'] = wrap(result['input'])
        else:
            for item in result['input']:
                if item.get('type', 'message') != 'message' or item.get('role') != 'user':
                    continue
                if isinstance(item['content'], str):
                    item['content'] = wrap(item['content'])
                else:
                    for part in item['content']:
                        if part['type'] == 'input_text':
                            part['text'] = wrap(part['text'])
    extra = (DECLARATION if spotlight else '') + (f'{CANARY_PREFIX}{canary}' if canary else '')
    if extra:
        result['instructions'] = result.get('instructions', '') + extra
    return result
