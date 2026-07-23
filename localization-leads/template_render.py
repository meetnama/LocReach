"""
template_render.py — Bridge between the Jinja/Tailwind templates in
`templates/` and the live Streamlit app.

Streamlit cannot use the Flask-oriented page templates directly (their
buttons/routes assume a Flask backend). But read-only, presentational
sections can be rendered server-side here with real data and embedded via
`st.components.v1.html`. Interactive controls stay native Streamlit.

Each `render_*` function returns a self-contained HTML document (Tailwind via
CDN, extending `_embed_base.html`) suitable for `st.components.v1.html`.
The paired `*_height` / `table_embed_height` helpers size the iframe.
"""
import os
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# Approx. row height (px) used to size the embedding iframe for tables.
_ROW_PX = 45
_CHROME_PX = 120
_MIN_PX = 160
_MAX_PX = 560


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )


def table_embed_height(row_count: int) -> int:
    """Pixel height for a table-embedding iframe, clamped to a sane range."""
    return max(_MIN_PX, min(_MAX_PX, _CHROME_PX + row_count * _ROW_PX))


# Backwards-compatible alias (Step 1 imported this name first).
def qualified_db_table_height(row_count: int) -> int:
    return table_embed_height(row_count)


def render_qualified_db_table(rows) -> str:
    """Render the 'All Qualified Domains in DB' partial (Step 1).

    `rows` from `db.db_load_qualified_domains`:
    (domain, company_name, linkedin_url, industry, country).
    """
    domains = [
        {
            "domain": r[0],
            "company_name": r[1] or "",
            "linkedin_url": r[2] or "",
            "industry": r[3] or "",
            "country": r[4] or "",
        }
        for r in rows
    ]
    return _env().get_template("_db_domains_embed.html").render(
        domains=domains, count=len(domains)
    )


def render_people_db_table(rows) -> str:
    """Render the 'All People in DB' partial (Step 2).

    `rows` from `db.db_load_people`:
    (full_name, title, company_name, domain, linkedin_url, people_source,
     found_at, company_type).
    """
    people = [
        {
            "full_name": r[0] or "",
            "title": r[1] or "",
            "company_name": r[2] or "",
            "domain": r[3] or "",
            "linkedin_url": r[4] or "",
            "company_type": (r[7] or "").lower() if len(r) > 7 else "",
        }
        for r in rows
    ]
    return _env().get_template("_db_people_embed.html").render(
        people=people, count=len(people)
    )


def render_leads_db_table(rows) -> str:
    """Render the 'All Leads in DB' partial (Step 3).

    `rows` from `db.db_load_leads`:
    (email, email_source, full_name, title, company, domain, linkedin_url).
    """
    leads = [
        {
            "email": r[0] or "",
            "email_source": r[1] or "",
            "full_name": r[2] or "",
            "title": r[3] or "",
            "company": r[4] or "",
            "domain": r[5] or "",
            "linkedin_url": r[6] or "",
        }
        for r in rows
    ]
    return _env().get_template("_db_leads_embed.html").render(
        leads=leads, count=len(leads)
    )


def render_pipeline_snapshot(qualified: int, people_total: int,
                             people_done: int, people_todo: int,
                             leads: int) -> str:
    """Render the Home 'Pipeline Snapshot' panel with live funnel counts."""
    people_pct = round(100 * people_done / people_total) if people_total else 0
    leads_pct = round(100 * leads / people_total) if people_total else 0
    conversion = leads_pct
    return _env().get_template("_pipeline_snapshot_embed.html").render(
        qualified=qualified,
        people_total=people_total,
        people_done=people_done,
        people_todo=people_todo,
        leads=leads,
        people_pct=people_pct,
        leads_pct=leads_pct,
        conversion=conversion,
    )
