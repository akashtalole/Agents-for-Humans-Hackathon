from claimclarity.tools.icd10 import lookup_icd10_code, search_icd10_codes


def test_lookup_flags_deprecated_category_header_as_not_billable():
    result = lookup_icd10_code("M54.5")
    assert "NOT billable" in result
    assert "category header" in result.lower()


def test_lookup_confirms_valid_billable_code():
    result = lookup_icd10_code("M54.51")
    assert "valid, billable" in result
    assert "Vertebrogenic low back pain" in result


def test_lookup_is_case_and_whitespace_insensitive():
    result = lookup_icd10_code(" m54.51 ")
    assert "valid, billable" in result


def test_lookup_unknown_code_is_inconclusive_not_a_false_denial():
    result = lookup_icd10_code("Z00.00")
    assert "not in ClaimClarity's bundled reference set" in result
    assert "inconclusive" in result.lower()


def test_search_finds_the_billable_replacement_for_a_deprecated_code():
    result = search_icd10_codes("low back pain")
    assert "M54.51" in result
    assert "M54.59" in result
    # the deprecated, non-billable category header must never be suggested as a fix
    assert "M54.5:" not in result


def test_search_no_match():
    result = search_icd10_codes("appendicitis")
    assert "No billable codes matching" in result
