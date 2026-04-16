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
    .group {{
      margin-bottom: 2rem;
    }}
    .group-head {{
      display: flex;
      align-items: baseline;
      gap: 0.6rem;
      margin: 0 0 0.8rem;
      padding-bottom: 0.4rem;
      border-bottom: 1px solid var(--border);
    }}
    .group-name {{
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    .group-domain {{
      color: var(--text-dim);
      font-size: 0.78rem;
    }}
    .group-count {{
      margin-left: auto;
      color: var(--text-dim);
      font-size: 0.75rem;
      font-variant-numeric: tabular-nums;
    }}
    .items {{
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }}
    .item {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      transition: background 0.15s, border-color 0.15s;
      overflow: hidden;
    }}
    .item:hover {{
      background: var(--bg-card-hover);
      border-color: var(--accent-dim);
    }}
    .item > summary {{
      list-style: none;
      padding: 0.75rem 1rem 0.75rem 2.2rem;
      cursor: pointer;
      position: relative;
      color: var(--text);
    }}
    .item > summary::-webkit-details-marker {{ display: none; }}
    .item > summary::before {{
      content: "▸";
      position: absolute;
      left: 0.8rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--accent-dim);
      font-size: 0.85rem;
      transition: transform 0.15s, color 0.15s;
    }}
    .item[open] > summary::before {{
      transform: translateY(-50%) rotate(90deg);
      color: var(--accent);
    }}
    .item-body {{
      padding: 0 1rem 0.9rem 2.2rem;
      color: var(--text-dim);
      font-size: 0.92rem;
      line-height: 1.5;
      border-top: 1px dashed var(--border);
      margin-top: 0.1rem;
      padding-top: 0.8rem;
    }}
    .item-body p {{ margin: 0 0 0.6rem; }}
    .item-body .read-more {{
      display: inline-block;
      color: var(--accent);
      text-decoration: none;
      font-size: 0.85rem;
      border-bottom: 1px solid var(--accent-dim);
    }}
    .item-body .read-more:hover {{
      border-bottom-color: var(--accent);
    }}
    .item-body .no-body {{
      font-style: italic;
      color: var(--text-dim);
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
        groups = _group_by_source(digest_items)
        body_html = "\n".join(_render_group(name, items) for name, items in groups)
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


def _group_by_source(digest_items):
    """Group items by source, preserving first-seen order of sources."""
    groups: dict[str, list] = {}
    for item, summary in digest_items:
        source = getattr(item, "source", "") or "Other"
        groups.setdefault(source, []).append((item, summary))
    return list(groups.items())


def _render_group(source: str, items: list) -> str:
    # Show domain of the first item alongside the source name
    first_link = getattr(items[0][0], "link", "") if items else ""
    domain = _domain_of(first_link)
    items_html = "\n".join(_render_item(item, summary) for item, summary in items)
    count_label = f"{len(items)} item{'s' if len(items) != 1 else ''}"
    return f"""<section class="group">
    <div class="group-head">
      <span class="group-name">{html.escape(source)}</span>
      <span class="group-domain">{html.escape(domain)}</span>
      <span class="group-count">{count_label}</span>
    </div>
    <div class="items">
{items_html}
    </div>
  </section>"""


def _render_item(item, summary: str) -> str:
    link = getattr(item, "link", "") or ""
    rss_summary = (getattr(item, "summary", "") or "").strip()
    title = (getattr(item, "title", "") or "").strip()

    # The headline summary (LLM output) — shown in the clickable row
    headline_html = html.escape(summary)

    # Expanded body: original RSS description (truncated if very long),
    # with a "read full article" link if we have one.
    if rss_summary:
        body_text = rss_summary if len(rss_summary) < 600 else rss_summary[:600].rstrip() + "…"
        body_inner = f"<p>{html.escape(body_text)}</p>"
    elif title and title != summary:
        body_inner = f'<p class="no-body">Original headline: {html.escape(title)}</p>'
    else:
        body_inner = '<p class="no-body">No additional context in the feed.</p>'

    if link:
        body_inner += (
            f'<a class="read-more" href="{html.escape(link)}" '
            f'target="_blank" rel="noopener">Read full article →</a>'
        )

    return f"""      <details class="item">
        <summary>{headline_html}</summary>
        <div class="item-body">{body_inner}</div>
      </details>"""


def _domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc
        return netloc.replace("www.", "") if netloc else ""
    except Exception:
        return ""
