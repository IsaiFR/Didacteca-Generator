"""Aplicación FastAPI local para ejecutar recursos educativos Didacteca."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from didacteca_ai.config import Settings, get_settings
from didacteca_ai.context_client import ContextClient
from didacteca_ai.errors import (
    DomainError,
    ErrorCode,
    ErrorDetails,
    ErrorResponse,
)
from didacteca_ai.llm_client import LLMClient
from didacteca_ai.schemas import ExecuteRequest, PublicSuccess
from didacteca_ai.service import ExecutionService


logger = logging.getLogger("didacteca_ai.api")
_ACTIONS = frozenset({"chat", "quiz", "activity"})
_REQUIRED_INPUTS = frozenset({"book_id", "section_id", "instructions"})
_PUBLIC_FIELDS = frozenset({"action", "book_id", "section_id", "instructions"})


def _request_action(request: Request) -> str | None:
    value = getattr(request.state, "validated_action", None)
    return value if value in _ACTIONS else None


def _validation_error(request: Request, error: RequestValidationError) -> DomainError:
    """Mapea errores de Pydantic sin devolver valores ni nombres arbitrarios."""

    body = error.body if isinstance(error.body, dict) else {}
    raw_action = body.get("action")
    action = raw_action if isinstance(raw_action, str) and raw_action in _ACTIONS else None

    missing_from_validation: set[str] = set()
    invalid_from_validation: set[str] = set()
    has_non_field_error = False
    for item in error.errors():
        location = tuple(item.get("loc", ()))
        field = location[-1] if location else None
        kind = item.get("type", "")
        if kind == "missing" and field in _PUBLIC_FIELDS:
            missing_from_validation.add(str(field))
        elif field in _PUBLIC_FIELDS:
            invalid_from_validation.add(str(field))
        else:
            has_non_field_error = True
            invalid_from_validation.add("body")

    # Las cadenas vacías/solo espacios son campos requeridos por completar.
    blank_inputs = {
        field
        for field in _REQUIRED_INPUTS
        if field in body
        and isinstance(body[field], str)
        and not body[field].strip()
    }
    invalid_from_validation.difference_update(blank_inputs)
    missing = _REQUIRED_INPUTS.difference(body.keys()) | blank_inputs | (
        missing_from_validation & _REQUIRED_INPUTS
    )

    if isinstance(raw_action, str) and raw_action not in _ACTIONS:
        return DomainError(
            ErrorCode.UNSUPPORTED_ACTION,
            "La acción solicitada no está soportada.",
            details=ErrorDetails(
                missing_fields=sorted(missing),
                conflicting_fields=[],
                invalid_fields=["action"],
                constraints=["action debe ser chat, quiz o activity."],
            ),
        )

    action_is_missing = "action" not in body or "action" in missing_from_validation
    if action is not None and missing and not invalid_from_validation and not has_non_field_error:
        return DomainError(
            ErrorCode.MISSING_INPUT_FIELDS,
            "Indica book_id, section_id e instructions antes de ejecutar la acción.",
            action=action,  # type: ignore[arg-type]
            details=ErrorDetails(
                missing_fields=sorted(missing),
                conflicting_fields=[],
                invalid_fields=[],
                constraints=["Envía los tres campos como cadenas no vacías."],
            ),
        )

    invalid_fields = sorted(invalid_from_validation)
    if action_is_missing:
        invalid_fields.append("action")
    return DomainError(
        ErrorCode.INVALID_REQUEST,
        "El cuerpo debe contener los cuatro campos con tipos válidos y sin propiedades adicionales.",
        action=action,  # type: ignore[arg-type]
        details=ErrorDetails(
            missing_fields=sorted(missing),
            conflicting_fields=[],
            invalid_fields=list(dict.fromkeys(invalid_fields or ["body"])),
            constraints=["Usa exclusivamente action, book_id, section_id e instructions."],
        ),
    )


def _log_api_error(request: Request, code: str, action: str | None) -> None:
    logger.info(
        "request_rejected",
        extra={
            "request_id": getattr(request.state, "request_id", uuid4().hex),
            "action": action,
            "code": code,
            "duration_ms": max(
                0,
                int((time.perf_counter() - getattr(request.state, "started", time.perf_counter())) * 1000),
            ),
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        },
    )


def create_app(
    settings: Settings | None = None,
    service: ExecutionService | None = None,
) -> FastAPI:
    """Crea la app sin abrir clientes externos hasta entrar en lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            app.state.execution_service = service
            if settings is not None:
                app.state.settings = settings
            yield
            return

        active_settings = settings or get_settings()
        key = active_settings.openai_api_key
        if key is None or not key.get_secret_value().strip():
            raise RuntimeError(
                "Falta OPENAI_API_KEY. Configúrala localmente antes de iniciar la aplicación."
            )

        app.state.settings = active_settings
        context_client: ContextClient | None = None
        llm_client: LLMClient | None = None
        try:
            context_client = ContextClient(active_settings)
            llm_client = LLMClient(active_settings)
            app.state.execution_service = ExecutionService(
                active_settings,
                context_client,
                llm_client,
            )
            yield
        finally:
            try:
                if llm_client is not None:
                    await llm_client.aclose()
            finally:
                if context_client is not None:
                    await context_client.aclose()

    app = FastAPI(
        title="Didacteca AI Engineer Jr",
        description="Genera chat, quizzes y actividades basados en una sección exacta del Context Service.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = uuid4().hex
        request.state.started = time.perf_counter()
        request.state.validated_action = None
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        domain_error = _validation_error(request, error)
        _log_api_error(request, domain_error.code.value, domain_error.action)
        return JSONResponse(
            status_code=domain_error.http_status,
            content=domain_error.to_payload(),
        )

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
        # ExecutionService registra sus errores con sus contadores locales.
        if error.code in {ErrorCode.INVALID_REQUEST, ErrorCode.UNSUPPORTED_ACTION}:
            _log_api_error(request, error.code.value, error.action)
        return JSONResponse(
            status_code=error.http_status,
            content=error.to_payload(),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _error: Exception) -> JSONResponse:
        action = _request_action(request)
        domain_error = DomainError(
            ErrorCode.INTERNAL_ERROR,
            "Ocurrió un error interno al ejecutar la solicitud.",
            action=action,  # type: ignore[arg-type]
        )
        if not getattr(request.state, "execution_started", False):
            _log_api_error(request, domain_error.code.value, action)
        return JSONResponse(
            status_code=domain_error.http_status,
            content=domain_error.to_payload(),
        )

    @app.post(
        "/execute",
        response_model=PublicSuccess,
        responses={
            404: {"model": ErrorResponse, "description": "Libro o sección inexistentes."},
            422: {"model": ErrorResponse, "description": "Solicitud inválida o aclaración requerida."},
            500: {"model": ErrorResponse, "description": "Error interno."},
            501: {"model": ErrorResponse, "description": "Capacidad no implementada."},
            502: {"model": ErrorResponse, "description": "Respuesta externa inválida."},
            503: {"model": ErrorResponse, "description": "Dependencia no disponible."},
            504: {"model": ErrorResponse, "description": "Tiempo de espera agotado."},
        },
    )
    async def execute(body: ExecuteRequest, request: Request) -> PublicSuccess:
        request.state.validated_action = body.action
        execution_service: ExecutionService = request.app.state.execution_service
        request.state.execution_started = True
        return await execution_service.execute(body)

    return app


app = create_app()
