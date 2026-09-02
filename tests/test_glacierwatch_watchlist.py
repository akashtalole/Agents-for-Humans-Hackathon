from glacierwatch.tools.watchlist import list_watchlist_sites, load_all_sites, load_site, regional_context


def test_load_all_sites_returns_real_bundled_data():
    sites = load_all_sites()
    assert len(sites) == 4
    ids = {s.id for s in sites}
    assert ids == {"gepang-gath", "samudra-tapu", "south-lhonak", "chorabari"}


def test_load_site_by_id():
    site = load_site("gepang-gath")
    assert site is not None
    assert site.name == "Gepang Gath Lake"
    assert site.status == "active_watch"
    assert site.sources, "bundled site must carry citations"


def test_load_site_unknown_returns_none():
    assert load_site("nonexistent-site") is None


def test_historical_sites_are_marked_distinctly():
    sites = load_all_sites()
    historical = [s for s in sites if s.status == "historical_case_study"]
    active = [s for s in sites if s.status == "active_watch"]
    assert {s.id for s in historical} == {"south-lhonak", "chorabari"}
    assert {s.id for s in active} == {"gepang-gath", "samudra-tapu"}


def test_list_watchlist_sites_tool_mentions_every_site():
    result = list_watchlist_sites()
    for site in load_all_sites():
        assert site.id in result


def test_regional_context_has_citable_stats():
    context = regional_context()
    assert "28,043" in context["total_glacial_lakes_indian_himalaya"]
    assert "56" in context["nationally_monitored_at_risk_lakes"]
