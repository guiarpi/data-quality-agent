"""HTML dashboard report generator.

Reads the Markdown reports written by each task, converts them to HTML, and
packages everything into a single self-contained HTML file with:
  - Run metadata header
  - KPI summary cards (one per task)
  - Sidebar navigation
  - Task sections with full report content
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import markdown as _md_lib

    def _md_to_html(text: str) -> str:
        return _md_lib.markdown(
            text,
            extensions=["tables", "fenced_code"],
        )

except ImportError:  # graceful fallback — wrap in <pre>
    def _md_to_html(text: str) -> str:
        return f"<pre>{_html.escape(text)}</pre>"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_html_report(
    *,
    task_results: list[tuple[str, Any]],  # (task_name, TaskResult)
    config: dict[str, Any],
    base_dir: Path,
    timestamp: str | None = None,
) -> str:
    """Return a self-contained HTML string combining all task reports."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    dd_cfg = config.get("data_dictionary", {})
    csv_path = dd_cfg.get("csv_path", "—")
    sample_rows = dd_cfg.get("sample_rows", "—")

    sections = []
    cards = []
    nav_items = []

    for task_name, result in task_results:
        label = _task_label(task_name)
        anchor = task_name

        # --- KPI card data ---
        card_html = _kpi_card(task_name, label, result)
        cards.append(card_html)
        nav_items.append(f'<a href="#{anchor}" class="nav-link">{label}</a>')

        # --- Section content ---
        md_content = ""
        if result.report_path and Path(result.report_path).is_file():
            md_content = Path(result.report_path).read_text(encoding="utf-8")
        content_html = _md_to_html(md_content) if md_content else "<p><em>No report generated.</em></p>"

        sections.append(
            f'<section id="{anchor}" class="task-section">'
            f'<h2 class="section-title">{label}</h2>'
            f'<div class="section-body">{content_html}</div>'
            f"</section>"
        )

    return _HTML_TEMPLATE.format(
        timestamp=_html.escape(timestamp),
        csv_path=_html.escape(str(csv_path)),
        sample_rows=f"{int(sample_rows):,}" if str(sample_rows).isdigit() else str(sample_rows),
        task_count=len(task_results),
        kpi_cards="\n".join(cards),
        nav_items="\n".join(nav_items),
        sections="\n".join(sections),
    )


# ---------------------------------------------------------------------------
# KPI card builder
# ---------------------------------------------------------------------------

_TASK_LABELS: dict[str, str] = {
    "data_dictionary": "Data Dictionary",
    "missing_values": "Missing Values",
    "data_types": "Data Types",
    "impossible_values": "Impossible Values",
    "invalid_entries": "Invalid Entries",
    "outliers": "Outliers",
    "categorical_cleaning": "Categorical Cleaning",
}

_TASK_ICONS: dict[str, str] = {
    "data_dictionary": "📖",
    "missing_values": "🕳",
    "data_types": "🔢",
    "impossible_values": "🚫",
    "invalid_entries": "⚠️",
    "outliers": "📊",
    "categorical_cleaning": "🏷",
}


def _task_label(task_name: str) -> str:
    return _TASK_LABELS.get(task_name, task_name.replace("_", " ").title())


def _kpi_card(task_name: str, label: str, result: Any) -> str:
    icon = _TASK_ICONS.get(task_name, "🔍")
    findings = result.findings or {}

    # Build a short metric line and decide card status colour
    metric_lines, status = _card_metrics(task_name, findings, result.ok)

    status_class = {"ok": "card-ok", "warn": "card-warn", "error": "card-error"}.get(
        status, "card-ok"
    )
    metrics_html = "".join(
        f'<div class="metric"><span class="metric-val">{v}</span><span class="metric-label">{k}</span></div>'
        for k, v in metric_lines
    )
    return (
        f'<a href="#{task_name}" class="kpi-card {status_class}">'
        f'<div class="card-icon">{icon}</div>'
        f'<div class="card-label">{label}</div>'
        f'<div class="card-metrics">{metrics_html}</div>'
        f"</a>"
    )


