from claimclarity.models import StateDOIInfo
from claimclarity.tools.state_doi import lookup_state_doi_process, lookup_state_doi_process_tool


def test_lookup_known_state_returns_its_own_entry():
    info = lookup_state_doi_process("CA")
    assert isinstance(info, StateDOIInfo)
    assert info.state_code == "CA"
    assert "California" in info.state_name
    assert "Department of Managed Health Care" in info.doi_name or "DMHC" in info.doi_name


def test_lookup_unknown_state_falls_back_to_default():
    info = lookup_state_doi_process("ZZ")
    assert info.state_code == "DEFAULT"
    assert "45 CFR 147.136" in info.regulatory_note


def test_lookup_blank_state_falls_back_to_default():
    info = lookup_state_doi_process("")
    assert info.state_code == "DEFAULT"


def test_lookup_is_case_and_whitespace_insensitive():
    info = lookup_state_doi_process(" ny ")
    assert info.state_code == "NY"
    assert info.state_name == "New York"


def test_default_entry_never_invents_a_phone_number():
    info = lookup_state_doi_process("DEFAULT")
    # every state's contact instruction should point somewhere to look, not a
    # specific phone number ClaimClarity can't actually verify offline
    assert "search" in info.doi_contact_instruction.lower() or "http" in info.doi_contact_instruction.lower()


def test_lookup_state_doi_process_tool_returns_plain_text_report():
    result = lookup_state_doi_process_tool("TX")
    assert "Texas" in result
    assert "Texas Department of Insurance" in result
    assert "45 CFR 147.136" in result
