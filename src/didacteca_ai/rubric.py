"""Validación defensiva y proyección textual de rúbricas para actividades."""

from __future__ import annotations

import re

from didacteca_ai.math_format import math_spans
from didacteca_ai.schemas import Rubric


def _escape_table_cell(value: str) -> str:
    """Escapa texto plano y conserva intactas las expresiones matemáticas."""

    spans = math_spans(value)
    parts: list[str] = []
    cursor = 0

    for start, end in spans:
        math = value[start:end]
        if "|" in math:
            raise ValueError(
                "No uses | literal dentro de matemáticas en una celda de rúbrica; "
                "escribe \\mid, \\vert o \\lvert...\\rvert según la operación deseada."
            )
        if "\n" in math or "\r" in math:
            raise ValueError(
                "La matemática dentro de una celda de rúbrica debe ser inline y ocupar "
                "una sola línea; cambia el bloque a \\(...\\)."
            )
        if math.startswith(r"\["):
            raise ValueError(
                "La matemática dentro de una celda de rúbrica debe ser inline; "
                "cambia \\[...\\] a \\(...\\)."
            )

        parts.append(_escape_plain_cell(value[cursor:start]))
        parts.append(math)
        cursor = end

    parts.append(_escape_plain_cell(value[cursor:]))
    return "".join(parts)


def _escape_plain_cell(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace("|", r"\|")
    return re.sub(r"\r\n|\r|\n", "<br>", escaped)


def render_expected_result(expected_product: str, rubric: Rubric | None) -> str:
    """Combina el producto esperado con la rúbrica en Markdown, si existe.

    La rúbrica se vuelve a validar al entrar para cubrir instancias creadas con
    ``model_construct()``, que omite los validadores normales de Pydantic.
    """

    if not isinstance(expected_product, str):
        raise TypeError("expected_product debe ser una cadena.")
    if rubric is None:
        return expected_product
    if not expected_product.strip():
        raise ValueError("expected_product no puede estar vacío.")
    if not isinstance(rubric, Rubric):
        raise TypeError("rubric debe ser Rubric o None.")

    checked_rubric = Rubric.model_validate(rubric.model_dump(mode="python"))
    lines = [
        expected_product,
        "",
        "### Rúbrica de evaluación",
        "",
        "| Criterio y evidencia | Máximo | Niveles de desempeño | Puntaje obtenido |",
        "| --- | ---: | --- | --- |",
    ]

    for criterion in checked_rubric.criteria:
        criterion_cell = "<br>".join(
            (
                _escape_table_cell(criterion.name),
                _escape_table_cell(criterion.evidence),
            )
        )
        levels_cell = "<br>".join(
            f"{level.score}: {_escape_table_cell(level.descriptor)}"
            for level in criterion.levels
        )
        lines.append(
            "| "
            f"{criterion_cell} | {criterion.max_points} | {levels_cell} | "
            "Por asignar |"
        )

    lines.extend(
        [
            "",
            "**Regla de suma:** los puntajes máximos de los criterios suman exactamente 10 puntos.",
            "El docente asigna el puntaje obtenido; la tabla no contiene calificaciones predeterminadas.",
        ]
    )
    return "\n".join(lines)