def _card_metrics(
    task_name: str, f: dict[str, Any], ok: bool
) -> tuple[list[tuple[str, Any]], str]:
    """Return ([(label, value), ...], status) for a task's KPI card."""
    if not ok:
        return [("status", "error")], "error"

    def _warn_if(count: int) -> str:
        return "warn" if count > 0 else "ok"

    if task_name == "data_dictionary":
        issues = f.get("missing_defs", 0) + f.get("extra_dict_vars", 0) + f.get("inconsistencies", 0)
        return [
            ("missing defs", f.get("missing_defs", 0)),
            ("extra vars", f.get("extra_dict_vars", 0)),
            ("type issues", f.get("inconsistencies", 0)),
        ], _warn_if(issues)

    if task_name == "missing_values":
        issues = f.get("always_null", 0) + f.get("high_null", 0)
        return [
            ("always null", f.get("always_null", 0)),
            ("high null", f.get("high_null", 0)),
        ], _warn_if(issues)

    if task_name == "data_types":
        return [
            ("columns profiled", f.get("columns_profiled", 0)),
        ], "ok"

    if task_name == "impossible_values":
        issues = f.get("rules_with_violations", 0)
        return [
            ("rules evaluated", f.get("rules_evaluated", 0)),
            ("violations", issues),
        ], _warn_if(issues)

    if task_name == "invalid_entries":
        issues = f.get("rules_with_violations", 0)
        return [
            ("checks run", f.get("rules_evaluated", 0)),
            ("violations", issues),
        ], _warn_if(issues)

    if task_name == "outliers":
        issues = f.get("columns_with_iqr_outliers", 0) + f.get("columns_with_zscore_outliers", 0)
        return [
            ("IQR flagged", f.get("columns_with_iqr_outliers", 0)),
            ("Z-score flagged", f.get("columns_with_zscore_outliers", 0)),
        ], _warn_if(issues)

    if task_name == "categorical_cleaning":
        issues = (
            f.get("columns_with_case_variants", 0)
            + f.get("columns_with_fuzzy_pairs", 0)
            + f.get("columns_with_low_frequency", 0)
        )
        return [
            ("case variants", f.get("columns_with_case_variants", 0)),
            ("fuzzy pairs", f.get("columns_with_fuzzy_pairs", 0)),
            ("low frequency", f.get("columns_with_low_frequency", 0)),
        ], _warn_if(issues)

    # Generic fallback
    items = [(k.replace("_", " "), v) for k, v in f.items() if isinstance(v, int)][:3]
    return items, "ok"


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Quality Report — {timestamp}</title>
<style>
  /* ── Reset & base ── */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22253a;
    --border: #2e3150;
    --text: #e2e4ef;
    --muted: #7b82a8;
    --accent: #6c8ef7;
    --ok: #34d399;
    --warn: #fbbf24;
    --error: #f87171;
    --radius: 10px;
    --sidebar-w: 220px;
  }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    font-size: 14px;
  }}

  /* ── Layout ── */
  .layout {{ display: flex; min-height: 100vh; }}
  .sidebar {{
    width: var(--sidebar-w);
    background: var(--surface);
    border-right: 1px solid var(--border);
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    flex-shrink: 0;
    padding: 20px 0;
  }}
  .main {{ flex: 1; min-width: 0; padding: 32px 40px; max-width: 1000px; }}

  /* ── Sidebar ── */
  .sidebar-title {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 0 20px 16px;
  }}
  .nav-link {{
    display: block;
    padding: 8px 20px;
    color: var(--muted);
    text-decoration: none;
    font-size: 13px;
    border-left: 2px solid transparent;
    transition: color .15s, border-color .15s;
  }}
  .nav-link:hover, .nav-link.active {{
    color: var(--text);
    border-left-color: var(--accent);
    background: rgba(108,142,247,.07);
  }}

  /* ── Top header ── */
  .run-header {{
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }}
  .run-header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 6px; }}
  .run-meta {{ color: var(--muted); font-size: 13px; }}
  .run-meta span {{ margin-right: 20px; }}
  .run-meta code {{
    background: var(--surface2);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 12px;
    color: var(--text);
  }}

  /* ── KPI grid ── */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 40px;
  }}
  .kpi-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    text-decoration: none;
    color: var(--text);
    transition: border-color .15s, transform .1s;
    display: block;
  }}
  .kpi-card:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
  .card-ok  {{ border-left: 3px solid var(--ok); }}
  .card-warn {{ border-left: 3px solid var(--warn); }}
  .card-error {{ border-left: 3px solid var(--error); }}
  .card-icon {{ font-size: 20px; margin-bottom: 6px; }}
  .card-label {{ font-weight: 600; font-size: 13px; margin-bottom: 10px; }}
  .card-metrics {{ display: flex; flex-direction: column; gap: 4px; }}
  .metric {{ display: flex; align-items: baseline; gap: 6px; }}
  .metric-val {{ font-size: 18px; font-weight: 700; }}
  .metric-label {{ font-size: 11px; color: var(--muted); }}

  /* ── Task sections ── */
  .task-section {{
    margin-bottom: 60px;
    padding-top: 8px;
  }}
  .section-title {{
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}
  .section-body {{ color: var(--text); }}

  /* ── Markdown content styles ── */
  .section-body h1 {{ font-size: 20px; margin: 24px 0 12px; display: none; }}
  .section-body h2 {{ font-size: 16px; font-weight: 700; margin: 24px 0 10px; color: var(--accent); }}
  .section-body h3 {{ font-size: 14px; font-weight: 600; margin: 18px 0 8px; }}
  .section-body p {{ margin: 8px 0 12px; color: var(--text); }}
  .section-body em {{ color: var(--muted); font-style: normal; }}
  .section-body strong {{ font-weight: 600; }}
  .section-body ul, .section-body ol {{ margin: 8px 0 12px 20px; }}
  .section-body li {{ margin: 3px 0; }}
  .section-body code {{
    background: var(--surface2);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: #a5b4fc;
  }}
  .section-body pre {{
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    overflow-x: auto;
    margin: 12px 0;
  }}
  .section-body pre code {{ background: none; padding: 0; color: var(--text); }}

  /* Tables */
  .section-body table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin: 12px 0 20px;
  }}
  .section-body th {{
    background: var(--surface2);
    text-align: left;
    padding: 8px 12px;
    border-bottom: 2px solid var(--border);
    font-weight: 600;
    white-space: nowrap;
  }}
  .section-body td {{
    padding: 7px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  .section-body tr:last-child td {{ border-bottom: none; }}
  .section-body tbody tr:hover {{ background: rgba(255,255,255,.03); }}
  .section-body td:last-child, .section-body th:last-child {{ text-align: right; }}

  /* ── Scrollspy ── */
  .nav-link.active {{ color: var(--text); border-left-color: var(--accent); background: rgba(108,142,247,.07); }}
</style>
</head>
<body>
<div class="layout">

  <nav class="sidebar">
    <div class="sidebar-title">Tasks</div>
    {nav_items}
  </nav>

  <main class="main">

    <header class="run-header">
      <h1>Data Quality Report</h1>
      <div class="run-meta">
        <span>🗓 {timestamp}</span>
        <span>📁 <code>{csv_path}</code></span>
        <span>🔢 {sample_rows} rows sampled</span>
        <span>✅ {task_count} tasks</span>
      </div>
    </header>

    <div class="kpi-grid">
      {kpi_cards}
    </div>

    {sections}

  </main>
</div>

<script>
  // Scrollspy — highlight active nav link as user scrolls
  const sections = document.querySelectorAll('.task-section');
  const navLinks = document.querySelectorAll('.nav-link');
  const obs = new IntersectionObserver(entries => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        navLinks.forEach(l => l.classList.remove('active'));
        const link = document.querySelector('.nav-link[href="#' + e.target.id + '"]');
        if (link) link.classList.add('active');
      }}
    }});
  }}, {{ rootMargin: '-20% 0px -70% 0px' }});
  sections.forEach(s => obs.observe(s));
</script>
</body>
</html>
"""
