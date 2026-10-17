"""Contratos públicos e internos usados por el servicio Didacteca."""

from __future__ import annotations

import re
from typing import Annotated, Generic, Literal, TypeAlias, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    AfterValidator,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


Action = Literal["chat", "quiz", "activity"]
Difficulty = Literal["easy", "intermediate", "hard"]
ActivityType = Literal[
    "diagnostica",
    "comprension",
    "aplicacion",
    "analisis",
    "evaluativa",
    "diseno",
]
Modality = Literal["individual", "team"]
InstructionField = Literal[
    "task",
    "audience",
    "question_count",
    "difficulty",
    "activity_type",
    "modality",
    "duration_minutes",
    "team_size",
]
ProblemField = Literal[
    "action",
    "book_id",
    "section_id",
    "instructions",
    "task",
    "audience",
    "question_count",
    "difficulty",
    "activity_type",
    "modality",
    "duration_minutes",
    "team_size",
]
class StrictContractModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


def _require_nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("El texto no puede estar vacío ni contener solo espacios.")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        raise ValueError("El texto contiene caracteres de control no permitidos.")
    return value


NonEmptyText = Annotated[
    StrictStr,
    Field(min_length=1),
    AfterValidator(_require_nonblank),
]


def require_identifier(value: str) -> str:
    """Acepta IDs opacos ASCII sin interpretarlos ni normalizarlos."""

    if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ValueError("El identificador solo admite letras ASCII, números, _ y -.")
    return value


Identifier = Annotated[StrictStr, AfterValidator(require_identifier)]


class ExecuteRequest(StrictContractModel):
    """Entrada pública: acepta exclusivamente los cuatro campos del contrato."""

    action: Action
    book_id: Identifier
    section_id: Identifier
    instructions: StrictStr

    @field_validator("book_id", "section_id", "instructions")
    @classmethod
    def validate_nonblank_fields(cls, value: str) -> str:
        return _require_nonblank(value)


class ChatSuccess(StrictContractModel):
    action: Literal["chat"]
    answer: NonEmptyText


class QuizQuestion(StrictContractModel):
    question: NonEmptyText
    options: list[NonEmptyText] = Field(min_length=4, max_length=4)
    correct_answer: NonEmptyText
    explanation: NonEmptyText

    @model_validator(mode="after")
    def validate_options(self) -> QuizQuestion:
        normalized = [re.sub(r"\s+", " ", item.strip()).casefold() for item in self.options]
        if len(set(normalized)) != 4:
            raise ValueError("Las cuatro opciones deben ser distintas.")
        if self.correct_answer not in self.options:
            raise ValueError("correct_answer debe coincidir con una opción exacta.")
        return self


class QuizSuccess(StrictContractModel):
    action: Literal["quiz"]
    title: NonEmptyText
    instructions: NonEmptyText
    questions: list[QuizQuestion] = Field(min_length=1)


class ActivitySuccess(StrictContractModel):
    action: Literal["activity"]
    title: NonEmptyText
    objective: NonEmptyText
    instructions: list[NonEmptyText] = Field(min_length=1)
    estimated_time_minutes: StrictInt = Field(gt=0)
    expected_result: NonEmptyText


PublicSuccess: TypeAlias = ChatSuccess | QuizSuccess | ActivitySuccess


class BookSection(StrictContractModel):
    """Sección conocida del Context Service; propiedades adicionales se ignoran."""

    model_config = ConfigDict(strict=True, extra="ignore")

    book_id: StrictStr
    section_id: StrictStr
    title: StrictStr
    content: StrictStr


class InstructionEvidence(StrictContractModel):
    field: InstructionField
    quote: NonEmptyText


class InstructionProblem(StrictContractModel):
    kind: Literal[
        "ambiguous",
        "conflicting",
        "invalid",
        "unfeasible",
        "rule_conflict",
    ]
    message: NonEmptyText
    fields: list[InstructionField]
    evidence: list[NonEmptyText]


