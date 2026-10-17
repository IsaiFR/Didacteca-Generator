from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import ValidationError

from didacteca_ai.errors import (
    DomainError,
    ErrorCode,
    ErrorDetails,
    InvalidModelOutput,
)
from didacteca_ai.schemas import (
    ActivityEvidence,
    ActivityDraft,
    ActivityGenerationEnvelope,
    ActivitySuccess,
    BookSection,
    ChatDraft,
    ChatGenerationEnvelope,
    ChatSuccess,
    ExecuteRequest,
    InstructionEvidence,
    ParsedInstructions,
    ParsedInstructionsWire,
    QuizQuestion,
    QuizQuestionDraft,
    QuizGenerationEnvelope,
    QuizSuccess,
    RubricLevel,
    SectionEvidence,
    Rubric,
)


def _parsed_instructions(**overrides: object) -> ParsedInstructions:
    values: dict[str, object] = {
        "task": "crear preguntas",
        "audience": None,
        "question_count": 3,
        "difficulty": "intermediate",
        "activity_type": None,
        "modality": None,
        "duration_minutes": None,
        "team_size": None,
        "evidence": [
            {"field": "task", "quote": "crear preguntas"},
            {"field": "question_count", "quote": "3 preguntas"},
            {"field": "difficulty", "quote": "intermedia"},
        ],
        "problems": [],
    }
    values.update(overrides)
    return ParsedInstructions.model_validate(values)


def _rubric() -> Rubric:
    return Rubric.model_validate(
        {
            "criteria": [
                {
                    "name": "Razonamiento",
                    "evidence": "Explica los pasos realizados.",
                    "max_points": 2,
                    "levels": [
                        {"score": 2, "descriptor": "Explicación completa."},
                        {"score": 1, "descriptor": "Explicación parcial."},
                        {"score": 0, "descriptor": "Sin evidencia."},
                    ],
                },
                {
                    "name": "Resultado",
                    "evidence": "Presenta una respuesta coherente.",
                    "max_points": 8,
                    "levels": [
                        {"score": score, "descriptor": f"Nivel {score}."}
                        for score in range(8, -1, -1)
                    ],
                },
            ]
        }
    )


def test_execute_request_accepts_exact_four_fields_and_rejects_extras() -> None:
    request = ExecuteRequest.model_validate(
        {
            "action": "chat",
            "book_id": "book_001",
            "section_id": "section_04",
            "instructions": "Explica este procedimiento.",
        }
    )
    assert request.action == "chat"
    assert set(request.model_dump()) == {
        "action",
        "book_id",
        "section_id",
        "instructions",
    }

    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(
            {
                **request.model_dump(),
                "audience": "secundaria",
            }
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("action", 1),
        ("book_id", 12),
        ("section_id", False),
        ("instructions", {"question": "hola"}),
    ],
)
def test_execute_request_rejects_coercion(field: str, value: object) -> None:
    request: dict[str, object] = {
        "action": "chat",
        "book_id": "book_001",
        "section_id": "section_04",
        "instructions": "Explica este procedimiento.",
    }
    request[field] = value
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(request)


@pytest.mark.parametrize("field", ["book_id", "section_id", "instructions"])
def test_execute_request_rejects_blank_required_text(field: str) -> None:
    request: dict[str, object] = {
        "action": "chat",
        "book_id": "book_001",
        "section_id": "section_04",
        "instructions": "Explica este procedimiento.",
    }
    request[field] = "   "
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(request)


def test_public_success_models_keep_the_pdf_field_sets() -> None:
    chat = ChatSuccess(action="chat", answer="Respuesta.")
    quiz = QuizSuccess(
        action="quiz",
        title="Quiz",
        instructions="Elige una opción.",
        questions=[
            QuizQuestion(
                question="¿Cuánto es 2 + 2?",
                options=["4", "3", "5", "6"],
                correct_answer="4",
                explanation="La suma es cuatro.",
            )
        ],
    )
    activity = ActivitySuccess(
        action="activity",
        title="Actividad",
        objective="Practicar.",
        instructions=["Resuelve el ejercicio."],
        estimated_time_minutes=20,
        expected_result="Una solución explicada.",
    )

    assert set(chat.model_dump()) == {"action", "answer"}
    assert set(quiz.model_dump()) == {"action", "title", "instructions", "questions"}
    assert set(quiz.questions[0].model_dump()) == {
        "question",
        "options",
        "correct_answer",
        "explanation",
    }
    assert set(activity.model_dump()) == {
        "action",
        "title",
        "objective",
        "instructions",
        "estimated_time_minutes",
        "expected_result",
    }


