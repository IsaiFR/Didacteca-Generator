"""Cliente asíncrono de OpenAI Responses con salidas Pydantic estrictas."""

from __future__ import annotations

import asyncio
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Literal, Mapping, TypeVar

import httpx
import openai
from openai import AsyncOpenAI
from openai.resources.responses.responses import _type_to_text_format_param
from pydantic import BaseModel, ValidationError

from .config import Settings
from .errors import DomainError, ErrorCode, InvalidModelOutput
from .prompts import (
    extraction_input,
    extraction_system_prompt,
    generation_input,
    generation_system_prompt,
)
from .schemas import (
    Action,
    ActivityGenerationEnvelope,
    AnyGenerationEnvelope,
    BookSection,
    ChatGenerationEnvelope,
    InstructionEvidence,
    ParsedInstructions,
    ParsedInstructionsWire,
    QuizGenerationEnvelope,
)


_ENVELOPE_BY_ACTION: dict[Action, type[BaseModel]] = {
    "chat": ChatGenerationEnvelope,
    "quiz": QuizGenerationEnvelope,
    "activity": ActivityGenerationEnvelope,
}
_QUOTA_ERROR_CODES = frozenset(
    {"insufficient_quota", "billing_hard_limit_reached", "quota_exceeded"}
)
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_Stage = Literal["extraction", "generation"]


