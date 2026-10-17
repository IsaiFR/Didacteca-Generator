"""Orquesta extracción, recuperación y generación para POST /execute."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any, Awaitable, Callable
from uuid import uuid4

from pydantic import ValidationError

from didacteca_ai.config import Settings
from didacteca_ai.errors import DomainError, ErrorCode, InvalidModelOutput
from didacteca_ai.schemas import ExecuteRequest, ParsedInstructions, PublicSuccess
from didacteca_ai.validation import (
    validate_generation,
    validate_instructions,
    validate_request_limits,
    validate_section,
)


logger = logging.getLogger("didacteca_ai.execute")


def _metric_value(metrics: Any, name: str) -> int:
    if isinstance(metrics, Mapping):
        value = metrics.get(name, 0)
    else:
        value = getattr(metrics, name, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _metrics_snapshot(client: Any) -> tuple[int, int]:
    metrics = getattr(client, "metrics", None)
    return _metric_value(metrics, "input_tokens"), _metric_value(metrics, "output_tokens")


class ExecutionService:
    """Flujo sin estado conversacional y con un presupuesto global de reparación."""

    def __init__(self, settings: Settings, context_client: Any, llm_client: Any) -> None:
        self.settings = settings
        self.context_client = context_client
        self.llm_client = llm_client

    async def execute(self, request: ExecuteRequest) -> PublicSuccess:
        """Ejecuta una acción sin superar dos llamadas normales y una reparación."""

        if not isinstance(request, ExecuteRequest):
            try:
                request = ExecuteRequest.model_validate(request)
            except ValidationError as error:
                raise DomainError(
                    ErrorCode.INVALID_REQUEST,
                    "La solicitud no cumple el contrato de entrada.",
                ) from error

        request_id = uuid4().hex
        started = time.perf_counter()
        calls = 0
        repairs = 0
        before_input_tokens, before_output_tokens = _metrics_snapshot(self.llm_client)
        max_calls = min(3, self.settings.max_model_calls_per_execution)
        max_repairs = min(1, self.settings.max_repairs_per_execution)

        def log_completion(code: str) -> None:
            after_input_tokens, after_output_tokens = _metrics_snapshot(self.llm_client)
            logger.info(
                "execute_finished",
                extra={
                    "request_id": request_id,
                    "action": request.action,
                    "code": code,
                    "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
                    "model_calls": calls,
                    "input_tokens": max(0, after_input_tokens - before_input_tokens),
                    "output_tokens": max(0, after_output_tokens - before_output_tokens),
                },
            )

        async def call_with_repair(
            stage: str,
            operation: Callable[[str | None], Awaitable[Any]],
            validate: Callable[[Any], Any],
        ) -> Any:
            nonlocal calls, repairs
            feedback: str | None = None
            while True:
                if calls >= max_calls:
                    raise DomainError(
                        ErrorCode.MODEL_OUTPUT_INVALID,
                        "Se agotó el presupuesto de llamadas antes de validar la salida del modelo.",
                        action=request.action,
                    )
                calls += 1
                try:
                    raw_output = await operation(feedback)
                    return validate(raw_output)
                except InvalidModelOutput as error:
                    if repairs >= max_repairs or calls >= max_calls:
                        raise DomainError(
                            ErrorCode.MODEL_OUTPUT_INVALID,
                            "La salida del modelo siguió siendo inválida después de la reparación disponible.",
                            action=request.action,
                        ) from error
                    repairs += 1
                    feedback = self._repair_feedback(stage, error)

        try:
            async with asyncio.timeout(self.settings.execution_timeout_seconds):
                if max_calls < 2:
                    raise DomainError(
                        ErrorCode.INTERNAL_ERROR,
                        "max_model_calls_per_execution debe permitir las dos llamadas normales.",
                        action=request.action,
                    )
                validate_request_limits(request, self.settings)

                controls: ParsedInstructions = await call_with_repair(
                    "extraction",
                    lambda feedback: self.llm_client.extract(
                        request.action,
                        request.instructions,
                        repair_feedback=feedback,
                    ),
                    lambda parsed: validate_instructions(
                        request.action,
                        request.instructions,
                        parsed,
                        self.settings,
                    ),
                )

                section = await self.context_client.get_section(
                    request.book_id,
                    request.section_id,
                )
                section = validate_section(section, request, self.settings)

                result: PublicSuccess = await call_with_repair(
                    "generation",
                    lambda feedback: self.llm_client.generate(
                        request.action,
                        controls,
                        section,
                        repair_feedback=feedback,
                        original_instructions=request.instructions,
                    ),
                    lambda envelope: validate_generation(
                        request.action,
                        envelope,
                        controls,
                        section,
                    ),
                )
            log_completion("SUCCESS")
            return result
        except DomainError as error:
            if error.action is None:
                error.action = request.action
            log_completion(error.code.value)
            raise
        except TimeoutError as error:
            timeout_error = DomainError(
                ErrorCode.EXECUTION_TIMEOUT,
                "La ejecución excedió el tiempo total configurado.",
                action=request.action,
            )
            log_completion(timeout_error.code.value)
            raise timeout_error from error
        except Exception:
            log_completion(ErrorCode.INTERNAL_ERROR.value)
            raise

    @staticmethod
    def _repair_feedback(stage: str, error: InvalidModelOutput) -> str:
        issues = error.issues or ("Corrige la salida para que cumpla el esquema y las validaciones.",)
        limited_issues = "\n".join(f"- {issue[:300]}" for issue in issues[:12])
        if stage == "extraction":
            constraint = (
                "Reinterpreta solo el texto original de instructions. Conserva los controles "
                "explícitos, deja null lo ausente e incluye citas literales exactas."
            )
        else:
            constraint = (
                "Corrige únicamente el borrador para respetar la misma acción, controles y "
                "sección; no cambies fuentes ni agregues conocimiento externo."
            )
        return f"{constraint}\nProblemas concretos:\n{limited_issues}"
