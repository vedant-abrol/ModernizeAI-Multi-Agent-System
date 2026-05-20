from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    start_line: int
    end_line: int
    chunk_index: int


def chunk_text(text: str, max_chars: int = 4000, overlap_chars: int = 400) -> list[TextChunk]:
    lines = text.splitlines()
    chunks: list[TextChunk] = []
    current_lines: list[str] = []
    current_start = 1
    current_size = 0

    for line_number, line in enumerate(lines, start=1):
        line_size = len(line) + 1
        if current_lines and current_size + line_size > max_chars:
            chunk_text_value = "\n".join(current_lines)
            chunks.append(
                TextChunk(
                    text=chunk_text_value,
                    start_line=current_start,
                    end_line=line_number - 1,
                    chunk_index=len(chunks),
                )
            )
            overlap_lines: list[str] = []
            overlap_size = 0
            for previous in reversed(current_lines):
                previous_size = len(previous) + 1
                if overlap_lines and overlap_size + previous_size > overlap_chars:
                    break
                overlap_lines.insert(0, previous)
                overlap_size += previous_size
            current_lines = overlap_lines
            current_start = max(1, line_number - len(current_lines))
            current_size = overlap_size
        current_lines.append(line)
        current_size += line_size

    if current_lines or not chunks:
        chunks.append(
            TextChunk(
                text="\n".join(current_lines),
                start_line=current_start,
                end_line=max(current_start, len(lines)),
                chunk_index=len(chunks),
            )
        )
    return chunks

