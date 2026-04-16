"""
Render the brief as a self-contained HTML file.

No external assets — inline CSS, system fonts only. Dark theme with
a subtle warm accent. Designed to look good as a morning page you
glance at over coffee.
"""

from __future__ import annotations

import datetime as dt
import html
from urllib.parse import urlparse


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Morning Brief — {date_long}</title>
  <style>
    :root {{
      --bg: #12141a;
      --bg-card: #1a1d26;
      --bg-card-hover: #232733;
      --text: #e8e6e1;
      --text-dim: #8f8d87;
      --accent: #d4a574;
      --accent-dim: #6b553d;
      --border: #2a2e3a;
      --source-bg: #2a2e3a;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #faf8f4;
        --bg-card: #ffffff;
        --bg-card-hover: #f5f2ec;
        --text: #1a1d26;
        --text-dim: #6b6862;
        --accent: #8b5a2b;
        --accent-dim: #b8966a;
        --border: #e5e1d9;
        --source-bg: #ede8de;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   "Helvetica Neue", Arial, sans-serif;
      font-size: 17px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }}
    main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 4rem 1.5rem 6rem;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 0.8rem;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      font-weight: 600;
    }}
    h1 {{
      margin: 0.4rem 0 0.2rem;
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .date {{
      color: var(--text-dim);
      font-size: 0.95rem;
    }}
    .intro {{
      font-size: 1.08rem;
      color: var(--text);
      margin: 0 0 3rem;
      padding: 1.25rem 1.5rem;
      background: var(--bg-card);
      border-left: 3px solid var(--accent);
      border-radius: 0 8px 8px 0;
    }}
    .section-label {{
      color: var(--text-dim);
      font-size: 0.75rem;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      margin: 0 0 1rem;
      font-weight: 600;
    }}
    .items {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    .item {{
      padding: 1rem 1.25rem;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      transition: background 0.15s, border-color 0.15s;
    }}
    .item:hover {{
      background: var(--bg-card-hover);
      border-color: var(--accent-dim);
    }}
    .item-head {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 0.4rem;
    }}
    .source {{
      display: inline-block;
      padding: 0.15rem 0.55rem;
      background: var(--source-bg);
      color: var(--text-dim);
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .domain {{
      color: var(--text-dim);
      font-size: 0.8rem;
    }}
    .summary {{
      margin: 0;
      color: var(--text);
    }}
    .summary a {{
      color: inherit;
      text-decoration: none;
      border-bottom: 1px solid var(--accent-dim);
    }}
    .summary a:hover {{
      color: var(--accent);
      border-bottom-color: var(--accent);
    }}
    footer {{
      margin-top: 4rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      color: var(--text-dim);
      font-size: 0.8rem;
      text-align: center;
    }}
    .empty {{
      padding: 2rem;
      background: var(--bg-card);
      border: 1px dashed var(--border);
      border-radius: 8px;
      color: var(--text-dim);
      text-align: center;
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">Morning Brief</div>
    <h1>Good morning.</h1>
    <div class="date">{date_long}</div>
  </header>

  <p class="intro">{intro_html}</p>

  {body_html}

  <footer>
    Generated {generated_at} · {item_count} items · model: {model}
  </footer>
</main>
</body>
</html>
"""


def render_brief_html(
    intro: str,
    digest_items: list[tuple[object, str]],
    now: dt.datetime,
    model: str,
) -> str:
    """Render the brief as a complete HTML document string."""
    if digest_items:
        items_html = "\n".join(_render_item(item, summary) for item, summary in digest_items)
        body_html = f'<div class="section-label">News</div>\n<div class="items">\n{items_html}\n</div>'
    else:
        body_html = '<div class="empty">Quiet morning — nothing notable in the feeds.</div>'

    return PAGE_TEMPLATE.format(
        date_long=now.strftime("%A, %B %-d, %Y"),
        intro_html=html.escape(intro),
        body_html=body_html,
        generated_at=now.strftime("%H:%M"),
        item_count=len(digest_items),
        model=html.escape(model),
    )


def _render_item(item, summary: str) -> str:
    title = getattr(item, "title", "") or ""
    link = getattr(item, "link", "") or ""
    source = getattr(item, "source", "") or ""
    domain = _domain_of(link)

    summary_html = html.escape(summary)
    if link:
        summary_html = f'<a href="{html.escape(link)}" target="_blank" rel="noopener">{summary_html}</a>'

    return f"""  <div class="item">
    <div class="item-head">
      <span class="source">{html.escape(source)}</span>
      <span class="domain">{html.escape(domain)}</span>
    </div>
    <p class="summary">{summary_html}</p>
  </div>"""


def _domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc
        return netloc.replace("www.", "") if netloc else ""
    except Exception:
        return ""
