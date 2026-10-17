"""Validación sintáctica acotada para marcadores matemáticos LaTeX."""

from __future__ import annotations

import re


_OPENERS = {"(": ")", "[": "]"}
_CLOSERS = frozenset(")]")
_UNWRAPPED_MATH_COMMAND = re.compile(
    r"(?<!\\)\\(?:frac|sqrt|Delta|delta|pm|times|cdot|pi|theta|alpha|beta|gamma|"
    r"leq|geq|neq|infty|sum|int|sin|cos|tan|log|ln|lim)\b"
)
_UNWRAPPED_SCRIPT = re.compile(r"(?<!\\)[\^_]\{[^{}\r\n]+\}")


def _reject_unwrapped_math(text: str, spans: list[tuple[int, int]]) -> None:
    """Rechaza solo marcadores LaTeX inequívocos que quedaron fuera de spans."""

    cursor = 0
    for start, end in [*spans, (len(text), len(text))]:
        plain_text = text[cursor:start]
        if _UNWRAPPED_MATH_COMMAND.search(plain_text) or _UNWRAPPED_SCRIPT.search(
            plain_text
        ):
            raise ValueError(
                "Expresión LaTeX evidente fuera de delimitadores matemáticos; "
                "envuelve la expresión completa con \\(...\\) o \\[...\\]."
            )
        cursor = end


def _update_brace_depth(character: str, depth: int) -> int:
    if character == "{":
        return depth + 1
    if character == "}":
        if depth == 0:
            raise ValueError("La expresión matemática contiene llaves desbalanceadas.")
        return depth - 1
    return depth


def math_spans(text: str) -> list[tuple[int, int]]:
    """Devuelve bloques ``\\(...\\)`` y ``\\[...\\]`` como spans [inicio, fin).

    Valida bloques delimitados y rechaza marcadores LaTeX evidentes que queden
    fuera. No detecta fórmulas ASCII de texto libre ni intenta compilar o
    interpretar semánticamente LaTeX.
    """

    if not isinstance(text, str):
        raise TypeError("text debe ser una cadena.")

    spans: list[tuple[int, int]] = []
    delimiter: str | None = None
    span_start = -1
    body_start = -1
    brace_depth = 0
    index = 0

    while index < len(text):
        if text[index] != "\\":
            if delimiter is not None:
                brace_depth = _update_brace_depth(text[index], brace_depth)
            index += 1
            continue

        run_start = index
        while index < len(text) and text[index] == "\\":
            index += 1
        slash_count = index - run_start
        if index == len(text):
            break
        following = text[index]
        has_delimiter_slash = slash_count % 2 == 1

        if delimiter is None:
            if following in _OPENERS:
                if slash_count != 1:
                    raise ValueError(
                        "Doble escape de delimitador matemático fuera de un bloque."
                    )
                span_start = run_start
                body_start = index + 1
                delimiter = following
                brace_depth = 0
                index += 1
                continue
            if following in _CLOSERS and has_delimiter_slash:
                raise ValueError("Se encontró un cierre matemático sin bloque abierto.")
            index = run_start + slash_count
            continue

        if following in "{}":
            if not has_delimiter_slash:
                brace_depth = _update_brace_depth(following, brace_depth)
            index += 1
            continue

        if following in _OPENERS and has_delimiter_slash:
            raise ValueError("No se permiten bloques matemáticos anidados.")

        if following in _CLOSERS and has_delimiter_slash:
            expected_closer = _OPENERS[delimiter]
            if following != expected_closer:
                raise ValueError("El cierre no coincide con el delimitador matemático.")
            closing_start = index - 1
            if not text[body_start:closing_start].strip():
                raise ValueError("El bloque matemático no puede estar vacío.")
            if brace_depth:
                raise ValueError("La expresión matemática contiene llaves desbalanceadas.")
            spans.append((span_start, index + 1))
            delimiter = None
            span_start = -1
            body_start = -1
            brace_depth = 0
            index += 1
            continue

        index = run_start + slash_count

    if delimiter is not None:
        raise ValueError("El bloque matemático no tiene un cierre correspondiente.")
    _reject_unwrapped_math(text, spans)
    return spans