class ParsedInstructions(StrictContractModel):
    """Controles extraídos; todo valor ausente se representa explícitamente con null."""

    task: NonEmptyText = Field(
        description=(
            "Acción y producto solicitados, extraídos de instructions. No cambies la acción "
            "pública ni inventes detalles que la persona no pidió. Incluye evidencia literal."
        )
    )
    audience: NonEmptyText | None = Field(
        description=(
            "Público destinatario explícito, incluido nivel educativo, grado/año o perfil "
            "(por ejemplo, 'estudiantes de segundo año de bachillerato'). Revisa toda la "
            "instrucción; usa null solo si no se especifica ningún destinatario. No infieras "
            "el público del libro, tema, dificultad ni de conocimientos supuestos. Incluye "
            "una cita literal exacta como evidencia."
        )
    )
    question_count: StrictInt | None = Field(
        description=(
            "Cantidad explícita de preguntas solicitada como entero. Usa null solo si no se "
            "especifica; si hay cantidades contradictorias o ambiguas, informa el problema "
            "y no elijas una por cuenta propia. Incluye evidencia literal."
        )
    )
    difficulty: Difficulty | None = Field(
        description=(
            "Dificultad explícita y única del quiz: easy, intermediate o hard. No la confundas "
            "con el nivel educativo del público. Usa null solo si falta y cita la expresión "
            "literal que la sustenta."
        )
    )
    activity_type: ActivityType | None = Field(
        description=(
            "Tipo explícito de actividad: diagnostica, comprension, aplicacion, analisis, "
            "evaluativa o diseno. Usa null solo si falta; no elijas un tipo por defecto. "
            "Incluye evidencia literal."
        )
    )
    modality: Modality | None = Field(
        description=(
            "Modalidad explícita de actividad: individual o team (en equipo). Usa null solo "
            "si falta; no la deduzcas del tipo de actividad. Incluye evidencia literal."
        )
    )
    duration_minutes: StrictInt | None = Field(
        description=(
            "Duración total explícita de la actividad, normalizada a minutos enteros. Usa "
            "null solo si falta; si la expresión es ambigua, contradictoria o no puede "
            "normalizarse sin cambiar lo pedido, registra el problema. Incluye evidencia literal."
        )
    )
    team_size: StrictInt | None = Field(
        description=(
            "Cantidad explícita de integrantes por equipo, como entero. Se usa solo con "
            "modalidad team. Usa null solo si no se especifica. Si se indica una cantidad "
            "aunque la modalidad sea individual, conserva el entero y registra el conflicto "
            "entre modalidad y team_size; no descartes el dato explícito. Registra también "
            "cantidades ambiguas o inválidas como problema e incluye evidencia literal."
        )
    )
    evidence: list[InstructionEvidence] = Field(
        description=(
            "Una cita literal, como subcadena exacta de instructions, por cada tarea o "
            "control no nulo extraído. No reformules las citas ni uses texto del libro."
        )
    )
    problems: list[InstructionProblem] = Field(
        description=(
            "Problemas explícitos de instrucciones ambiguas, contradictorias, inválidas, "
            "inviables o en conflicto con las reglas de la capacidad. No inventes problemas; "
            "las citas de evidencia deben ser subcadenas literales de instructions."
        )
    )

    @model_validator(mode="after")
    def validate_evidence_links(self) -> ParsedInstructions:
        evidenced_fields = {item.field for item in self.evidence}
        if "task" not in evidenced_fields:
            raise ValueError("La tarea extraída debe tener evidencia literal asociada.")

        values = {
            "audience": self.audience,
            "question_count": self.question_count,
            "difficulty": self.difficulty,
            "activity_type": self.activity_type,
            "modality": self.modality,
            "duration_minutes": self.duration_minutes,
            "team_size": self.team_size,
        }
        missing_evidence = [
            name
            for name, value in values.items()
            if value is not None and name not in evidenced_fields
        ]
        if missing_evidence:
            raise ValueError(
                "Los valores extraídos requieren evidencia literal: "
                + ", ".join(missing_evidence)
            )
        return self


_InstructionValueT = TypeVar("_InstructionValueT")


class QuotedInstructionValue(StrictContractModel, Generic[_InstructionValueT]):
    """Un control normalizado acompañado por su cita literal en la salida del modelo."""

    value: _InstructionValueT
    quote: NonEmptyText


class ParsedInstructionsWire(StrictContractModel):
    """Formato de extracción del modelo; se normaliza antes de llegar al servicio."""

    task: QuotedInstructionValue[NonEmptyText]
    audience: QuotedInstructionValue[NonEmptyText] | None
    question_count: QuotedInstructionValue[StrictInt] | None
    difficulty: QuotedInstructionValue[Difficulty] | None
    activity_type: QuotedInstructionValue[ActivityType] | None
    modality: QuotedInstructionValue[Modality] | None
    duration_minutes: QuotedInstructionValue[StrictInt] | None
    team_size: QuotedInstructionValue[StrictInt] | None
    problems: list[InstructionProblem]


