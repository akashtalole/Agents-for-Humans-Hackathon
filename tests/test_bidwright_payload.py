from pathlib import Path

import pytest

from bidwright.payload import resolve_input_paths


def test_resolve_input_paths_with_existing_paths(tmp_path: Path):
    rfp_file = tmp_path / "rfp.md"
    rfp_file.write_text("RFP content")
    profile_file = tmp_path / "profile.json"
    profile_file.write_text("{}")

    rfp_path, profile_path = resolve_input_paths(
        {"rfp_path": str(rfp_file), "profile_path": str(profile_file)}, str(tmp_path / "work")
    )
    assert rfp_path == str(rfp_file)
    assert profile_path == str(profile_file)


def test_resolve_input_paths_with_inline_text(tmp_path: Path):
    workdir = tmp_path / "work"
    rfp_path, profile_path = resolve_input_paths(
        {"rfp_text": "Inline RFP text", "profile_text": "Inline profile text"}, str(workdir)
    )
    assert Path(rfp_path).read_text() == "Inline RFP text"
    assert Path(profile_path).read_text() == "Inline profile text"


def test_resolve_input_paths_mixed_path_and_text(tmp_path: Path):
    rfp_file = tmp_path / "rfp.md"
    rfp_file.write_text("RFP content")
    workdir = tmp_path / "work"

    rfp_path, profile_path = resolve_input_paths(
        {"rfp_path": str(rfp_file), "profile_text": "Inline profile text"}, str(workdir)
    )
    assert rfp_path == str(rfp_file)
    assert Path(profile_path).read_text() == "Inline profile text"


def test_resolve_input_paths_missing_field_raises_clear_error(tmp_path: Path):
    with pytest.raises(KeyError, match="rfp_path.*rfp_text"):
        resolve_input_paths({"profile_text": "Inline profile text"}, str(tmp_path / "work"))
