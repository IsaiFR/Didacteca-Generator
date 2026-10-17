from __future__ import annotations

import pytest
from pydantic import ValidationError

from didacteca_ai.rubric import render_expected_result
from didacteca_ai.schemas import Rubric, RubricCriterion, RubricLevel


def _valid_rubric() -> Rubric:
    return Rubric.model_validate(
        {
            "criteria": [
                {
                    "name": "Razonamiento",
                    "evidence": "Explica los pasos realizados.",
                    "max_points": 2,
                    "levels": [
                        {"score": 2, "descriptor": "Completo."},
                        {"score": 1, "descriptor": "Parcial."},
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


def test_without_rubric_returns_the_product_unchanged() -> None:
    expected_product = "Una solución explicada.\nCon los pasos de trabajo."
    assert render_expected_result(expected_product, None) == expected_product


def test_rubric_is_rendered_with_maxima_levels_and_unassigned_scores() -> None:
    rendered = render_expected_result("Una solución explicada.", _valid_rubric())

    assert "Una solución explicada.\n\n### Rúbrica de evaluación" in rendered
    assert "| Criterio y evidencia | Máximo | Niveles de desempeño | Puntaje obtenido |" in rendered
    assert "| Razonamiento<br>Explica los pasos realizados. | 2 |" in rendered
    assert "2: Completo.<br>1: Parcial.<br>0: Sin evidencia." in rendered
    assert rendered.count("Por asignar |") == 2
    assert "suman exactamente 10 puntos" in rendered
    assert "no contiene calificaciones predeterminadas" in rendered


def test_table_cell_pipes_are_escaped_and_linebreaks_become_br() -> None:
    rubric = Rubric.model_validate(
        {
            "criteria": [
                {
                    "name": "Método | procedimiento",
                    "evidence": "Describe un paso.\nIncluye una razón.",
                    "max_points": 10,
                    "levels": [
                        {"score": score, "descriptor": f"Nivel {score} | adecuado."}
                        for score in range(10, -1, -1)
                    ],
                }
            ]
        }
    )

    rendered = render_expected_result("Producto", rubric)
    assert r"Método \| procedimiento" in rendered
    assert "Describe un paso.<br>Incluye una razón." in rendered
    assert r"Nivel 10 \| adecuado." in rendered
    assert "\r" not in rendered


def test_valid_inline_latex_in_rubric_is_preserved_and_expected_product_keeps_display_math() -> None:
    data = _valid_rubric().model_dump(mode="python")
    data["criteria"][0]["evidence"] = (
        r"Usa \(x^2\) y calcula \(\frac{\Delta}{4}\)."
    )
    data["criteria"][0]["levels"][0]["descriptor"] = (
        r"Presenta \(x^2\) sin errores."
    )
    rubric = Rubric.model_validate(data)
    expected_product = "Producto esperado:\n" + r"\[x^2+1\]"

    rendered = render_expected_result(expected_product, rubric)

    assert expected_product in rendered
    assert r"Usa \(x^2\) y calcula \(\frac{\Delta}{4}\)." in rendered
    assert r"Presenta \(x^2\) sin errores." in rendered
    assert r"\\(x^2\\)" not in rendered


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "evidence",
            r"Usa \(|x|\) para expresar el valor absoluto.",
            "No uses | literal",
        ),
        ("evidence", r"Compara \[x+1\] con el resultado.", "debe ser inline"),
        (
            "evidence",
            "Expresión: " + r"\(x+" + "\n" + r"1\)",
            "una sola línea",
        ),
    ],
)
def test_table_rejects_nonportable_math_cells(field: str, value: str, message: str) -> None:
    data = _valid_rubric().model_dump(mode="python")
    data["criteria"][0][field] = value
    rubric = Rubric.model_validate(data)

    with pytest.raises(ValueError) as caught:
        render_expected_result("Producto", rubric)
    assert message in str(caught.value)


def test_render_revalidates_rubric_built_without_pydantic_validators() -> None:
    invalid_rubric = Rubric.model_construct(
        criteria=[
            RubricCriterion.model_construct(
                name="Criterio",
                evidence="Evidencia.",
                max_points=2,
                levels=[
                    RubricLevel.model_construct(score=2, descriptor="Completo."),
                    RubricLevel.model_construct(score=0, descriptor="Ausente."),
                ],
            )
        ]
    )

    with pytest.raises(ValidationError):
        render_expected_result("Producto", invalid_rubric)


def test_render_rejects_non_rubric_objects_when_a_rubric_is_supplied() -> None:
    with pytest.raises(TypeError):
        render_expected_result("Producto", object())  # type: ignore[arg-type]


def test_render_rejects_blank_product_when_rubric_is_present() -> None:
    with pytest.raises(ValueError):
        render_expected_result("  \n", _valid_rubric())
