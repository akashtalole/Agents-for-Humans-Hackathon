"""File writing tool - identical in behavior to the other two projects'
documents.py (minus read_document, which GlacierWatch doesn't need since its
inputs are the bundled watchlist plus live API data, not user-supplied files)."""
from __future__ import annotations

from pathlib import Path

from strands import tool


@tool
def save_text_file(path: str, content: str) -> str:
    """Write text content to a file, creating parent directories as needed.

    Args:
        path: Destination filesystem path.
        content: Text content to write.

    Returns:
        A short confirmation message including the number of characters written.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Saved {len(content)} characters to {path}"
