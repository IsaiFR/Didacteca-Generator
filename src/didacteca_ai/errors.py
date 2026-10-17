"""Errores de dominio y formato público uniforme para solicitudes fallidas."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr


Action = Literal["chat", "quiz", "activity"]
ResponseStatus = Literal["needs_clarification", "error"]


class ErrorCode(StrEnum):
    REQUEST_BODY_TOO_LARGE = "REQUEST_BODY_TOO_LARGE"
    REQUEST_BODY_TIMEOUT = "REQUEST_BODY_TIMEOUT"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INVALID_JSON = "INVALID_JSON"
    DUPLICATE_JSON_KEYS = "DUPLICATE_JSON_KEYS"
    REQUEST_RATE_LIMITED = "REQUEST_RATE_LIMITED"
    EXECUTION_CAPACITY_REACHED = "EXECUTION_CAPACITY_REACHED"
    CLIENT_CAPACITY_REACHED = "CLIENT_CAPACITY_REACHED"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    MISSING_INPUT_FIELDS = "MISSING_INPUT_FIELDS"
    MISSING_PARAMETERS = "MISSING_PARAMETERS"
    AMBIGUOUS_INSTRUCTIONS = "AMBIGUOUS_INSTRUCTIONS"
    CONFLICTING_INSTRUCTIONS = "CONFLICTING_INSTRUCTIONS"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    UNFEASIBLE_ACTIVITY = "UNFEASIBLE_ACTIVITY"
    REQUEST_RULE_CONFLICT = "REQUEST_RULE_CONFLICT"
    BOOK_NOT_FOUND = "BOOK_NOT_FOUND"
    SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
    CONTENT_EMPTY = "CONTENT_EMPTY"
    CONTENT_INSUFFICIENT = "CONTENT_INSUFFICIENT"
    CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
    CONTEXT_INVALID_RESPONSE = "CONTEXT_INVALID_RESPONSE"
    CONTEXT_REQUEST_REJECTED = "CONTEXT_REQUEST_REJECTED"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    AI_INVALID_RESPONSE = "AI_INVALID_RESPONSE"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_ACCESS_DENIED = "AI_ACCESS_DENIED"
    AI_QUOTA_EXCEEDED = "AI_QUOTA_EXCEEDED"
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    AI_MODEL_UNAVAILABLE = "AI_MODEL_UNAVAILABLE"
    CONTEXT_TIMEOUT = "CONTEXT_TIMEOUT"
    AI_TIMEOUT = "AI_TIMEOUT"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    AI_REFUSAL = "AI_REFUSAL"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    ACTION_NOT_IMPLEMENTED = "ACTION_NOT_IMPLEMENTED"


_CLARIFICATION_CODES = frozenset(
    {
        ErrorCode.MISSING_INPUT_FIELDS,
        ErrorCode.MISSING_PARAMETERS,
        ErrorCode.AMBIGUOUS_INSTRUCTIONS,
        ErrorCode.CONFLICTING_INSTRUCTIONS,
        ErrorCode.INVALID_PARAMETERS,
        ErrorCode.UNFEASIBLE_ACTIVITY,
    }
)

_HTTP_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.REQUEST_BODY_TOO_LARGE: 413,
    ErrorCode.REQUEST_BODY_TIMEOUT: 408,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.INVALID_JSON: 400,
    ErrorCode.DUPLICATE_JSON_KEYS: 400,
    ErrorCode.REQUEST_RATE_LIMITED: 429,
    ErrorCode.EXECUTION_CAPACITY_REACHED: 503,
    ErrorCode.CLIENT_CAPACITY_REACHED: 503,
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.UNSUPPORTED_ACTION: 422,
    ErrorCode.MISSING_INPUT_FIELDS: 422,
    ErrorCode.MISSING_PARAMETERS: 422,
    ErrorCode.AMBIGUOUS_INSTRUCTIONS: 422,
    ErrorCode.CONFLICTING_INSTRUCTIONS: 422,
    ErrorCode.INVALID_PARAMETERS: 422,
    ErrorCode.UNFEASIBLE_ACTIVITY: 422,
    ErrorCode.REQUEST_RULE_CONFLICT: 422,
    ErrorCode.BOOK_NOT_FOUND: 404,
    ErrorCode.SECTION_NOT_FOUND: 404,
    ErrorCode.CONTENT_EMPTY: 422,
    ErrorCode.CONTENT_INSUFFICIENT: 422,
    ErrorCode.CONTEXT_TOO_LARGE: 422,
    ErrorCode.CONTEXT_INVALID_RESPONSE: 502,
    ErrorCode.CONTEXT_REQUEST_REJECTED: 502,
    ErrorCode.MODEL_OUTPUT_INVALID: 502,
    ErrorCode.AI_INVALID_RESPONSE: 502,
    ErrorCode.CONTEXT_UNAVAILABLE: 503,
    ErrorCode.AI_UNAVAILABLE: 503,
    ErrorCode.AI_ACCESS_DENIED: 503,
    ErrorCode.AI_QUOTA_EXCEEDED: 503,
    ErrorCode.AI_RATE_LIMITED: 503,
    ErrorCode.AI_MODEL_UNAVAILABLE: 503,
    ErrorCode.CONTEXT_TIMEOUT: 504,
    ErrorCode.AI_TIMEOUT: 504,
    ErrorCode.EXECUTION_TIMEOUT: 504,
    ErrorCode.AI_REFUSAL: 422,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.ACTION_NOT_IMPLEMENTED: 501,
}


class ErrorDetails(BaseModel):
    """Los cuatro arreglos que aparecen siempre en ``error.details``."""

    model_config = ConfigDict(strict=True, extra="forbid")

    missing_fields: list[StrictStr]
    conflicting_fields: list[StrictStr]
    invalid_fields: list[StrictStr]
    constraints: list[StrictStr]

    @classmethod
    def empty(cls) -> ErrorDetails:
        return cls(
            missing_fields=[],
            conflicting_fields=[],
            invalid_fields=[],
            constraints=[],
        )


class PublicError(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: ErrorCode
    message: StrictStr
    details: ErrorDetails


class ErrorResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    status: ResponseStatus
    action: Action | None
    error: PublicError


class DomainError(Exception):
    """Fallo de dominio que puede convertirse a una única respuesta HTTP."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        action: Action | None = None,
        details: ErrorDetails | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.action = action
        self.details = details if details is not None else ErrorDetails.empty()
        self.http_status = _HTTP_STATUS_BY_CODE[code]
        self.status: ResponseStatus = (
            "needs_clarification" if code in _CLARIFICATION_CODES else "error"
        )
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            status=self.status,
            action=self.action,
            error=PublicError(
                code=self.code,
                message=self.message,
                details=self.details,
            ),
        )

    def to_payload(self) -> dict[str, object]:
        """Devuelve el objeto JSON listo para ``JSONResponse``."""

        return self.to_response().model_dump(mode="json")


class InvalidModelOutput(Exception):
    """Salida del modelo reparable antes de emitir un error de dominio."""

    def __init__(
        self,
        stage: Literal["extraction", "generation"],
        message: str,
        *,
        issues: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.issues = issues
        super().__init__(message)
