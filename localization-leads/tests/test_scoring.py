"""Tests for the company qualification scoring module."""
import json

from scoring import score_company, _tier_from_score, _has_contact_page


def test_basic_company_scores_strong(site_data_basic):
    """A site with keywords + contact + about + LinkedIn should be 'strong'."""
    score, tier, reasons = score_company(
        site_data_basic,
        domain="acme.com",
        linkedin_url="https://www.linkedin.com/company/acme-translation",
    )
    assert score >= 60
    assert tier == "strong"
    assert isinstance(reasons, list) and len(reasons) > 0
    assert any("keyword" in r for r in reasons)
    assert any("contact" in r for r in reasons)
    assert any("LinkedIn" in r for r in reasons)


def test_no_keywords_fails_hard():
    """A site with structure but zero LSP keywords must score 0 / weak."""
    site = {
        "markdown": "We sell shoes. Running shoes and boots for everyone.",
        "links": ["https://shoes.com/contact", "https://shoes.com/about"],
    }
    score, tier, reasons = score_company(site, domain="shoes.com", linkedin_url="")
    assert score == 0
    assert tier == "weak"
    assert any("missing industry keywords" in r for r in reasons)


def test_empty_site_data_returns_zero():
    score, tier, reasons = score_company(None, domain="x.com", linkedin_url="")
    assert score == 0
    assert tier == "weak"
    assert reasons == []


def test_tier_thresholds():
    assert _tier_from_score(80) == "strong"
    assert _tier_from_score(60) == "strong"
    assert _tier_from_score(59) == "possible"
    assert _tier_from_score(30) == "possible"
    assert _tier_from_score(29) == "weak"
    assert _tier_from_score(0) == "weak"


def test_keyword_density_caps_at_50():
    """Even a keyword-stuffed page can't exceed 50 from relevance alone."""
    many = " ".join(["translation localization interpretation linguist "
                     "multilingual subtitling dubbing transcreation sworn"] * 5)
    site = {"markdown": many, "links": []}
    score, tier, reasons = score_company(site, domain="kw.com", linkedin_url="")
    assert score <= 100  # never exceeds total cap
    # relevance alone: min(50, count*7) — count capped by keyword list
    relevance_only = score_company({"markdown": many, "links": []}, "kw.com", "")[0]
    # remove non-relevance signals by passing empty links + no linkedin already done
    assert relevance_only <= 50


def test_has_contact_page_detects_localized_paths():
    links = ["https://acme.de/kontakt", "https://acme.de/"]
    assert _has_contact_page(links) is True
    links2 = ["https://acme.com/blog", "https://acme.com/"]
    assert _has_contact_page(links2) is False


def test_has_contact_page_handles_dict_links():
    """scanner can produce dict links with 'href' key."""
    links = [{"href": "https://acme.com/impressum"}, {"href": "https://acme.com/"}]
    assert _has_contact_page(links) is True


def test_multilingual_no_longer_scores():
    """Multilingual signal was removed from scoring."""
    site = {
        "markdown": 'translation link rel="alternate" hreflang="de" /en/ /de/',
        "links": [],
    }
    _, _, reasons = score_company(site, "x.com", "")
    assert "multilingual site" not in reasons
