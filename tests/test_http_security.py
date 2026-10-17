"""Verificaciones HTTP offline a través de la app ASGI completa, sin sockets."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI

from didacteca_ai import http_security
from didacteca_ai.errors import ErrorResponse
from didacteca_ai.main import create_app
from didacteca_ai.schemas import ChatSuccess


BODY = json.dumps({
    "action": "chat", "book_id": "book_001", "section_id": "section_04",
    "instructions": "Explica el discriminante.",
}).encode()


class LocalService:
    """Sustituye proveedores; todo el transporte y parsing HTTP son reales."""

    def __init__(self):
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False
        self.fail = False

    async def execute(self, body):
        self.calls += 1
        self.started.set()
        if self.block:
            await self.release.wait()
        if self.fail:
            raise RuntimeError("no se debe publicar este detalle")
        return ChatSuccess(action=body.action, answer="El discriminante informa sobre las raíces.")


async def request(
    app, *, chunks=None, headers=None, ip="127.0.0.1", path="/execute", method="POST",
    disconnect=False, raise_server_error=True,
    receive_started=None, root_path="",
):
    """Transporta chunks reales (incluido CL falso), sin normalización HTTPX."""
    chunks = [BODY] if chunks is None else chunks
    headers = [(b"content-type", b"application/json")] if headers is None else headers
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": method, "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": root_path,
        "headers": headers, "client": (ip, 1234), "server": ("testserver", 80),
    }
    messages = []
    pending = list(chunks)

    async def receive():
        if pending:
            chunk = pending.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(pending)}
        if disconnect:
            return {"type": "http.disconnect"}
        if receive_started is not None:
            receive_started.set()
        # Starlette cancela esta espera al terminar de enviar la respuesta.
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    try:
        await app(scope, receive, send)
    except Exception:
        if raise_server_error:
            raise
    if not messages:
        return None
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), body


def assert_error(response, status, code):
    actual_status, headers, body = response
    assert actual_status == status
    payload = ErrorResponse.model_validate_json(body)
    assert payload.error.code == code
    assert payload.action is None
    assert headers[b"cache-control"] == b"no-store"
    assert headers[b"x-content-type-options"] == b"nosniff"
    return headers


@pytest.mark.parametrize("extra_headers", [[], [(b"content-length", b"1")], [(b"transfer-encoding", b"chunked")]], ids=["no-content-length", "false-content-length", "chunked"])
async def test_actual_body_limit_without_trusting_content_length(settings, extra_headers):
    service = LocalService()
    configured = settings.model_copy(update={"max_request_body_bytes": len(BODY)})
    app = create_app(settings=configured, service=service)
    async with app.router.lifespan_context(app):
        response = await request(app, chunks=[BODY[:30], BODY[30:], b" "], headers=[
            (b"content-type", b"application/json"), *extra_headers,
        ])
        assert_error(response, 413, "REQUEST_BODY_TOO_LARGE")
        assert (await request(app))[0] == 200  # El rechazo no retiene un slot.
    assert service.calls == 1


@pytest.mark.parametrize("headers", [
    [], [(b"content-type", b"text/plain")], [(b"content-type", b"application/jsonp")],
    [(b"content-type", b"application/json"), (b"content-type", b"text/plain")],
], ids=["missing", "plain-text", "jsonp", "duplicate-content-type"])
async def test_missing_or_ambiguous_media_type_is_rejected(settings, headers):
    service = LocalService()
    app = create_app(settings=settings, service=service)
    async with app.router.lifespan_context(app):
        assert_error(await request(app, headers=headers), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert service.calls == 0


@pytest.mark.parametrize("body,code", [
    (b'{"action":"chat","action":"quiz"}', "DUPLICATE_JSON_KEYS"),
    (b'{"nested":{"x":1,"x":2}}', "DUPLICATE_JSON_KEYS"),
    (b'{"action":"chat","act\\u0069on":"quiz"}', "DUPLICATE_JSON_KEYS"),
    (b'{"action":', "INVALID_JSON"),
    (b'{"action":NaN}', "INVALID_JSON"),
    (b'\xff', "INVALID_JSON"),
    (b'', "INVALID_JSON"),
], ids=["duplicate-action", "duplicate-nested", "duplicate-unicode", "syntax", "nan", "invalid-encoding", "empty"])
async def test_json_is_checked_before_schema_or_external_execution(settings, body, code):
    service = LocalService()
    app = create_app(settings=settings, service=service)
    async with app.router.lifespan_context(app):
        assert_error(await request(app, chunks=[body]), 400, code)
    assert service.calls == 0


async def test_valid_deep_json_without_object_contract_is_422(settings):
    service = LocalService()
    app = create_app(settings=settings, service=service)
    async with app.router.lifespan_context(app):
        assert_error(await request(app, chunks=[b'[' * 128 + b']' * 128]), 422, "INVALID_REQUEST")
    assert service.calls == 0


@pytest.mark.parametrize("mode", ["root-prefix", "root-direct", "mount"])
async def test_root_path_and_mount_cannot_bypass_body_guard(settings, mode):
    service = LocalService()
    configured = settings.model_copy(update={"max_request_body_bytes": len(BODY)})
    app = create_app(settings=configured, service=service)
    target = app
    path = "/execute" if mode == "root-direct" else "/api/execute"
    root_path = "/api"
    if mode == "mount":
        target = FastAPI()
        target.mount("/api", app)
        root_path = ""
    async with app.router.lifespan_context(app):
        response = await request(target, path=path, root_path=root_path, chunks=[BODY, b" "])
        assert_error(response, 413, "REQUEST_BODY_TOO_LARGE")
        assert (await request(target, path=path, root_path=root_path))[0] == 200
    assert service.calls == 1


async def test_success_keeps_contract_and_accepts_json_parameters(settings):
    service = LocalService()
    app = create_app(settings=settings, service=service)
    async with app.router.lifespan_context(app):
        status, headers, raw = await request(app, headers=[(b"content-type", b"Application/JSON; charset=utf-8")])
        assert status == 200
        assert set(json.loads(raw)) == {"action", "answer"}
        assert headers[b"cache-control"] == b"no-store"
        assert headers[b"x-content-type-options"] == b"nosniff"
        docs = await request(app, method="GET", path="/docs", headers=[])
        assert docs[0] == 200
        schema = await request(app, method="GET", path="/openapi.json", headers=[])
        assert schema[0] == 200
        assert set(json.loads(schema[2])["paths"]["/execute"]["post"]["responses"]) >= {"400", "413", "415", "429", "503"}


async def test_rate_window_uses_client_ip_and_expires_without_sleep(settings, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(http_security, "monotonic", lambda: now[0])
    service = LocalService()
    configured = settings.model_copy(update={"rate_limit_requests": 2})
    app = create_app(settings=configured, service=service)
    async with app.router.lifespan_context(app):
        for forged in (b"1.2.3.4", b"5.6.7.8"):
            assert (await request(app, headers=[(b"content-type", b"application/json"), (b"x-forwarded-for", forged)]))[0] == 200
        headers = assert_error(await request(app), 429, "REQUEST_RATE_LIMITED")
        assert headers[b"retry-after"] == b"60"
        assert (await request(app, ip="192.0.2.2"))[0] == 200
        assert (await request(app, method="GET", path="/docs"))[0] == 200
        now[0] += 60
        assert (await request(app))[0] == 200
    assert service.calls == 4


async def test_client_table_is_bounded_without_eviction_bypass(settings, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(http_security, "monotonic", lambda: now[0])
    service = LocalService()
    configured = settings.model_copy(update={"rate_limit_max_clients": 2, "rate_limit_requests": 1})
    app = create_app(settings=configured, service=service)
    async with app.router.lifespan_context(app):
        assert (await request(app, ip="192.0.2.1"))[0] == 200
        assert (await request(app, ip="192.0.2.2"))[0] == 200
        headers = assert_error(await request(app, ip="192.0.2.3"), 503, "CLIENT_CAPACITY_REACHED")
        assert headers[b"retry-after"] == b"60"
        assert_error(await request(app, ip="192.0.2.1"), 429, "REQUEST_RATE_LIMITED")
        now[0] += 60
        assert (await request(app, ip="192.0.2.3"))[0] == 200
    assert service.calls == 3


async def test_global_capacity_rejects_without_queue_then_releases(settings):
    service = LocalService()
    service.block = True
    app = create_app(settings=settings.model_copy(update={"max_concurrent_executions": 1}), service=service)
    async with app.router.lifespan_context(app):
        first = asyncio.create_task(request(app))
        try:
            await asyncio.wait_for(service.started.wait(), 2)
            rejected = await asyncio.wait_for(request(app, ip="192.0.2.2"), 2)
            headers = assert_error(rejected, 503, "EXECUTION_CAPACITY_REACHED")
            assert headers[b"retry-after"] == b"1"
            assert service.calls == 1
        finally:
            service.release.set()
            first_result = await asyncio.wait_for(first, 2)
        assert first_result[0] == 200
        assert (await request(app))[0] == 200


async def test_cancelled_execution_does_not_leak_global_capacity(settings):
    service = LocalService()
    service.block = True
    app = create_app(settings=settings.model_copy(update={"max_concurrent_executions": 1}), service=service)
    async with app.router.lifespan_context(app):
        first = asyncio.create_task(request(app))
        await asyncio.wait_for(service.started.wait(), 2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        service.block = False
        assert (await request(app))[0] == 200


async def test_body_read_has_deadline_and_releases_capacity(settings):
    service = LocalService()
    configured = settings.model_copy(update={
        "max_concurrent_executions": 1, "request_body_timeout_seconds": 0.01,
    })
    app = create_app(settings=configured, service=service)
    async with app.router.lifespan_context(app):
        # El emisor no entrega ni un chunk; el temporizador cancela receive.
        assert_error(await request(app, chunks=[]), 408, "REQUEST_BODY_TIMEOUT")
        assert (await request(app))[0] == 200
    assert service.calls == 1


async def test_cancelled_body_read_and_disconnect_release_capacity(settings):
    service = LocalService()
    configured = settings.model_copy(update={"max_concurrent_executions": 1})
    app = create_app(settings=configured, service=service)
    async with app.router.lifespan_context(app):
        reading = asyncio.Event()
        first = asyncio.create_task(request(app, chunks=[], receive_started=reading))
        await asyncio.wait_for(reading.wait(), 2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert await request(app, chunks=[], disconnect=True) is None
        assert (await request(app))[0] == 200
    assert service.calls == 1


@pytest.mark.parametrize("path,root_path", [("/execute", ""), ("/api/execute", "/api")], ids=["direct", "root-prefix"])
async def test_failure_does_not_leak_capacity_or_sensitive_error(settings, path, root_path):
    service = LocalService()
    service.fail = True
    app = create_app(settings=settings.model_copy(update={"max_concurrent_executions": 1}), service=service)
    async with app.router.lifespan_context(app):
        status, headers, raw = await request(app, path=path, root_path=root_path, raise_server_error=False)
        assert status == 500
        assert ErrorResponse.model_validate_json(raw).error.code == "INTERNAL_ERROR"
        assert b"no se debe publicar" not in raw
        assert headers[b"cache-control"] == b"no-store"
        assert headers[b"x-content-type-options"] == b"nosniff"
        service.fail = False
        assert (await request(app))[0] == 200
