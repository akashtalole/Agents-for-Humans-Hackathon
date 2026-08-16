from pathlib import Path

import pytest

from bidwright.tools.documents import read_document, save_text_file


def test_read_document_txt(tmp_path: Path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Hello RFP world")
    assert read_document(str(file_path)) == "Hello RFP world"


def test_read_document_md(tmp_path: Path):
    file_path = tmp_path / "sample.md"
    file_path.write_text("# Title\n\nBody text")
    assert "Title" in read_document(str(file_path))


def test_read_document_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_document(str(tmp_path / "does_not_exist.txt"))


def test_save_text_file_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "nested" / "dir" / "out.md"
    message = save_text_file(str(target), "content here")
    assert target.read_text() == "content here"
    assert "12 characters" in message