@dataclass(frozen=True)
class _UsageMetrics:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient:
    """Realiza extracción y generación; el servicio dueño controla reparaciones."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client
        self._metrics_var: ContextVar[_UsageMetrics | None] = ContextVar(
            f"didacteca_llm_usage_{id(self)}", default=None
        )

    @property
    def metrics(self) -> Mapping[str, int]:
        """Uso de tokens de la tarea asíncrona actual, sin guardar contenido."""

        usage = self._metrics_var.get() or _UsageMetrics()
        return {
            "calls": usage.calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        }

    async def extract(
        self,
        action: Action,
        instructions: str,
        *,
        repair_feedback: str | None = None,
    ) -> ParsedInstructions:
        """Interpreta controles explícitos sin recibir contenido del libro."""

        input_messages = extraction_input(action, instructions)
        if repair_feedback:
            input_messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {"kind": "validation_feedback", "feedback": repair_feedback},
                        ensure_ascii=False,
                    ),
                }
            )
        parsed: ParsedInstructionsWire = await self._parse(
            stage="extraction",
            action=action,
            model=ParsedInstructionsWire,
            system_prompt=extraction_system_prompt(action),
            input_messages=input_messages,
            max_output_tokens=self._settings.extraction_max_output_tokens,
        )
        return self._normalize_extraction(parsed)

    async def generate(
        self,
        action: Action,
        controls: ParsedInstructions,
        section: BookSection,
        *,
        repair_feedback: str | None = None,
        original_instructions: str | None = None,
    ) -> AnyGenerationEnvelope:
        """Genera con esquema de acción y referencia ya recuperada."""

        model = _ENVELOPE_BY_ACTION.get(action)
        if model is None:
            raise DomainError(
                ErrorCode.UNSUPPORTED_ACTION,
                "La acción solicitada no está implementada.",
            )
        parsed = await self._parse(
            stage="generation",
            action=action,
            model=model,
            system_prompt=generation_system_prompt(action),
            input_messages=generation_input(
                action,
                controls,
                section,
                repair_feedback=repair_feedback,
                original_instructions=original_instructions,
            ),
            max_output_tokens=self._settings.generation_max_output_tokens,
        )
        return model.model_validate(parsed, strict=True)  # type: ignore[return-value]

    async def _parse(
        self,
        *,
        stage: _Stage,
        action: Action,
        model: type[_ModelT],
        system_prompt: str,
        input_messages: list[dict[str, str]],
        max_output_tokens: int,
    ) -> _ModelT:
        self._check_schema(model, action)
        client = self._get_client(action)
        self._add_usage(calls=1)

        try:
            async with asyncio.timeout(self._settings.ai_timeout_seconds):
                response = await client.responses.parse(
                    model=self._settings.openai_model,
                    instructions=system_prompt,
                    input=input_messages,
                    text_format=model,
                    max_output_tokens=max_output_tokens,
                    timeout=self._settings.ai_timeout_seconds,
                    store=False,
                    truncation="disabled",
                )
        except openai.ContentFilterFinishReasonError as exc:
            raise DomainError(
                ErrorCode.AI_REFUSAL,
                "El proveedor rechazó la solicitud por sus políticas de seguridad.",
                action=action,
            ) from exc
        except openai.LengthFinishReasonError as exc:
            raise InvalidModelOutput(
                stage,
                "La respuesta estructurada quedó incompleta.",
                issues=("Devuelve el objeto completo dentro del esquema solicitado.",),
            ) from exc
        except openai.APITimeoutError as exc:
            raise DomainError(
                ErrorCode.AI_TIMEOUT,
                "OpenAI excedió el tiempo límite de la llamada.",
                action=action,
            ) from exc
        except TimeoutError as exc:
            raise DomainError(
                ErrorCode.AI_TIMEOUT,
                "OpenAI excedió el tiempo límite de la llamada.",
                action=action,
            ) from exc
        except openai.APIStatusError as exc:
            raise self._map_status_error(exc, action) from exc
        except openai.APIConnectionError as exc:
            raise DomainError(
                ErrorCode.AI_UNAVAILABLE,
                "No fue posible conectar con OpenAI.",
                action=action,
            ) from exc
        except openai.APIResponseValidationError as exc:
            raise DomainError(
                ErrorCode.AI_INVALID_RESPONSE,
                "OpenAI devolvió una respuesta incompatible con su protocolo.",
                action=action,
            ) from exc
        except openai.APIError as exc:
            raise DomainError(
                ErrorCode.AI_INVALID_RESPONSE,
                "OpenAI no pudo procesar la respuesta estructurada.",
                action=action,
            ) from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            raise self._invalid_output(stage, exc) from exc

        self._record_response_usage(response)
        status = getattr(response, "status", None)
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None)
            if reason == "content_filter":
                raise DomainError(
                    ErrorCode.AI_REFUSAL,
                    "El proveedor rechazó la solicitud por sus políticas de seguridad.",
                    action=action,
                )
            raise InvalidModelOutput(
                stage,
                "La respuesta estructurada quedó incompleta.",
                issues=("Devuelve el objeto completo dentro del esquema solicitado.",),
            )
        if self._contains_refusal(response):
            raise DomainError(
                ErrorCode.AI_REFUSAL,
                "El proveedor rechazó la solicitud por sus políticas de seguridad.",
                action=action,
            )
        if status != "completed":
            raise DomainError(
                ErrorCode.AI_INVALID_RESPONSE,
                "OpenAI devolvió un estado de respuesta incompatible.",
                action=action,
            )

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise InvalidModelOutput(
                stage,
                "El modelo no produjo un objeto conforme al esquema.",
                issues=("Devuelve un objeto completo conforme al esquema indicado.",),
            )
        try:
            return model.model_validate(parsed, strict=True)
        except ValidationError as exc:
            raise self._invalid_output(stage, exc) from exc

    @staticmethod
    def _normalize_extraction(parsed: ParsedInstructionsWire) -> ParsedInstructions:
        """Convierte controles con citas locales al modelo plano que usa el servicio."""

        data: dict[str, Any] = {}
        evidence: list[InstructionEvidence] = []
        for field in (
            "task",
            "audience",
            "question_count",
            "difficulty",
            "activity_type",
            "modality",
            "duration_minutes",
            "team_size",
        ):
            item = getattr(parsed, field)
            if item is None:
                data[field] = None
                continue
            data[field] = item.value
            evidence.append(InstructionEvidence(field=field, quote=item.quote))

        data["evidence"] = evidence
        data["problems"] = parsed.problems
        try:
            return ParsedInstructions.model_validate(data, strict=True)
        except ValidationError as exc:
            raise LLMClient._invalid_output("extraction", exc) from exc

    def _get_client(self, action: Action) -> Any:
        if self._client is not None:
            return self._client
        secret = self._settings.openai_api_key
        if secret is None:
            raise DomainError(
                ErrorCode.AI_ACCESS_DENIED,
                "OPENAI_API_KEY no está configurada para ejecutar esta capacidad.",
                action=action,
            )
        try:
            self._client = AsyncOpenAI(
                api_key=secret.get_secret_value(),
                base_url="https://api.openai.com/v1",
                timeout=self._settings.ai_timeout_seconds,
                max_retries=0,
            )
        except openai.OpenAIError as exc:
            raise DomainError(
                ErrorCode.AI_ACCESS_DENIED,
                "No se pudo inicializar el cliente de OpenAI con la configuración actual.",
                action=action,
            ) from exc
        return self._client

    @staticmethod
    @lru_cache(maxsize=8)
    def _strict_schema(model: type[BaseModel]) -> bool:
        """Valida localmente la conversión y el nombre que el SDK transmite."""

        wire_format = _type_to_text_format_param(model)
        name = wire_format.get("name")
        schema = wire_format.get("schema")
        return (
            isinstance(name, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) is not None
            and isinstance(schema, dict)
            and schema.get("type") == "object"
            and isinstance(schema.get("properties"), dict)
        )

    def _check_schema(self, model: type[BaseModel], action: Action) -> None:
        try:
            compatible = self._strict_schema(model)
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                ErrorCode.AI_INVALID_RESPONSE,
                "El esquema de salida configurado no es compatible con Structured Outputs.",
                action=action,
            ) from exc
        if not compatible:
            raise DomainError(
                ErrorCode.AI_INVALID_RESPONSE,
                "El esquema de salida o el nombre del formato no es compatible con Structured Outputs.",
                action=action,
            )

    @staticmethod
    def _invalid_output(
        stage: _Stage,
        exc: ValidationError | json.JSONDecodeError,
    ) -> InvalidModelOutput:
        if isinstance(exc, ValidationError):
            safe_errors = exc.errors(include_input=False, include_context=False)[:8]
            issues = tuple(
                LLMClient._format_validation_issue(error) for error in safe_errors
            )
        else:
            issues = ("El texto de salida no es JSON válido.",)
        return InvalidModelOutput(
            stage,
            "La salida del modelo no cumple el esquema estructurado.",
            issues=issues,
        )

    @staticmethod
    def _format_validation_issue(error: Mapping[str, Any]) -> str:
        """Expose only bounded locations, error types and sanitized validator messages."""

        location_parts = error.get("loc", ())
        if not isinstance(location_parts, (tuple, list)):
            location_parts = ()
        location = ".".join(
            LLMClient._safe_validation_text(part, limit=80)
            for part in location_parts
            if isinstance(part, (str, int)) and not isinstance(part, bool)
        )
        error_type = error.get("type", "validation_error")
        if not isinstance(error_type, str):
            error_type = "validation_error"
        message = LLMClient._safe_validation_text(
            error.get("msg", "El valor no cumple la validación."),
            limit=220,
        )
        prefix = f"{location}: " if location else ""
        return f"{prefix}{LLMClient._safe_validation_text(error_type, limit=80)}: {message}"

    @staticmethod
    def _safe_validation_text(value: Any, *, limit: int) -> str:
        """Redact secrets and omit Pydantic input, context, and traceback details."""

        text = str(value)
        text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redactado]", text)
        text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b", "[credencial redactada]", text)
        text = re.sub(
            r"(?i)\b(?:openai[_ -]?api[_ -]?key|api[_ -]?key|authorization|token|password|secret)\s*[:=]\s*[^\s,;]+",
            "[dato sensible redactado]",
            text,
        )
        text = re.sub(r"(?i)https?://[^\s,;]+", "[URL omitida]", text)
        return re.sub(r"\s+", " ", text).strip()[:limit]

    def _add_usage(self, *, calls: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> None:
        current = self._metrics_var.get() or _UsageMetrics()
        self._metrics_var.set(
            replace(
                current,
                calls=current.calls + calls,
                input_tokens=current.input_tokens + input_tokens,
                output_tokens=current.output_tokens + output_tokens,
            )
        )

    def _record_response_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
            input_tokens = 0
        if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
            output_tokens = 0
        self._add_usage(
            input_tokens=max(input_tokens, 0),
            output_tokens=max(output_tokens, 0),
        )

    @staticmethod
    def _contains_refusal(response: Any) -> bool:
        for output in getattr(response, "output", ()) or ():
            for content in getattr(output, "content", ()) or ():
                if getattr(content, "type", None) == "refusal":
                    return True
        return False

    @staticmethod
    def _map_status_error(exc: openai.APIStatusError, action: Action) -> DomainError:
        status = exc.status_code
        if status in (401, 403):
            code = ErrorCode.AI_ACCESS_DENIED
            message = "La credencial no tiene acceso autorizado a OpenAI."
        elif status == 404:
            code = ErrorCode.AI_MODEL_UNAVAILABLE
            message = "El modelo configurado no existe o no está habilitado para la cuenta."
        elif status == 408:
            code = ErrorCode.AI_TIMEOUT
            message = "OpenAI excedió el tiempo límite de la llamada."
        elif status == 429 and LLMClient._provider_error_code(exc) in _QUOTA_ERROR_CODES:
            code = ErrorCode.AI_QUOTA_EXCEEDED
            message = "La cuota de OpenAI está agotada o no está disponible."
        elif status == 429:
            code = ErrorCode.AI_RATE_LIMITED
            message = "OpenAI limitó temporalmente la frecuencia de solicitudes."
        elif status >= 500:
            code = ErrorCode.AI_UNAVAILABLE
            message = "OpenAI no está disponible temporalmente."
        else:
            code = ErrorCode.AI_INVALID_RESPONSE
            message = "OpenAI rechazó la solicitud o devolvió un error de protocolo."
        return DomainError(code, message, action=action)

    @staticmethod
    def _provider_error_code(exc: openai.APIStatusError) -> str | None:
        body = getattr(exc, "body", None)
        if not isinstance(body, dict):
            return None
        error = body.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, str):
                return code
        code = body.get("code")
        return code if isinstance(code, str) else None

    async def aclose(self) -> None:
        """Cierra únicamente el AsyncOpenAI creado por esta instancia."""

        if self._owns_client and self._client is not None:
            await self._client.close()
            self._client = None

