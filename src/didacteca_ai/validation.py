"""Validaciones cruzadas de controles, contexto y borradores del modelo."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from didacteca_ai.errors import (
    DomainError,
    ErrorCode,
    ErrorDetails,
    InvalidModelOutput,
)
from didacteca_ai.math_format import math_spans
from didacteca_ai.schemas import (
    ActivityDraft,
    ActivityGenerationEnvelope,
    ActivitySuccess,
    AnyGenerationEnvelope,
    BookSection,
    ChatDraft,
    ChatGenerationEnvelope,
    ChatSuccess,
    ExecuteRequest,
    ParsedInstructions,
    PublicSuccess,
    QuizDraft,
    QuizGenerationEnvelope,
    QuizSuccess,
)
from didacteca_ai.rubric import render_expected_result
from didacteca_ai.source_reference import source_passages


_ACTION_FIELDS: dict[str, tuple[str, ...]] = {
    "chat": ("task",),
    "quiz": ("task", "audience", "question_count", "difficulty"),
    "activity": ("task", "audience", "activity_type", "modality", "duration_minutes"),
}

_SAFE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_REQUEST: "La solicitud no cumple el contrato de entrada.",
    ErrorCode.MISSING_INPUT_FIELDS: "Completa los campos requeridos de la solicitud.",
    ErrorCode.MISSING_PARAMETERS: "Completa los controles pedagógicos que faltan en instructions.",
    ErrorCode.AMBIGUOUS_INSTRUCTIONS: "Aclara los valores ambiguos de instructions.",
    ErrorCode.CONFLICTING_INSTRUCTIONS: "Resuelve las instrucciones contradictorias.",
    ErrorCode.INVALID_PARAMETERS: "Corrige los controles que están fuera del contrato permitido.",
    ErrorCode.UNFEASIBLE_ACTIVITY: "Reformula la actividad para que sea realizable con estos límites.",
    ErrorCode.REQUEST_RULE_CONFLICT: "La solicitud contradice las reglas de la capacidad seleccionada.",
    ErrorCode.CONTENT_EMPTY: "La sección seleccionada no contiene texto utilizable.",
    ErrorCode.CONTENT_INSUFFICIENT: "El contenido de la sección no basta para completar esta solicitud.",
}

_GENERATION_ERROR_CODES: dict[str, ErrorCode] = {
    "MISSING_PARAMETERS": ErrorCode.MISSING_PARAMETERS,
    "AMBIGUOUS_INSTRUCTIONS": ErrorCode.AMBIGUOUS_INSTRUCTIONS,
    "CONFLICTING_INSTRUCTIONS": ErrorCode.CONFLICTING_INSTRUCTIONS,
    "INVALID_PARAMETERS": ErrorCode.INVALID_PARAMETERS,
    "UNFEASIBLE_ACTIVITY": ErrorCode.UNFEASIBLE_ACTIVITY,
    "REQUEST_RULE_CONFLICT": ErrorCode.REQUEST_RULE_CONFLICT,
    "CONTENT_EMPTY": ErrorCode.CONTENT_EMPTY,
    "CONTENT_INSUFFICIENT": ErrorCode.CONTENT_INSUFFICIENT,
}

_ERROR_PRIORITY: tuple[ErrorCode, ...] = (
    ErrorCode.REQUEST_RULE_CONFLICT,
    ErrorCode.CONFLICTING_INSTRUCTIONS,
    ErrorCode.AMBIGUOUS_INSTRUCTIONS,
    ErrorCode.UNFEASIBLE_ACTIVITY,
    ErrorCode.INVALID_PARAMETERS,
    ErrorCode.MISSING_PARAMETERS,
    ErrorCode.CONTENT_EMPTY,
    ErrorCode.CONTENT_INSUFFICIENT,
)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _pydantic_issues(error: ValidationError) -> tuple[str, ...]:
    """Return locations and fixed validation messages without rejected values."""

    issues: list[str] = []
    for item in error.errors()[:12]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "output"
        issues.append(f"{location}: {item.get('msg', 'valor inválido')}")
    return tuple(issues) or ("La salida no cumple el esquema interno.",)


def _model_data(value: Any, stage: str) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return dict(value)
    raise InvalidModelOutput(stage, "El modelo no devolvió un objeto estructurado.", issues=("Se esperaba un objeto JSON.",))


def _validate_math_strings(value: Any, path: str) -> None:
    """Valida únicamente la notación matemática delimitada en una salida generada."""

    if isinstance(value, str):
        try:
            math_spans(value)
        except ValueError as error:
            raise InvalidModelOutput(
                "generation",
                "La salida contiene notación matemática delimitada inválida.",
                issues=(f"{path}: {error}",),
            ) from error
        return

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_math_strings(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_math_strings(item, f"{path}[{index}]")


def validate_request_limits(request: ExecuteRequest, settings: Any) -> None:
    """Aplica límites configurables antes de consumir Context Service u OpenAI."""

    invalid: list[str] = []
    constraints: list[str] = []
    for field in ("book_id", "section_id"):
        value = getattr(request, field)
        if len(value) > settings.max_identifier_chars:
            invalid.append(field)
            constraints.append(
                f"{field} no puede superar {settings.max_identifier_chars} caracteres."
            )
    if len(request.instructions) > settings.max_instructions_chars:
        invalid.append("instructions")
        constraints.append(
            f"instructions no puede superar {settings.max_instructions_chars} caracteres."
        )
    if invalid:
        raise DomainError(
            ErrorCode.INVALID_REQUEST,
            "La solicitud supera los límites de entrada permitidos.",
            action=request.action,
            details=ErrorDetails(
                missing_fields=[],
                conflicting_fields=[],
                invalid_fields=_unique(invalid),
                constraints=constraints,
            ),
        )


def _instruction_problem_details(
    parsed: ParsedInstructions,
) -> tuple[list[ErrorCode], list[str], list[str], list[str]]:
    codes: list[ErrorCode] = []
    conflicting: list[str] = []
    invalid: list[str] = []
    constraints: list[str] = []
    for problem in parsed.problems:
        code = {
            "ambiguous": ErrorCode.AMBIGUOUS_INSTRUCTIONS,
            "conflicting": ErrorCode.CONFLICTING_INSTRUCTIONS,
            "invalid": ErrorCode.INVALID_PARAMETERS,
            "unfeasible": ErrorCode.UNFEASIBLE_ACTIVITY,
            "rule_conflict": ErrorCode.REQUEST_RULE_CONFLICT,
        }[problem.kind]
        codes.append(code)
        fields = list(problem.fields) or ["instructions"]
        if problem.kind in {"ambiguous", "conflicting", "rule_conflict"}:
            conflicting.extend(fields)
            if problem.kind == "rule_conflict":
                constraints.append(
                    "Conserva la acción y la fuente seleccionadas; no solicites anular las reglas del servicio."
                )
            else:
                constraints.append(
                    "Aclara en instructions un único valor para: " + ", ".join(fields) + "."
                )
        elif problem.kind == "invalid":
            invalid.extend(fields)
            constraints.append(
                "Corrige en instructions los valores de: " + ", ".join(fields) + "."
            )
        else:
            constraints.append(
                "Ajusta la solicitud para que sea realizable dentro de los límites indicados."
            )
    return codes, conflicting, invalid, constraints


def validate_instructions(
    action: str,
    instructions: str,
    parsed_value: Any,
    settings: Any,
) -> ParsedInstructions:
    """Valida tipos, evidencia literal y controles obligatorios por capacidad."""

    try:
        parsed = ParsedInstructions.model_validate(_model_data(parsed_value, "extraction"))
    except InvalidModelOutput:
        raise
    except ValidationError as error:
        raise InvalidModelOutput(
            "extraction",
            "La extracción no cumple el esquema interno.",
            issues=_pydantic_issues(error),
        ) from error

    for item in parsed.evidence:
        if item.quote not in instructions:
            raise InvalidModelOutput(
                "extraction",
                "La extracción citó texto que no aparece literalmente en instructions.",
                issues=(f"La evidencia de {item.field} debe ser literal.",),
            )
    for problem in parsed.problems:
        if any(quote not in instructions for quote in problem.evidence):
            raise InvalidModelOutput(
                "extraction",
                "La extracción citó evidencia de problema que no aparece en instructions.",
                issues=("La evidencia de los problemas debe ser literal.",),
            )

    codes, conflicting, invalid, constraints = _instruction_problem_details(parsed)
    missing: list[str] = []
    for field in _ACTION_FIELDS[action]:
        if field == "task":
            continue
        if getattr(parsed, field) is None:
            missing.append(field)

    if action == "activity":
        if parsed.modality == "team":
            if parsed.team_size is None:
                missing.append("team_size")
            elif parsed.team_size < 2 or parsed.team_size > settings.max_team_size:
                invalid.append("team_size")
                constraints.append(
                    f"team_size debe ser un entero entre 2 y {settings.max_team_size} para modalidad team."
                )
        elif parsed.modality == "individual" and parsed.team_size is not None:
            invalid.append("team_size")
            constraints.append("team_size solo se usa cuando modality es team.")

        if parsed.duration_minutes is not None and (
            parsed.duration_minutes < 1
            or parsed.duration_minutes > settings.max_activity_minutes
        ):
            invalid.append("duration_minutes")
            constraints.append(
                f"duration_minutes debe ser un entero entre 1 y {settings.max_activity_minutes}."
            )

    if action == "quiz" and parsed.question_count is not None and (
        parsed.question_count < 1
        or parsed.question_count > settings.max_quiz_questions
    ):
        invalid.append("question_count")
        constraints.append(
            f"question_count debe ser un entero entre 1 y {settings.max_quiz_questions}."
        )

    codes.extend(
        [ErrorCode.INVALID_PARAMETERS] if invalid and ErrorCode.INVALID_PARAMETERS not in codes else []
    )
    codes.extend(
        [ErrorCode.MISSING_PARAMETERS] if missing else []
    )

    if codes:
        selected = next(code for code in _ERROR_PRIORITY if code in codes)
        if not constraints:
            constraints.append(
                "Completa los controles pedagógicos requeridos para la acción seleccionada."
            )
        if selected == ErrorCode.MISSING_PARAMETERS:
            message = _SAFE_MESSAGES[selected]
        else:
            message = _SAFE_MESSAGES[selected]
        raise DomainError(
            selected,
            message,
            action=action,  # type: ignore[arg-type]
            details=ErrorDetails(
                missing_fields=_unique(missing),
                conflicting_fields=_unique(conflicting),
                invalid_fields=_unique(invalid),
                constraints=_unique(constraints),
            ),
        )

    return parsed


def validate_section(
    section_value: Any,
    request: ExecuteRequest,
    settings: Any,
) -> BookSection:
    """Comprueba el contrato, la identidad exacta y el tamaño del contexto."""

    try:
        section = BookSection.model_validate(_model_data(section_value, "generation"))
    except (ValidationError, InvalidModelOutput) as error:
        raise DomainError(
            ErrorCode.CONTEXT_INVALID_RESPONSE,
            "El Context Service devolvió una sección con formato inválido.",
            action=request.action,
        ) from error

    if section.book_id != request.book_id or section.section_id != request.section_id:
        raise DomainError(
            ErrorCode.CONTEXT_INVALID_RESPONSE,
            "El Context Service devolvió identificadores distintos a los solicitados.",
            action=request.action,
        )
    if not section.content.strip():
        raise DomainError(
            ErrorCode.CONTENT_EMPTY,
            _SAFE_MESSAGES[ErrorCode.CONTENT_EMPTY],
            action=request.action,
        )
    if len(section.content) > settings.max_context_chars:
        raise DomainError(
            ErrorCode.CONTEXT_TOO_LARGE,
            "La sección supera el límite de contexto configurado.",
            action=request.action,
            details=ErrorDetails(
                missing_fields=[],
                conflicting_fields=[],
                invalid_fields=[],
                constraints=[
                    f"content debe tener como máximo {settings.max_context_chars} caracteres."
                ],
            ),
        )
    return section


def _envelope_model(action: str) -> type[BaseModel]:
    return {
        "chat": ChatGenerationEnvelope,
        "quiz": QuizGenerationEnvelope,
        "activity": ActivityGenerationEnvelope,
    }[action]


def _generation_error(envelope: AnyGenerationEnvelope, action: str) -> DomainError:
    problems = envelope.problems
    codes = [_GENERATION_ERROR_CODES[item.code] for item in problems]
    if envelope.outcome == "insufficient_context":
        chosen = ErrorCode.CONTENT_INSUFFICIENT
    elif envelope.outcome == "rejected":
        chosen = ErrorCode.REQUEST_RULE_CONFLICT
    else:
        chosen = next((code for code in _ERROR_PRIORITY if code in codes), ErrorCode.INVALID_PARAMETERS)

    missing = [field for item in problems for field in item.missing_fields]
    conflicting = [field for item in problems for field in item.conflicting_fields]
    invalid = [field for item in problems for field in item.invalid_fields]
    constraints = [
        _safe_model_constraint(value)
        for problem in problems
        for value in problem.constraints
    ]
    constraints = _unique([value for value in constraints if value])[:8]
    if not constraints:
        constraints = [
            "Resuelve los controles indicados antes de volver a generar el recurso."
        ]
        if chosen == ErrorCode.CONTENT_INSUFFICIENT:
            constraints = ["La solicitud debe poder sustentarse con la sección recuperada."]
        elif chosen == ErrorCode.REQUEST_RULE_CONFLICT:
            constraints = ["Conserva la acción y la fuente solicitadas, y usa solo el contenido recuperado."]
        elif missing or conflicting or invalid:
            constraints = [
                "Revisa los campos señalados y envía de nuevo los cuatro campos de la solicitud."
            ]
    return DomainError(
        chosen,
        _SAFE_MESSAGES.get(chosen, "No se pudo completar la solicitud."),
        action=action,  # type: ignore[arg-type]
        details=ErrorDetails(
            missing_fields=_unique(missing),
            conflicting_fields=_unique(conflicting),
            invalid_fields=_unique(invalid),
            constraints=constraints,
        ),
    )


def _safe_model_constraint(value: str) -> str:
    """Limita y redacta texto de aclaración sin reflejar credenciales obvias."""

    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(
        r"(?i)\bBearer\s+[^\s,;]+",
        "Bearer [redactado]",
        text,
    )
    text = re.sub(
        r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b",
        "[credencial redactada]",
        text,
    )
    text = re.sub(
        r"(?i)\b([a-z0-9_]*(?:api[_ -]?key|token|password|contraseña|clave))\s*[:=]\s*[^\s,;]+",
        r"\1=[redactado]",
        text,
    )
    text = re.sub(r"(?i)\bhttps?://[^\s,;]+", "[URL omitida]", text)
    return text[:300]


def _check_source_references(source_ids: list[int], content: str, field: str) -> None:
    passage_count = len(source_passages(content))
    for source_id in source_ids:
        if source_id < 1 or source_id > passage_count:
            raise InvalidModelOutput(
                "generation",
                "El borrador referencia un fragmento que no existe en la sección.",
                issues=(
                    f"El source_id de {field} debe ser un entero entre 1 y {passage_count}; "
                    "usa solo los source_id incluidos en source_passages.",
                ),
            )


def _normalized_question(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _public_success(model: type[BaseModel], payload: dict[str, Any]) -> PublicSuccess:
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise InvalidModelOutput(
            "generation",
            "El resultado proyectado no cumple el esquema público.",
            issues=_pydantic_issues(error),
        ) from error


def _activity_mode_is_explicit(draft: ActivityDraft, controls: ParsedInstructions) -> bool:
    text = " ".join(draft.instructions).casefold()
    if controls.modality == "individual":
        return re.search(r"\bindividual(?:es|mente)?\b", text) is not None
    if controls.modality != "team" or controls.team_size is None:
        return False

    if re.search(r"\b(?:equipo|equipos|grupo|grupos)\b", text) is None:
        return False
    number = str(controls.team_size)
    spanish_numbers = {
        2: "dos",
        3: "tres",
        4: "cuatro",
        5: "cinco",
        6: "seis",
        7: "siete",
        8: "ocho",
    }
    number_options = [number]
    if controls.team_size in spanish_numbers:
        number_options.append(spanish_numbers[controls.team_size])
    alternatives = "|".join(re.escape(value) for value in number_options)
    size_patterns = (
        rf"\b(?:{alternatives})\s+(?:integrantes?|personas?)\b",
        rf"\b(?:equipos?|grupos?)\s+de\s+(?:{alternatives})\b",
    )
    if not any(re.search(pattern, text) for pattern in size_patterns):
        return False
    return True


def validate_generation(
    action: str,
    envelope_value: Any,
    controls: ParsedInstructions,
    section: BookSection,
) -> PublicSuccess:
    """Revalida el sobre de generación y proyecta solo el esquema público."""

    try:
        envelope = _envelope_model(action).model_validate(
            _model_data(envelope_value, "generation")
        )
    except InvalidModelOutput:
        raise
    except ValidationError as error:
        raise InvalidModelOutput(
            "generation",
            "La generación no cumple el esquema interno.",
            issues=_pydantic_issues(error),
        ) from error

    if envelope.outcome != "success":
        raise _generation_error(envelope, action)
    if envelope.limitations:
        raise InvalidModelOutput(
            "generation",
            "Un resultado exitoso debe tener limitations vacío; las limitaciones bloqueantes usan otro outcome.",
            issues=(
                "Deja limitations vacío y comunica avisos no bloqueantes en un campo público existente.",
            ),
        )
    draft = envelope.result
    _validate_math_strings(draft, "result")
    if action == "chat":
        assert isinstance(draft, ChatDraft)
        _check_source_references(
            [item.source_id for item in draft.evidence], section.content, "answer"
        )
        return _public_success(ChatSuccess, {"action": "chat", "answer": draft.answer})

    if action == "quiz":
        assert isinstance(draft, QuizDraft)
        if len(draft.questions) != controls.question_count:
            raise InvalidModelOutput(
                "generation",
                "El número de preguntas no coincide con el solicitado.",
                issues=(f"Se requieren exactamente {controls.question_count} preguntas.",),
            )
        normalized_questions = [_normalized_question(item.question) for item in draft.questions]
        if len(set(normalized_questions)) != len(normalized_questions):
            raise InvalidModelOutput(
                "generation",
                "El quiz repite preguntas.",
                issues=("Cada pregunta debe ser distinta tras normalizar espacios y mayúsculas.",),
            )
        for index, question in enumerate(draft.questions, start=1):
            _check_source_references(
                [item.source_id for item in question.evidence],
                section.content,
                f"questions[{index}]",
            )
        return _public_success(
            QuizSuccess,
            {
                "action": "quiz",
                "title": draft.title,
                "instructions": draft.instructions,
                "questions": [
                    {
                        "question": question.question,
                        "options": question.options,
                        "correct_answer": question.correct_answer,
                        "explanation": question.explanation,
                    }
                    for question in draft.questions
                ],
            }
        )

    assert isinstance(draft, ActivityDraft)
    if draft.estimated_time_minutes != controls.duration_minutes:
        raise InvalidModelOutput(
            "generation",
            "La duración devuelta no coincide con el presupuesto solicitado.",
            issues=(f"estimated_time_minutes debe ser {controls.duration_minutes}.",),
        )
    if not _activity_mode_is_explicit(draft, controls):
        if controls.modality == "individual":
            mode_issue = "Incluye literalmente 'individualmente' en los pasos de la actividad."
        else:
            mode_issue = (
                f"Incluye literalmente 'En equipos de {controls.team_size} integrantes' "
                "en los pasos de la actividad."
            )
        raise InvalidModelOutput(
            "generation",
            "Las instrucciones no expresan la modalidad y el tamaño de equipo solicitados.",
            issues=(mode_issue,),
        )
    if controls.activity_type == "evaluativa" and draft.rubric is None:
        raise InvalidModelOutput(
            "generation",
            "La actividad evaluativa requiere una rúbrica interna válida.",
            issues=("Incluye una rúbrica con puntajes máximos que sumen 10.",),
        )
    if controls.activity_type != "evaluativa" and draft.rubric is not None:
        raise InvalidModelOutput(
            "generation",
            "Solo las actividades evaluativas reciben rúbrica en esta versión.",
            issues=("Devuelve rubric como null para los demás tipos de actividad.",),
        )
    _check_source_references(
        [item.source_id for item in draft.evidence if item.target == "objective"],
        section.content,
        "objective",
    )
    _check_source_references(
        [item.source_id for item in draft.evidence if item.target == "instructions"],
        section.content,
        "instructions",
    )
    try:
        expected_result = render_expected_result(draft.expected_product, draft.rubric)
    except ValidationError as error:
        raise InvalidModelOutput(
            "generation",
            "No se pudo validar la rúbrica o el producto esperado.",
            issues=_pydantic_issues(error),
        ) from error
    except (TypeError, ValueError) as error:
        raise InvalidModelOutput(
            "generation",
            "No se pudo validar la rúbrica o el producto esperado.",
            issues=(str(error),),
        ) from error
    _validate_math_strings(expected_result, "result.expected_result")
    return _public_success(
        ActivitySuccess,
        {
            "action": "activity",
            "title": draft.title,
            "objective": draft.objective,
            "instructions": draft.instructions,
            "estimated_time_minutes": draft.estimated_time_minutes,
            "expected_result": expected_result,
        }
    )
