"""Fail-closed, image-only HTTP adapter for a pinned Qwen3.8 deployment.

This module deliberately imports no model, CUDA, or image-processing packages.
The server owns tokenization and chat-template formatting. Its advertised model
ID is checked against the local deployment manifest; that check is a declaration
of identity, not independent attestation of the server's weights or hardware.
"""
from __future__ import annotations

import base64
import copy
import http.client
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request


_TOKEN_FIELDS = {
    'input_tokens': ('prompt_tokens',),
    'output_tokens': ('completion_tokens',),
    'reasoning_tokens': ('completion_tokens_details', 'reasoning_tokens'),
}
_THINK_TAG = re.compile(r'<\s*/?\s*think\b', re.IGNORECASE)
_INLINE_THINK = re.compile(r'\A\s*<think>(.*?)</think>(.*)\Z', re.DOTALL)
_SECRET_KEYS = {'api_key', 'authorization', 'password', 'secret', 'access_token'}


class Qwen38Error(RuntimeError):
    """The server did not produce a complete, attributable final answer."""


class Qwen38TruncatedError(Qwen38Error):
    """A completion exhausted its budget; partial text is never a prediction."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # In particular, do not forward an Authorization header to a redirected host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _positive_integer(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f'{name} must be a positive integer')


def _reject_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('deployment keys must be strings')
            if key.casefold() in _SECRET_KEYS:
                raise ValueError('deployment must not contain credentials')
            _reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item)


def _usage_values(response):
    usage = response.get('usage')
    if usage is None:
        return {key: None for key in _TOKEN_FIELDS}
    if not isinstance(usage, dict):
        raise Qwen38Error('Server returned malformed token usage')
    details = usage.get('completion_tokens_details')
    if details is not None and not isinstance(details, dict):
        raise Qwen38Error('Server returned malformed token usage')
    values = {}
    for key, path in _TOKEN_FIELDS.items():
        value = usage
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        if value is not None and (type(value) is not int or value < 0):
            raise Qwen38Error('Server returned malformed token usage')
        values[key] = value
    # SGLang's pinned API reports this directly under usage; OpenAI-compatible
    # servers may use completion_tokens_details instead. Never silently choose
    # between contradictory measurements.
    direct_reasoning = usage.get('reasoning_tokens')
    if direct_reasoning is not None:
        if type(direct_reasoning) is not int or direct_reasoning < 0:
            raise Qwen38Error('Server returned malformed token usage')
        if values['reasoning_tokens'] is not None and values['reasoning_tokens'] != direct_reasoning:
            raise Qwen38Error('Server returned conflicting reasoning token usage')
        values['reasoning_tokens'] = direct_reasoning
    return values


def _final_content(response, model):
    if 'model' in response and response['model'] != model:
        raise Qwen38Error('Response model differs from the pinned served model')
    choices = response.get('choices')
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise Qwen38Error('Server must return exactly one completion choice')
    choice = choices[0]
    if choice.get('finish_reason') == 'length':
        raise Qwen38TruncatedError('Completion exhausted its token budget; partial answers are unusable')
    if choice.get('finish_reason') != 'stop':
        # Do not quote server-provided content or error descriptions into logs.
        raise Qwen38Error('Completion did not finish with stop; truncated or failed answers are unusable')
    message = choice.get('message')
    if not isinstance(message, dict) or message.get('role', 'assistant') != 'assistant':
        raise Qwen38Error('Server returned a malformed assistant message')
    if message.get('refusal') or message.get('tool_calls'):
        raise Qwen38Error('Server returned a refusal or tool call instead of a final answer')
    reasoning = message.get('reasoning_content')
    if reasoning is not None and not isinstance(reasoning, str):
        raise Qwen38Error('Server returned malformed reasoning content')
    content = message.get('content')
    if not isinstance(content, str) or not content.strip():
        raise Qwen38Error('Server returned no final answer')
    if _THINK_TAG.search(content):
        match = _INLINE_THINK.fullmatch(content) if reasoning is None else None
        if match is None or _THINK_TAG.search(match.group(1)) or _THINK_TAG.search(match.group(2)):
            raise Qwen38Error('Server returned an ambiguous or unclosed reasoning block')
        content = match.group(2)
        if not content.strip():
            raise Qwen38Error('Server returned reasoning without a final answer')
    # Existing pipeline parsers see only the original final text, never reasoning.
    return content


class Qwen38Client:
    """One stateless chat-completion request for each pipeline inference call."""

    def __init__(self, base_url: str, model: str, deployment: dict,
                 thinking: str = 'off', max_completion_tokens: int = 4096,
                 timeout_seconds: float = 180, api_key_env: str = 'QWEN38_API_KEY'):
        if not isinstance(base_url, str) or base_url != base_url.strip():
            raise ValueError('base_url must be an absolute HTTP(S) API URL')
        try:
            parsed = urllib.parse.urlsplit(base_url)
            port = parsed.port
        except ValueError:
            raise ValueError('base_url must be an absolute HTTP(S) API URL') from None
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.query or parsed.fragment or '?' in base_url or '#' in base_url or
                any(char.isspace() or ord(char) < 32 for char in base_url) or
                (port is not None and port < 1)):
            raise ValueError('base_url must use HTTP(S) without credentials, query, or fragment')
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise ValueError('model must be a nonempty served-model ID')
        if not isinstance(deployment, dict) or not deployment:
            raise ValueError('deployment must be a nonempty pinned deployment manifest')
        _reject_secrets(deployment)
        try:
            json.dumps(deployment, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError('deployment must contain only finite JSON values') from None
        if deployment.get('served_model') != model:
            raise ValueError('model must match deployment.served_model')
        if thinking not in ('off', 'low', 'medium', 'xhigh'):
            raise ValueError('thinking must be off, low, medium, or xhigh')
        _positive_integer(max_completion_tokens, 'max_completion_tokens')
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or
                not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError('timeout_seconds must be finite and positive')
        if not isinstance(api_key_env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', api_key_env):
            raise ValueError('api_key_env must be an environment-variable name')
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.deployment = copy.deepcopy(deployment)
        self.thinking = thinking
        self.max_completion_tokens = max_completion_tokens
        self.timeout_seconds = timeout_seconds
        self._api_key_env = api_key_env
        self._verified = False
        self._last_final_text = None
        self._opener = urllib.request.build_opener(_NoRedirect())
        self._model_calls = self._successful_calls = self._failed_calls = 0
        self._successful_seconds = 0.0
        self._known_tokens = {key: 0 for key in _TOKEN_FIELDS}
        self._missing_usage = {key: 0 for key in _TOKEN_FIELDS}

    def _request_json(self, path, payload=None):
        headers = {'Accept': 'application/json'}
        key = os.environ.get(self._api_key_env)
        if key:
            if any(ord(char) < 32 or ord(char) > 126 for char in key):
                raise Qwen38Error('API credential contains an invalid header character')
            headers['Authorization'] = f'Bearer {key}'
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    raise Qwen38Error(f'Server returned HTTP {int(response.status)}')
                raw = response.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            raise Qwen38Error(f'Server returned HTTP {status}') from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
            # URL errors can contain sensitive server text; expose only a fixed error.
            raise Qwen38Error('Could not complete the model server request') from None
        if len(raw) > 8 * 1024 * 1024:
            raise Qwen38Error('Server response exceeded the size limit')
        try:
            result = json.loads(raw.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (UnicodeError, ValueError, TypeError):
            raise Qwen38Error('Server returned invalid JSON') from None
        if not isinstance(result, dict) or 'error' in result:
            raise Qwen38Error('Server returned an invalid API response')
        return result

    def verify(self):
        """Check the declared served-model ID; do not attest remote model weights."""
        self._verified = False
        response = self._request_json('/models')
        advertised = response.get('data')
        if (not isinstance(advertised, list) or not advertised or
                any(not isinstance(item, dict) or not isinstance(item.get('id'), str)
                    or not item['id'] for item in advertised)):
            raise Qwen38Error('Server returned a malformed model listing')
        if self.model not in {item['id'] for item in advertised}:
            raise Qwen38Error('Pinned served-model ID is not advertised by the server')
        self._verified = True
        return self.model_details()

    def infer(self, prompt: str, images: list, logger, max_tokens: int = 200,
              response_schema: dict | None = None, bounded_response: bool = False) -> str:
        self._last_final_text = None
        if type(bounded_response) is not bool or (bounded_response and response_schema is None):
            raise ValueError('Bounded recovery needs a query schema and a Boolean flag')
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('prompt must be nonempty text')
        if not isinstance(images, list) or not images:
            raise ValueError('images must be a nonempty list of page images')
        content = []
        for image in images:
            buffer = io.BytesIO()
            try:
                image.save(buffer, format='PNG')
            except Exception:
                raise ValueError('Each page image must support lossless PNG serialization') from None
            encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}})
        content.append({'type': 'text', 'text': prompt})
        thinking_on = self.thinking != 'off'
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': content}],
            'stream': False,
            'max_tokens': self.max_completion_tokens,
            'chat_template_kwargs': {'enable_thinking': thinking_on, 'preserve_thinking': False},
            'temperature': 1.0 if thinking_on else 0.7,
            'top_p': 0.95 if thinking_on else 0.8,
            'top_k': 20,
            'presence_penalty': 0.0 if thinking_on else 1.5,
            # Supported by the pinned SGLang ChatCompletionRequest. A seed alone
            # does not guarantee identical results across GPU/runtime changes.
            'seed': 0,
        }
        if thinking_on:
            payload['reasoning_effort'] = self.thinking
        if response_schema is not None:
            from model_options import query_json_schema
            payload['response_format'] = {
                'type': 'json_schema',
                'json_schema': {'name': 'document_query', 'strict': True,
                                'schema': query_json_schema(response_schema, bounded_response=bounded_response)},
            }
        logger.debug('Qwen3.8 query: %d images, thinking=%s, completion budget=%d (legacy hint=%s)',
                     len(images), self.thinking, self.max_completion_tokens, max_tokens)
        started = time.monotonic()
        usage = {key: None for key in _TOKEN_FIELDS}
        self._model_calls += 1
        try:
            if not self._verified:
                self.verify()
            response = self._request_json('/chat/completions', payload)
            usage = _usage_values(response)
            final = _final_content(response, self.model)
        except BaseException:
            self._failed_calls += 1
            raise
        else:
            self._successful_calls += 1
            self._successful_seconds += time.monotonic() - started
            self._last_final_text = final
            return final
        finally:
            for key, value in usage.items():
                if value is None:
                    self._missing_usage[key] += 1
                else:
                    self._known_tokens[key] += value

    @property
    def last_final_text(self):
        """Only the most recent successful final answer; no reasoning retained."""
        return self._last_final_text

    def snapshot(self) -> dict:
        result = {
            'model_calls': self._model_calls,
            'successful_calls': self._successful_calls,
            'failed_calls': self._failed_calls,
            'successful_seconds': self._successful_seconds,
        }
        for key in _TOKEN_FIELDS:
            result[key] = self._known_tokens[key] if not self._missing_usage[key] else None
            result['known_' + key] = self._known_tokens[key]
            result['missing_' + key + '_calls'] = self._missing_usage[key]
        return result

    def model_details(self) -> dict:
        from model_options import RESPONSE_FORMAT, RESPONSE_RECOVERY_POLICY
        return {
            'backend': 'qwen38-http',
            'served_model': self.model,
            'deployment': copy.deepcopy(self.deployment),
            'thinking': self.thinking,
            'max_completion_tokens': self.max_completion_tokens,
            'response_format': RESPONSE_FORMAT,
            'response_recovery': RESPONSE_RECOVERY_POLICY,
            'generation': {
                'temperature': 0.7 if self.thinking == 'off' else 1.0,
                'top_p': 0.8 if self.thinking == 'off' else 0.95,
                'top_k': 20,
                'presence_penalty': 1.5 if self.thinking == 'off' else 0.0,
                'seed': 0,
                'preserve_thinking': False,
            },
            'verification': 'declared_manifest_and_advertised_model_id' if self._verified else 'unverified',
        }