class SectionEvidence(StrictContractModel):
    source_id: StrictInt = Field(
        ge=1,
        description=(
            "Identificador entero de un fragmento de source_passages enviado por la "
            "aplicación. Elige un source_id que exista; no inventes citas ni identifiques "
            "fragmentos por paráfrasis."
        ),
    )


class ChatDraft(StrictContractModel):
    answer: NonEmptyText
    evidence: list[SectionEvidence] = Field(min_length=1)


class QuizQuestionDraft(QuizQuestion):
    question: NonEmptyText = Field(
        description=(
            "Ajusta la demanda a controls.difficulty y al público indicado. En easy usa "
            "recuerdo, reconocimiento o aplicación directa. En intermediate exige aplicar "
            "o relacionar varios pasos en un caso nuevo que la sección no haya resuelto "
            "explícitamente; el caso puede ser sintético si deriva solo de los métodos del "
            "contenido, sin añadir hechos externos. En hard pide analizar o justificar "
            "varios aspectos dentro del contenido y nivel del público."
        )
    )
    explanation: NonEmptyText = Field(
        description=(
            "Justifica por qué la respuesta es correcta con pasos y relaciones del contenido. "
            "Para intermediate y hard, muestra el razonamiento multietapa aplicado al caso; "
            "no te limites a repetir una fórmula ni agregues conocimientos externos."
        )
    )
    evidence: list[SectionEvidence] = Field(min_length=1)


class QuizDraft(StrictContractModel):
    title: NonEmptyText
    instructions: NonEmptyText
    questions: list[QuizQuestionDraft] = Field(min_length=1)


class ActivityEvidence(StrictContractModel):
    target: Literal["objective", "instructions"] = Field(
        description="Indica qué campo de salida sustenta el fragmento referenciado por source_id."
    )
    source_id: StrictInt = Field(
        ge=1,
        description=(
            "Identificador entero de un fragmento de source_passages que sustenta el "
            "objetivo o los pasos. Elige solo un source_id existente enviado por la "
            "aplicación; no inventes identificadores."
        ),
    )


class RubricLevel(StrictContractModel):
    score: StrictInt = Field(
        ge=0,
        le=10,
        description=(
            "Puntaje entero de este nivel. Los niveles de cada criterio deben incluir todos "
            "los enteros desde max_points hasta cero, en orden descendente."
        ),
    )
    descriptor: NonEmptyText = Field(
        description="Describe de forma observable el desempeño correspondiente a este puntaje."
    )


class RubricCriterion(StrictContractModel):
    name: NonEmptyText = Field(description="Nombre único y observable del criterio.")
    evidence: NonEmptyText = Field(
        description=(
            "Describe qué evidencia de aprendizaje observable se evalúa con este criterio; "
            "debe relacionarse con el objetivo y el contenido recuperado."
        )
    )
    max_points: StrictInt = Field(
        gt=0,
        le=10,
        description=(
            "Puntaje máximo entero positivo del criterio, no mayor que 10. La suma de los "
            "máximos de todos los criterios debe ser exactamente 10."
        ),
    )
    levels: list[RubricLevel] = Field(
        min_length=2,
        description=(
            "Incluye un descriptor por cada puntaje entero desde max_points hasta cero, "
            "sin saltos y en orden descendente."
        ),
    )

    @model_validator(mode="after")
    def validate_levels(self) -> RubricCriterion:
        expected_scores = list(range(self.max_points, -1, -1))
        actual_scores = [level.score for level in self.levels]
        if actual_scores != expected_scores:
            raise ValueError(
                "Cada criterio debe incluir sus puntajes desde el máximo hasta cero, en orden."
            )
        return self


class Rubric(StrictContractModel):
    criteria: list[RubricCriterion] = Field(
        min_length=1,
        description=(
            "Criterios observables y distintos; los puntajes máximos deben sumar "
            "exactamente 10."
        ),
    )

    @model_validator(mode="after")
    def validate_criteria(self) -> Rubric:
        names = [re.sub(r"\s+", " ", item.name.strip()).casefold() for item in self.criteria]
        if len(set(names)) != len(names):
            raise ValueError("Los criterios de la rúbrica deben ser distintos.")
        if sum(item.max_points for item in self.criteria) != 10:
            raise ValueError("La suma de los puntajes máximos de la rúbrica debe ser 10.")
        return self


