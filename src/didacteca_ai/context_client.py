"""Cliente HTTP del servicio de contexto proporcionado por Didacteca."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from pydantic import ValidationError

from .config import Settings
from .errors import DomainError, ErrorCode, ErrorDetails
from .schemas import BookSection, require_identifier


class ContextClient:
    """Recupera una sección exacta sin compartir credenciales con ese servicio."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = settings.provided_service_base_url.rstrip("/")
        self._owns_client = http_client is None
        self._http_client = (
            http_client
            if http_client is not None
            else httpx.AsyncClient(
                timeout=settings.context_timeout_seconds,
                follow_redirects=False,
            )
        )

    async def get_section(self, book_id: str, section_id: str) -> BookSection:
        """Obtiene y valida los identificadores, el contenido y su tamaño."""

        for name, value in (("book_id", book_id), ("section_id", section_id)):
            try:
                require_identifier(value)
                if len(value) > self._settings.max_identifier_chars:
                    raise ValueError("Identificador demasiado largo.")
            except (TypeError, ValueError) as exc:
                raise DomainError(
                    ErrorCode.INVALID_REQUEST,
                    "La solicitud contiene un identificador inválido.",
                    details=ErrorDetails(
                        missing_fields=[], conflicting_fields=[], invalid_fields=[name],
                        constraints=["Usa identificadores ASCII con letras, números, _ o - dentro del límite configurado."],
                    ),
                ) from exc

        try:
            async with asyncio.timeout(self._settings.context_timeout_seconds):
                async with self._http_client.stream(
                    "POST",
                    f"{self._base_url}/context",
                    json={"book_id": book_id, "section_id": section_id},
                    headers={"Accept-Encoding": "identity"},
                    timeout=self._settings.context_timeout_seconds,
                ) as response:
                    if response.headers.get("content-encoding", "identity").strip().casefold() != "identity":
                        raise DomainError(
                            ErrorCode.CONTEXT_INVALID_RESPONSE,
                            "El servicio de contexto devolvió una codificación de contenido no admitida.",
                        )
                    # No se admite compresión: así el límite se comprueba antes
                    # de que un decoder expanda un chunk arbitrariamente grande.
                    # Cuenta bytes antes de cargar JSON, también
                    # para cuerpos de error. El context manager cierra el stream
                    # cuando se supera el límite o vence el timeout total.
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > self._settings.max_context_response_bytes:
                            raise DomainError(
                                ErrorCode.CONTEXT_TOO_LARGE,
                                "La respuesta del servicio de contexto supera el límite configurado.",
                            )
                        body.extend(chunk)
        except httpx.TimeoutException as exc:
            raise DomainError(
                ErrorCode.CONTEXT_TIMEOUT,
                "El servicio de contexto excedió el tiempo límite.",
            ) from exc
        except TimeoutError as exc:
            raise DomainError(
                ErrorCode.CONTEXT_TIMEOUT,
                "El servicio de contexto excedió el tiempo límite.",
            ) from exc
        except httpx.RequestError as exc:
            raise DomainError(
                ErrorCode.CONTEXT_UNAVAILABLE,
                "No fue posible conectar con el servicio de contexto.",
            ) from exc

        if response.status_code == 404:
            self._raise_not_found(body)
        if response.status_code == 422:
            raise DomainError(
                ErrorCode.CONTEXT_REQUEST_REJECTED,
                "El servicio de contexto rechazó los identificadores recibidos.",
            )
        if response.status_code in (408, 504):
            raise DomainError(
                ErrorCode.CONTEXT_TIMEOUT,
                "El servicio de contexto excedió el tiempo límite.",
            )
        if response.status_code >= 500:
            raise DomainError(
                ErrorCode.CONTEXT_UNAVAILABLE,
                "El servicio de contexto no está disponible temporalmente.",
            )
        if response.status_code != 200:
            raise DomainError(
                ErrorCode.CONTEXT_INVALID_RESPONSE,
                "El servicio de contexto devolvió un estado HTTP inesperado.",
            )

        try:
            payload: Any = json.loads(body)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise DomainError(
                ErrorCode.CONTEXT_INVALID_RESPONSE,
                "El servicio de contexto no devolvió JSON válido.",
            ) from exc

        try:
            section = BookSection.model_validate(payload, strict=True)
        except ValidationError as exc:
            raise DomainError(
                ErrorCode.CONTEXT_INVALID_RESPONSE,
                "La respuesta del servicio de contexto no cumple el contrato.",
            ) from exc

        if section.book_id != book_id or section.section_id != section_id:
            raise DomainError(
                ErrorCode.CONTEXT_INVALID_RESPONSE,
                "El servicio de contexto devolvió una sección distinta a la solicitada.",
            )
        if not section.content.strip():
            raise DomainError(
                ErrorCode.CONTENT_EMPTY,
                "La sección solicitada no contiene texto educativo.",
            )
        if len(section.content) > self._settings.max_context_chars:
            raise DomainError(
                ErrorCode.CONTEXT_TOO_LARGE,
                "El contenido de la sección supera el límite configurado.",
            )
        return section

    @staticmethod
    def _raise_not_found(body: bytes | bytearray) -> None:
        """Usa el código estructurado del proveedor, nunca su mensaje libre."""

        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            payload = None

        code: object = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = error.get("code")

        if code == ErrorCode.BOOK_NOT_FOUND.value:
            raise DomainError(
                ErrorCode.BOOK_NOT_FOUND,
                "El libro solicitado no existe en el servicio de contexto.",
            )
        if code == ErrorCode.SECTION_NOT_FOUND.value:
            raise DomainError(
                ErrorCode.SECTION_NOT_FOUND,
                "La sección solicitada no existe en el libro indicado.",
            )
        raise DomainError(
            ErrorCode.CONTEXT_INVALID_RESPONSE,
            "El servicio de contexto devolvió un 404 con un código desconocido.",
        )

    async def aclose(self) -> None:
        """Cierra únicamente el cliente que creó esta instancia."""

        if self._owns_client:
            await self._http_client.aclose()
