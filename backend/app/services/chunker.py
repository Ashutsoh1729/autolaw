"""Document chunking service — splits extracted text into manageable chunks."""

import re
from dataclasses import dataclass


@dataclass
class TextChunk:
    """A single chunk of text extracted from a document."""

    index: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    char_start: int = 0
    char_end: int = 0


# Default chunking parameters
DEFAULT_MAX_TOKENS = 2000  # Approximate token limit per chunk
DEFAULT_OVERLAP_CHARS = 200  # Overlap between consecutive chunks


def chunk_by_tokens(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[TextChunk]:
    """Split text into chunks based on approximate token count.

    Uses a simple heuristic: ~4 characters per token on average for English text.
    Chunks are split at paragraph or sentence boundaries when possible.
    """
    if not text or not text.strip():
        return []

    avg_chars_per_token = 4
    max_chars = max_tokens * avg_chars_per_token

    chunks: list[TextChunk] = []
    start = 0
    text_len = len(text)
    index = 0

    while start < text_len:
        end = min(start + max_chars, text_len)

        # Try to break at a paragraph boundary first
        if end < text_len:
            # Look for double newline (paragraph break) going backwards
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + max_chars // 2:
                end = para_break + 2  # include the newlines
            else:
                # Look for single newline
                nl_break = text.rfind("\n", start, end)
                if nl_break > start + max_chars // 2:
                    end = nl_break + 1
                else:
                    # Look for sentence boundary
                    sentence_end = max(
                        text.rfind(". ", start, end),
                        text.rfind("! ", start, end),
                        text.rfind("? ", start, end),
                    )
                    if sentence_end > start + max_chars // 2:
                        end = sentence_end + 2

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                TextChunk(
                    index=index,
                    text=chunk_text,
                    char_start=start,
                    char_end=end,
                )
            )
            index += 1

        # Move start, accounting for overlap
        start = end - overlap_chars if end < text_len else text_len

    return chunks


def chunk_by_pages(text_with_page_markers: str) -> list[TextChunk]:
    """Split text by page markers (for documents with page annotations).

    Expects page markers like '--- Page 1 ---' inserted during OCR.
    """
    if not text_with_page_markers.strip():
        return []

    # Split on page markers
    page_pattern = re.compile(r"---\s*Page\s+(\d+)\s*---")
    parts = page_pattern.split(text_with_page_markers)

    chunks: list[TextChunk] = []
    # parts[0] is text before first marker (usually empty)
    # then pairs of (page_num, page_text)
    if len(parts) < 2:
        return chunk_by_tokens(text_with_page_markers)

    for i in range(1, len(parts), 2):
        page_num = int(parts[i])
        page_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if page_text:
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    text=page_text,
                    page_start=page_num,
                    page_end=page_num,
                )
            )

    if not chunks:
        return chunk_by_tokens(text_with_page_markers)

    return chunks


def chunk_document(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[TextChunk]:
    """Main chunking entry point.

    Tries page-based chunking first; falls back to token-based chunking.
    """
    if "--- Page " in text:
        chunks = chunk_by_pages(text)
        if chunks:
            return chunks
    return chunk_by_tokens(text, max_tokens, overlap_chars)
