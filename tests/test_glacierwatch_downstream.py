from glacierwatch.tools.downstream import data_caveat, load_downstream_exposure


def test_load_downstream_exposure_known_site_returns_settlements():
    settlements = load_downstream_exposure("gepang-gath")
    assert settlements
    names = {s.name for s in settlements}
    assert "Sissu" in names
    for s in settlements:
        assert s.population_band


def test_load_downstream_exposure_unknown_site_returns_empty_list():
    assert load_downstream_exposure("nonexistent-site") == []


def test_data_caveat_is_explicit_about_illustrative_figures():
    caveat = data_caveat()
    assert "illustrative" in caveat.lower() or "approximate" in caveat.lower()
    assert "verified" in caveat.lower()
