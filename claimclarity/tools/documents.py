"""File I/O tools: reading source documents and writing generated ones.

Identical in behavior to bidwright/tools/documents.py - duplicated rather than
shared so ClaimClarity stays an independently deployable project.
"""
from __future__ import annotations

from pathlib import Path

from strands import tool


@tool
def read_document(path: str) -> str:
    """Read a document from disk and return its plain-text contents.

    Supports .txt, .md, .pdf, and .docx files.

    Args:
        path: Filesystem path to the document.

    Returns:
        The extracted plain text of the document.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        import docx

        document = docx.Document(str(file_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    return file_path.read_text(encoding="utf-8", errors="ignore")


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