def test_public_quiz_question_requires_four_distinct_options_and_exact_key() -> None:
    base = {
        "question": "¿Cuál es la respuesta?",
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
        "explanation": "Porque corresponde.",
    }
    with pytest.raises(ValidationError):
        QuizQuestion.model_validate({**base, "options": ["A", "a", "C", "D"]})
    with pytest.raises(ValidationError):
        QuizQuestion.model_validate({**base, "correct_answer": "a"})


def test_book_section_ignores_extra_service_properties_but_keeps_types_strict() -> None:
    section = BookSection.model_validate(
        {
            "book_id": "book_001",
            "section_id": "section_04",
            "title": "Sistemas de ecuaciones",
            "content": "Contenido recuperado.",
            "metadata": {"source": "provided-service"},
        }
    )
    assert set(section.model_dump()) == {"book_id", "section_id", "title", "content"}
    with pytest.raises(ValidationError):
        BookSection.model_validate(
            {
                "book_id": "book_001",
                "section_id": "section_04",
                "title": "Título",
                "content": 3,
            }
        )


def test_parsed_instructions_require_nullable_controls_and_literal_evidence() -> None:
    parsed = _parsed_instructions()
    assert parsed.audience is None
    assert parsed.activity_type is None

    with pytest.raises(ValidationError):
        _parsed_instructions(question_count=True)
    with pytest.raises(ValidationError):
        _parsed_instructions(evidence=[{"field": "task", "quote": "crear preguntas"}])


def test_parsed_instructions_problem_shape_is_explicit() -> None:
    parsed = _parsed_instructions(
        question_count=None,
        difficulty=None,
        evidence=[{"field": "task", "quote": "crear preguntas"}],
        problems=[
            {
                "kind": "ambiguous",
                "message": "Hay dos cantidades posibles.",
                "fields": ["question_count"],
                "evidence": ["5 o 10 preguntas"],
            }
        ],
    )
    assert parsed.problems[0].fields == ["question_count"]


def test_parsed_instructions_wire_requires_quoted_values_and_strict_nullable_controls() -> None:
    base: dict[str, object] = {
        "task": {"value": "crear preguntas", "quote": "crear preguntas"},
        "audience": None,
        "question_count": {"value": 5, "quote": "cinco preguntas"},
        "difficulty": {"value": "intermediate", "quote": "intermedia"},
        "activity_type": None,
        "modality": None,
        "duration_minutes": None,
        "team_size": None,
        "problems": [],
    }
    parsed = ParsedInstructionsWire.model_validate(base)
    assert parsed.task.value == "crear preguntas"
    assert parsed.question_count is not None
    assert parsed.question_count.value == 5
    assert "evidence" not in parsed.model_dump()

    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate(
            {**base, "task": {"value": "crear preguntas"}}
        )
    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate(
            {**base, "question_count": {"value": True, "quote": "cinco preguntas"}}
        )
    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate(
            {**base, "audience": {"value": 12, "quote": "estudiantes"}}
        )
    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate(
            {**base, "difficulty": {"value": "medium", "quote": "intermedia"}}
        )
    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate(
            {key: value for key, value in base.items() if key != "audience"}
        )
    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate({**base, "unrecognized": "extra"})
    with pytest.raises(ValidationError):
        ParsedInstructionsWire.model_validate(
            {**base, "question_count": {"value": 5, "quote": "cinco preguntas", "extra": True}}
        )


@pytest.mark.parametrize(
    "make_invalid",
    [
        lambda: ChatSuccess(action="chat", answer="   "),
        lambda: InstructionEvidence(field="task", quote="\n\t"),
        lambda: RubricLevel(score=0, descriptor="  "),
        lambda: _parsed_instructions(task="\t"),
    ],
)
def test_nonempty_text_rejects_whitespace_only_values(
    make_invalid: Callable[[], object],
) -> None:
    with pytest.raises(ValidationError):
        make_invalid()


def test_nonempty_text_rejects_nul_but_allows_normal_line_breaks_and_tabs() -> None:
    with pytest.raises(ValidationError):
        ChatSuccess(action="chat", answer="Texto con NUL\x00 en medio.")

    result = ChatSuccess(
        action="chat",
        answer="Primera línea.\nSegunda línea\tcon tabulación.\rCierre.",
    )
    assert "\n" in result.answer
    assert "\t" in result.answer
    assert "\r" in result.answer


