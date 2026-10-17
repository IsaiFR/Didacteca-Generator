"""Rechazo local conservador de órdenes explícitas ajenas a la tarea educativa.

No es un detector general de inyecciones ni evalúa código. Los patrones reducen
algunos intentos evidentes antes del modelo; la jerarquía del prompt, contratos
y validaciones siguen siendo necesarios. El libro nunca pasa por este filtro.
"""

from __future__ import annotations

import re
import unicodedata

from .errors import DomainError, ErrorCode, ErrorDetails


_EDUCATIONAL = re.compile(
    r"^\s*(?:¿\s*)?(?:explica|analiza|describe|traduce|compara|define|"
    r"explain|analyze|describe|translate|compare|define|que\s+(?:significa|es)|"
    r"por\s+que|what\s+(?:does|is)|why)\b"
)
_QUOTED = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'|«[^»\n]*»|“[^”\n]*”|`[^`\n]*`')

# Exigen verbos de mandato y objetivos concretos. No buscamos palabras SQL ni
# comandos aislados: pueden ser el tema legítimo de una pregunta del libro.
_OVERRIDE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(?:ignora|omite|olvida|desobedece|anula|ignore|disregard|forget|override)\b"
        r"\s+(?:(?:todas?|las?|los?|tus?|mis?|these|all|the|your|previous|prior|anteriores?|previas?)\s+){0,5}"
        r"(?:reglas|instrucciones|restricciones|rules|instructions|restrictions|system\s+prompt)\b",
        r"\b(?:actua|comportate|act|behave)\s+(?:ahora\s+)?(?:como|as)\s+"
        r"(?:(?:un|una|a|an|el|the)\s+)?(?:administrador|administrator|system|sistema|developer)\b",
        r"\b(?:ahora\s+eres|eres\s+ahora|you\s+are\s+now)\s+(?:(?:el|un|a|the)\s+)?"
        r"(?:sistema|system|developer|administrador|administrator)\b",
        r"\b(?:activa|habilita|enable|activate)\s+(?:el\s+)?"
        r"(?:modo\s+(?:desarrollador|sin\s+restricciones)|developer\s+mode)\b",
        r"\b(?:revela|muestra|imprime|dame|devuelve|reveal|show|print|return|give\s+me)\b"
        r"[^.!?\n;]{0,70}\b(?:secretos?|secrets?|api[_ -]?key|claves?\s+(?:api|privadas?)|"
        r"openai_api_key|system\s+prompt|prompt\s+(?:del?\s+)?sistema|variables?\s+de\s+entorno)\b",
        r"\b(?:lee|abre|read|open)\s+(?:(?:el|the)\s+)?(?:archivo\s+)?[\"']?\.env\b",
        r"\b(?:ejecuta|corre|execute|run)\s+(?:(?:este|el|the|this|un|a)\s+)?"
        r"(?:comando|command|shell|powershell|bash|cmd(?:\.exe)?|rm\s+-|curl\b|wget\b|eval\s*\(|exec\s*\()",
        r"\b(?:usa|utiliza|use)\s+(?:tu\s+|your\s+)?(?:conocimiento\s+externo|external\s+knowledge)\b",
        r"\b(?:cambia|change)\s+(?:(?:la|el|the)\s+)?(?:action|accion|esquema\s+de\s+salida|output\s+schema)\b",
    )
)


def _inspection_text(instructions: str) -> str:
    # Solo la copia de inspección cambia: citas y petición original se conservan.
    normalized = unicodedata.normalize("NFKC", instructions).casefold()
    normalized = "".join(
        character for character in normalized if unicodedata.category(character) != "Cf"
    )
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFD", normalized)
        if unicodedata.category(character) != "Mn"
    )
    return normalized


def validate_request_rules(instructions: str, action: str) -> None:
    """Rechaza órdenes claras, permitiendo ejemplos citados para su análisis."""

    inspection = _inspection_text(instructions)
    # Una cita solo se trata como ejemplo cuando la petición comienza con una
    # tarea de análisis. Órdenes añadidas fuera de la cita se siguen comprobando.
    if _EDUCATIONAL.match(inspection):
        inspection = _QUOTED.sub(" EJEMPLO_CITADO ", inspection)
    if any(pattern.search(inspection) for pattern in _OVERRIDE_PATTERNS):
        raise DomainError(
            ErrorCode.REQUEST_RULE_CONFLICT,
            "La solicitud contradice las reglas de la capacidad seleccionada.",
            action=action,
            details=ErrorDetails(
                missing_fields=[],
                conflicting_fields=["instructions"],
                invalid_fields=[],
                constraints=[
                    "Solicita una tarea educativa sin anular reglas, revelar secretos ni ejecutar comandos."
                ],
            ),
        )
