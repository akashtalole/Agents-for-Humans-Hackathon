from pathlib import Path

import pytest

from claimclarity.payload import resolve_document_paths


def test_resolve_document_paths_with_existing_paths(tmp_path: Path):
    doc_file = tmp_path / "denial.md"
    doc_file.write_text("Denial notice content")

    paths = resolve_document_paths({"document_paths": [str(doc_file)]}, str(tmp_path / "work"))
    assert paths == [str(doc_file)]


def test_resolve_document_paths_with_inline_texts(tmp_path: Path):
    workdir = tmp_path / "work"
    paths = resolve_document_paths(
        {"document_texts": ["Denial notice text", "Plan summary text"]}, str(workdir)
    )
    assert len(paths) == 2
    assert Path(paths[0]).read_text() == "Denial notice text"
    assert Path(paths[1]).read_text() == "Plan summary text"


def test_resolve_document_paths_combines_paths_and_texts(tmp_path: Path):
    doc_file = tmp_path / "denial.md"
    doc_file.write_text("Denial notice content")
    workdir = tmp_path / "work"

    paths = resolve_document_paths(
        {"document_paths": [str(doc_file)], "document_texts": ["Plan summary text"]}, str(workdir)
    )
    assert len(paths) == 2
    assert paths[0] == str(doc_file)
    assert Path(paths[1]).read_text() == "Plan summary text"


def test_resolve_document_paths_neither_provided_raises_clear_error(tmp_path: Path):
    with pytest.raises(ValueError, match="document_paths.*document_texts"):
        resolve_document_paths({}, str(tmp_path / "work"))