def test_draft_schemas_keep_internal_evidence_out_of_public_success() -> None:
    chat = ChatDraft(answer="Respuesta.", evidence=[{"source_id": 1}])
    question = QuizQuestionDraft(
        question="¿Cuánto es 2 + 2?",
        options=["4", "3", "5", "6"],
        correct_answer="4",
        explanation="La suma es cuatro.",
        evidence=[{"source_id": 1}],
    )
    assert chat.evidence[0].source_id == 1
    assert len(question.evidence) == 1
    assert "evidence" not in ChatSuccess(action="chat", answer=chat.answer).model_dump()


def test_rubric_has_ten_points_with_complete_descending_integer_levels() -> None:
    rubric = _rubric()
    assert sum(item.max_points for item in rubric.criteria) == 10

    with pytest.raises(ValidationError):
        Rubric.model_validate(
            {
                "criteria": [
                    {
                        "name": "A",
                        "evidence": "Evidencia.",
                        "max_points": True,
                        "levels": [
                            {"score": 1, "descriptor": "Sí."},
                            {"score": 0, "descriptor": "No."},
                        ],
                    },
                    {
                        "name": "B",
                        "evidence": "Evidencia.",
                        "max_points": 9,
                        "levels": [
                            {"score": score, "descriptor": f"Nivel {score}."}
                            for score in range(9, -1, -1)
                        ],
                    },
                ]
            }
        )

    with pytest.raises(ValidationError):
        Rubric.model_validate(
            {
                "criteria": [
                    {
                        "name": "Rango excesivo",
                        "evidence": "Evidencia observable.",
                        "max_points": 10**30,
                        "levels": [
                            {"score": 10, "descriptor": "Nivel máximo."},
                            {"score": 0, "descriptor": "Sin evidencia."},
                        ],
                    }
                ]
            }
        )

    invalid_levels = _rubric().model_dump()
    invalid_levels["criteria"][0]["levels"][1]["score"] = 0
    with pytest.raises(ValidationError):
        Rubric.model_validate(invalid_levels)


def test_activity_draft_requires_objective_and_step_evidence() -> None:
    draft = ActivityDraft.model_validate(
        {
            "title": "Actividad",
            "objective": "Aplicar el método.",
            "instructions": ["Resuelve", "Comprueba"],
            "estimated_time_minutes": 20,
            "expected_product": "Solución explicada.",
            "rubric": None,
            "evidence": [
                {"target": "objective", "source_id": 1},
                {"target": "instructions", "source_id": 1},
            ],
        }
    )
    assert draft.rubric is None

    with pytest.raises(ValidationError):
        ActivityDraft.model_validate(
            {
                "title": "Actividad",
                "objective": "Aplicar el método.",
                "instructions": ["Resuelve"],
                "estimated_time_minutes": 20,
                "expected_product": "Solución explicada.",
                "rubric": None,
                "evidence": [{"target": "objective", "source_id": 1}],
            }
        )


def test_generation_evidence_source_ids_are_positive_strict_integers() -> None:
    with pytest.raises(ValidationError):
        SectionEvidence(source_id=0)
    with pytest.raises(ValidationError):
        ActivityEvidence(target="objective", source_id=0)
    with pytest.raises(ValidationError):
        SectionEvidence(source_id=True)


def test_domain_error_has_one_payload_shape_and_http_mapping() -> None:
    error = DomainError(
        ErrorCode.MISSING_PARAMETERS,
        "Indica la cantidad de preguntas.",
        action="quiz",
        details=ErrorDetails(
            missing_fields=["question_count"],
            conflicting_fields=[],
            invalid_fields=[],
            constraints=[],
        ),
    )
    payload = error.to_payload()

    assert error.http_status == 422
    assert payload == {
        "status": "needs_clarification",
        "action": "quiz",
        "error": {
            "code": "MISSING_PARAMETERS",
            "message": "Indica la cantidad de preguntas.",
            "details": {
                "missing_fields": ["question_count"],
                "conflicting_fields": [],
                "invalid_fields": [],
                "constraints": [],
            },
        },
    }


def test_invalid_model_output_is_separate_from_irreversible_domain_errors() -> None:
    invalid = InvalidModelOutput("generation", "La clave no coincide.", issues=("correct_answer",))
    assert not isinstance(invalid, DomainError)
    assert invalid.stage == "generation"


@pytest.mark.parametrize(
    "model",
    [
        ParsedInstructions,
        ParsedInstructionsWire,
        ChatGenerationEnvelope,
        QuizGenerationEnvelope,
        ActivityGenerationEnvelope,
    ],
)
def test_openai_responses_sdk_serializes_valid_named_structured_output_models(model) -> None:
    format_param = type_to_text_format_param(model)

    assert format_param["type"] == "json_schema"
    assert format_param["strict"] is True
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", format_param["name"])
    assert format_param["name"] == model.__name__
