"""Dobles de servicios compartidos por las pruebas integradas."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from didacteca_ai.config import Settings
from didacteca_ai.schemas import (
    ActivityGenerationEnvelope,
    BookSection,
    ChatGenerationEnvelope,
    ParsedInstructions,
    QuizGenerationEnvelope,
    Rubric,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        openai_api_key="test-only-not-a-real-key",
    )


@pytest.fixture
def section() -> BookSection:
    return BookSection(
        book_id="book_001",
        section_id="section_04",
        title="Ecuaciones cuadráticas",
        content=(
            "Una ecuación cuadrática tiene la forma ax² + bx + c = 0. "
            "El discriminante b² - 4ac permite conocer la naturaleza de sus raíces. "
            "Si el discriminante es positivo, existen dos raíces reales distintas."
        ),
    )


def make_case(action: str) -> tuple[str, ParsedInstructions]:
    if action == "chat":
        instructions = "Explica el discriminante."
        parsed = {
            "task": "Explica el discriminante.",
            "audience": None,
            "question_count": None,
            "difficulty": None,
            "activity_type": None,
            "modality": None,
            "duration_minutes": None,
            "team_size": None,
            "evidence": [{"field": "task", "quote": "Explica el discriminante."}],
            "problems": [],
        }
        return instructions, ParsedInstructions.model_validate(parsed)

    if action == "quiz":
        instructions = "Crea 2 preguntas de dificultad fácil para estudiantes de secundaria."
        parsed = {
            "task": "Crea preguntas",
            "audience": "estudiantes de secundaria",
            "question_count": 2,
            "difficulty": "easy",
            "activity_type": None,
            "modality": None,
            "duration_minutes": None,
            "team_size": None,
            "evidence": [
                {"field": "task", "quote": "Crea 2 preguntas"},
                {"field": "audience", "quote": "estudiantes de secundaria"},
                {"field": "question_count", "quote": "2 preguntas"},
                {"field": "difficulty", "quote": "dificultad fácil"},
            ],
            "problems": [],
        }
        return instructions, ParsedInstructions.model_validate(parsed)

    instructions = (
        "Crea una actividad evaluativa individual de 20 minutos "
        "para estudiantes de secundaria."
    )
    parsed = {
        "task": "Crea una actividad evaluativa",
        "audience": "estudiantes de secundaria",
        "question_count": None,
        "difficulty": None,
        "activity_type": "evaluativa",
        "modality": "individual",
        "duration_minutes": 20,
        "team_size": None,
        "evidence": [
            {"field": "task", "quote": "Crea una actividad evaluativa"},
            {"field": "audience", "quote": "estudiantes de secundaria"},
            {"field": "activity_type", "quote": "evaluativa"},
            {"field": "modality", "quote": "individual"},
            {"field": "duration_minutes", "quote": "20 minutos"},
        ],
        "problems": [],
    }
    return instructions, ParsedInstructions.model_validate(parsed)


def make_team_activity_case() -> tuple[str, ParsedInstructions]:
    instructions = (
        "Crea una actividad evaluativa para estudiantes de secundaria "
        "en equipos de 4 integrantes durante 20 minutos."
    )
    parsed = ParsedInstructions.model_validate(
        {
            "task": "Crea una actividad evaluativa",
            "audience": "estudiantes de secundaria",
            "question_count": None,
            "difficulty": None,
            "activity_type": "evaluativa",
            "modality": "team",
            "duration_minutes": 20,
            "team_size": 4,
            "evidence": [
                {"field": "task", "quote": "Crea una actividad evaluativa"},
                {"field": "audience", "quote": "estudiantes de secundaria"},
                {"field": "activity_type", "quote": "evaluativa"},
                {"field": "modality", "quote": "equipos"},
                {"field": "duration_minutes", "quote": "20 minutos"},
                {"field": "team_size", "quote": "4 integrantes"},
            ],
            "problems": [],
        }
    )
    return instructions, parsed


def make_rubric() -> Rubric:
    return Rubric.model_validate(
        {
            "criteria": [
                {
                    "name": "Uso de la información",
                    "evidence": "Relaciona la respuesta con el discriminante.",
                    "max_points": 5,
                    "levels": [
                        {"score": 5, "descriptor": "Explica la relación correctamente."},
                        {"score": 4, "descriptor": "Explica la relación con una omisión."},
                        {"score": 3, "descriptor": "La relación es parcialmente correcta."},
                        {"score": 2, "descriptor": "Presenta errores importantes."},
                        {"score": 1, "descriptor": "La evidencia es mínima."},
                        {"score": 0, "descriptor": "No presenta evidencia."},
                    ],
                },
                {
                    "name": "Justificación",
                    "evidence": "Sustenta la conclusión con un paso pertinente.",
                    "max_points": 5,
                    "levels": [
                        {"score": 5, "descriptor": "Justifica la conclusión completa."},
                        {"score": 4, "descriptor": "Justifica con una omisión menor."},
                        {"score": 3, "descriptor": "La justificación es parcial."},
                        {"score": 2, "descriptor": "La justificación es débil."},
                        {"score": 1, "descriptor": "La justificación es mínima."},
                        {"score": 0, "descriptor": "No presenta justificación."},
                    ],
                },
            ]
        }
    )


def make_envelope(action: str, section: BookSection) -> BaseModel:
    if action == "chat":
        return ChatGenerationEnvelope.model_validate(
            {
                "outcome": "success",
                "result": {
                    "answer": "El discriminante permite conocer la naturaleza de las raíces.",
                    "evidence": [{"source_id": 1}],
                },
                "problems": [],
                "limitations": [],
            }
        )
    if action == "quiz":
        return QuizGenerationEnvelope.model_validate(
            {
                "outcome": "success",
                "result": {
                    "title": "Discriminante",
                    "instructions": "Selecciona una respuesta en cada pregunta.",
                    "questions": [
                        {
                            "question": "¿Qué permite conocer el discriminante?",
                            "options": ["La naturaleza de las raíces", "El color del gráfico", "El nombre de la variable", "La unidad de medida"],
                            "correct_answer": "La naturaleza de las raíces",
                            "explanation": "El discriminante indica la naturaleza de las raíces.",
                            "evidence": [{"source_id": 1}],
                        },
                        {
                            "question": "¿Cuál es una expresión del discriminante?",
                            "options": ["b² - 4ac", "a + b + c", "2a + c", "b² + 4ac"],
                            "correct_answer": "b² - 4ac",
                            "explanation": "La sección presenta b² - 4ac como discriminante.",
                            "evidence": [{"source_id": 1}],
                        },
                    ],
                },
                "problems": [],
                "limitations": [],
            }
        )

    return ActivityGenerationEnvelope.model_validate(
        {
            "outcome": "success",
            "result": {
                "title": "Exploración del discriminante",
                "objective": "Relacionar el discriminante con la naturaleza de las raíces.",
                "instructions": [
                    "Individualmente, explica qué informa el discriminante.",
                    "Resuelve un ejemplo y escribe una justificación individual.",
                ],
                "estimated_time_minutes": 20,
                "expected_product": "Una explicación escrita con un ejemplo resuelto.",
                "rubric": make_rubric(),
                "evidence": [
                    {"target": "objective", "source_id": 1},
                    {"target": "instructions", "source_id": 1},
                ],
            },
            "problems": [],
            "limitations": [],
        }
    )


class FakeContextClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    async def get_section(self, book_id: str, section_id: str) -> Any:
        self.calls.append((book_id, section_id))
        if self.error is not None:
            raise self.error
        return self.response

    async def aclose(self) -> None:
        self.closed = True


class FakeLLMClient:
    def __init__(
        self,
        *,
        extractions: Sequence[Any] = (),
        generations: Sequence[Any] = (),
        default_extraction: Any = None,
        default_generation: Any = None,
    ) -> None:
        self.extractions = list(extractions)
        self.generations = list(generations)
        self.default_extraction = default_extraction
        self.default_generation = default_generation
        self.extract_calls: list[dict[str, Any]] = []
        self.generate_calls: list[dict[str, Any]] = []
        self.metrics = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.closed = False

    @staticmethod
    def _next(queue: list[Any], default: Any) -> Any:
        value = queue.pop(0) if queue else default
        if isinstance(value, BaseException):
            raise value
        return value

    async def extract(
        self,
        action: str,
        instructions: str,
        *,
        repair_feedback: str | None = None,
    ) -> Any:
        self.extract_calls.append(
            {"action": action, "instructions": instructions, "repair_feedback": repair_feedback}
        )
        self.metrics = {
            "calls": self.metrics["calls"] + 1,
            "input_tokens": self.metrics["input_tokens"] + 10,
            "output_tokens": self.metrics["output_tokens"] + 5,
        }
        return self._next(self.extractions, self.default_extraction)

    async def generate(
        self,
        action: str,
        controls: ParsedInstructions,
        section: BookSection,
        *,
        repair_feedback: str | None = None,
        original_instructions: str | None = None,
    ) -> Any:
        self.generate_calls.append(
            {
                "action": action,
                "controls": controls,
                "section": section,
                "repair_feedback": repair_feedback,
                "original_instructions": original_instructions,
            }
        )
        self.metrics = {
            "calls": self.metrics["calls"] + 1,
            "input_tokens": self.metrics["input_tokens"] + 20,
            "output_tokens": self.metrics["output_tokens"] + 10,
        }
        return self._next(self.generations, self.default_generation)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def case_factory():
    return make_case


@pytest.fixture
def envelope_factory():
    return make_envelope
