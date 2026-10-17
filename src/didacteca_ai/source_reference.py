"""Particionamiento reversible del contenido para citas con identificadores."""

from __future__ import annotations


_MAX_PASSAGE_CHARS = 800
_SENTENCE_ENDINGS = frozenset(".!?。！？")


def source_passages(content: str) -> list[str]:
    """Divide contenido sin cambiar ni perder caracteres.

    Prefiere límites de oración y después espacios, dentro de fragmentos de hasta
    800 caracteres. Para contenido no blanco, concatenar la lista reproduce
    ``content`` carácter por carácter; una cadena vacía o solo de espacios produce ``[]``.
    """

    if not isinstance(content, str):
        raise TypeError("content debe ser una cadena.")
    if not content.strip():
        return []

    passages: list[str] = []
    start = 0
    content_length = len(content)
    while start < content_length:
        hard_end = min(start + _MAX_PASSAGE_CHARS, content_length)
        if hard_end == content_length:
            passages.append(content[start:hard_end])
            break

        preferred_start = start + _MAX_PASSAGE_CHARS // 2
        sentence_boundaries: list[int] = []
        space_boundaries: list[int] = []
        for index in range(start, hard_end):
            character = content[index]
            if character in _SENTENCE_ENDINGS:
                following = index + 1
                if following == content_length or content[following].isspace():
                    if following > start:
                        sentence_boundaries.append(following)
            if character.isspace():
                boundary = index + 1
                if boundary > start:
                    space_boundaries.append(boundary)

        usable_sentences = [
            boundary for boundary in sentence_boundaries if boundary >= preferred_start
        ]
        usable_spaces = [
            boundary for boundary in space_boundaries if boundary >= preferred_start
        ]
        if usable_sentences:
            end = usable_sentences[-1]
        elif usable_spaces:
            end = usable_spaces[-1]
        else:
            end = hard_end

        passages.append(content[start:end])
        start = end

    return passages
