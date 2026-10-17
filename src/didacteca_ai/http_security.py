"""Controles HTTP locales a cada app/proceso, antes de analizar el contrato."""

from __future__ import annotations

import asyncio
import json
import math
from time import monotonic

from starlette._utils import get_route_path
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from didacteca_ai.config import Settings
from didacteca_ai.errors import DomainError, ErrorCode


EXECUTE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            # No incluir claves ni valores arbitrarios en errores o registros.
            raise _DuplicateKey
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("Constante JSON no válida")


class ExecuteSecurityMiddleware:
    """Admisión inmediata y cuerpo acotado; no crea tareas ni colas de espera.

    El contador se modifica sin await y se libera en finally, también ante
    cancelación. Los límites son por proceso; varios workers requieren un
    límite compartido en el proxy. La IP es scope.client: no se leen cabeceras
    reenviadas. El servidor debe confiar solo en proxies explícitos.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.active = 0
        # IP -> (inicio monotónico de ventana fija, solicitudes admitidas).
        self.clients: dict[str, tuple[float, int]] = {}

    def _rate_check(self, scope: Scope) -> tuple[ErrorCode | None, int]:
        now = monotonic()
        window = self.settings.rate_limit_window_seconds
        expired = [ip for ip, (start, _) in self.clients.items() if now - start >= window]
        for ip in expired:
            del self.clients[ip]
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        entry = self.clients.get(ip)
        if entry is None:
            if len(self.clients) >= self.settings.rate_limit_max_clients:
                earliest = min(start + window for start, _ in self.clients.values())
                return ErrorCode.CLIENT_CAPACITY_REACHED, max(1, math.ceil(earliest - now))
            self.clients[ip] = (now, 1)
            return None, 0
        start, count = entry
        if count >= self.settings.rate_limit_requests:
            return ErrorCode.REQUEST_RATE_LIMITED, max(1, math.ceil(start + window - now))
        self.clients[ip] = (start, count + 1)
        return None, 0

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send, code: ErrorCode, retry_after: int = 0
    ) -> None:
        messages = {
            ErrorCode.REQUEST_BODY_TOO_LARGE: "El cuerpo supera el límite de bytes permitido.",
            ErrorCode.REQUEST_BODY_TIMEOUT: "Se agotó el tiempo para recibir el cuerpo de la solicitud.",
            ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Envía el cuerpo con Content-Type application/json.",
            ErrorCode.INVALID_JSON: "El cuerpo debe ser JSON válido.",
            ErrorCode.DUPLICATE_JSON_KEYS: "El JSON contiene claves repetidas; envía cada clave una sola vez.",
            ErrorCode.REQUEST_RATE_LIMITED: "Se alcanzó el límite temporal de solicitudes de este cliente.",
            ErrorCode.EXECUTION_CAPACITY_REACHED: "La capacidad de ejecuciones simultáneas está ocupada.",
            ErrorCode.CLIENT_CAPACITY_REACHED: "La capacidad temporal de clientes está ocupada.",
        }
        error = DomainError(code, messages[code])
        headers = dict(EXECUTE_HEADERS)
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        await JSONResponse(error.to_payload(), status_code=error.http_status, headers=headers)(
            scope, receive, send
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or get_route_path(scope) != "/execute" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"x-content-type-options"}
                ]
                message = dict(message, headers=headers + [
                    (key.lower().encode("ascii"), value.encode("ascii"))
                    for key, value in EXECUTE_HEADERS.items()
                ])
            await send(message)

        code, retry_after = self._rate_check(scope)
        if code is not None:
            await self._reject(scope, receive, secured_send, code, retry_after)
            return
        if self.active >= self.settings.max_concurrent_executions:
            await self._reject(scope, receive, secured_send, ErrorCode.EXECUTION_CAPACITY_REACHED, 1)
            return

        self.active += 1
        try:
            media_types = [value for key, value in scope["headers"] if key.lower() == b"content-type"]
            if len(media_types) != 1 or media_types[0].split(b";", 1)[0].strip().lower() != b"application/json":
                await self._reject(scope, receive, secured_send, ErrorCode.UNSUPPORTED_MEDIA_TYPE)
                return

            body = bytearray()
            too_large = False
            try:
                async with asyncio.timeout(self.settings.request_body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > self.settings.max_request_body_bytes:
                            too_large = True
                            break
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await self._reject(scope, receive, secured_send, ErrorCode.REQUEST_BODY_TIMEOUT)
                return
            if too_large:
                await self._reject(scope, receive, secured_send, ErrorCode.REQUEST_BODY_TOO_LARGE)
                return
            try:
                json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            except _DuplicateKey:
                await self._reject(scope, receive, secured_send, ErrorCode.DUPLICATE_JSON_KEYS)
                return
            except (ValueError, UnicodeError, RecursionError):
                await self._reject(scope, receive, secured_send, ErrorCode.INVALID_JSON)
                return

            # Entregar los mismos bytes al parser de FastAPI; después preservar
            # http.disconnect para no interferir con su ciclo de respuesta.
            delivered = False

            async def replay_receive() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, secured_send)
        finally:
            self.active -= 1