class ActivityDraft(StrictContractModel):
    title: NonEmptyText
    objective: NonEmptyText
    instructions: list[NonEmptyText] = Field(min_length=1)
    estimated_time_minutes: StrictInt = Field(gt=0)
    expected_product: NonEmptyText
    rubric: Rubric | None = Field(
        description=(
            "Incluye una rúbrica completa cuyos máximos suman 10 solo para actividad "
            "evaluativa; usa null para otros tipos de actividad."
        )
    )
    evidence: list[ActivityEvidence] = Field(
        min_length=1,
        description=(
            "Referencias mediante source_id a fragmentos pertinentes del content recuperado, "
            "con al menos una referencia para el objetivo y otra para las instrucciones."
        ),
    )

    @model_validator(mode="after")
    def validate_activity_evidence(self) -> ActivityDraft:
        targets = {item.target for item in self.evidence}
        if not {"objective", "instructions"}.issubset(targets):
            raise ValueError(
                "La actividad requiere evidencia de la sección para el objetivo y los pasos."
            )
        return self


class GenerationProblem(StrictContractModel):
    code: Literal[
        "MISSING_PARAMETERS",
        "AMBIGUOUS_INSTRUCTIONS",
        "CONFLICTING_INSTRUCTIONS",
        "INVALID_PARAMETERS",
        "UNFEASIBLE_ACTIVITY",
        "REQUEST_RULE_CONFLICT",
        "CONTENT_EMPTY",
        "CONTENT_INSUFFICIENT",
    ]
    message: NonEmptyText
    missing_fields: list[ProblemField]
    conflicting_fields: list[ProblemField]
    invalid_fields: list[ProblemField]
    constraints: list[NonEmptyText]


GenerationOutcome = Literal[
    "success", "needs_clarification", "insufficient_context", "rejected"
]
DraftT = TypeVar("DraftT", ChatDraft, QuizDraft, ActivityDraft)


class GenerationEnvelope(StrictContractModel, Generic[DraftT]):
    """Sobre JSON raíz objeto; se especializa con el borrador de cada acción."""

    outcome: GenerationOutcome
    result: DraftT | None
    problems: list[GenerationProblem]
    limitations: list[NonEmptyText]

    @model_validator(mode="after")
    def validate_outcome(self) -> GenerationEnvelope[DraftT]:
        if self.outcome == "success":
            if self.result is None:
                raise ValueError("Un resultado exitoso requiere result.")
            if self.problems:
                raise ValueError("Un resultado exitoso no puede incluir problemas bloqueantes.")
            return self

        if self.result is not None:
            raise ValueError("Un resultado no exitoso debe tener result null.")
        if not self.problems and not self.limitations:
            raise ValueError("Un resultado no exitoso debe explicar el problema o la limitación.")

        if self.outcome == "needs_clarification":
            has_structured_target = any(
                problem.missing_fields
                or problem.conflicting_fields
                or problem.invalid_fields
                or problem.constraints
                for problem in self.problems
            )
            if not has_structured_target:
                raise ValueError(
                    "Una aclaración debe identificar campos o restricciones que resolver."
                )
        elif self.outcome == "insufficient_context":
            allowed_codes = {"CONTENT_EMPTY", "CONTENT_INSUFFICIENT"}
            if not any(problem.code in allowed_codes for problem in self.problems):
                raise ValueError("La insuficiencia requiere un problema de contenido explícito.")
        elif self.outcome == "rejected":
            if not any(
                problem.code == "REQUEST_RULE_CONFLICT" for problem in self.problems
            ):
                raise ValueError("Un rechazo requiere identificar el conflicto de reglas.")
        return self


class ChatGenerationEnvelope(GenerationEnvelope[ChatDraft]):
    """Sobre de generación con nombre compatible con Structured Outputs."""


class QuizGenerationEnvelope(GenerationEnvelope[QuizDraft]):
    """Sobre de generación con nombre compatible con Structured Outputs."""


class ActivityGenerationEnvelope(GenerationEnvelope[ActivityDraft]):
    """Sobre de generación con nombre compatible con Structured Outputs."""


AnyGenerationEnvelope = (
    ChatGenerationEnvelope | QuizGenerationEnvelope | ActivityGenerationEnvelope
)
