"""
Morning Brief — fetch RSS feeds, summarize via local Ollama, print a digest.

Usage:
    python brief.py                 # run with default config.yaml
    python brief.py --config x.yaml # use a different config file
    python brief.py --dry-run       # fetch but skip LLM calls (for debugging)
    python brief.py --limit 5       # cap items per feed (for testing)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import feedparser
import httpx
import yaml


@dataclass
class Item:
    title: str
    summary: str
    link: str
    source: str
    published: dt.datetime | None


# ---------------------------------------------------------------------------
# Config

def load_config(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def load_prompt(path: Path) -> str:
    return path.read_text()


# ---------------------------------------------------------------------------
# Fetching

def fetch_feed(url: str, name: str, lookback_hours: int, limit: int | None) -> list[Item]:
    # Fetch with an explicit timeout so a slow server can't hang us.
    raw = httpx.get(url, timeout=20, follow_redirects=True,
                    headers={"User-Agent": "morning-brief/0.1"})
    raw.raise_for_status()
    parsed = feedparser.parse(raw.content)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    items: list[Item] = []
    for entry in parsed.entries:
        published = _entry_datetime(entry)
        if published and published < cutoff:
            continue
        items.append(Item(
            title=entry.get("title", "").strip(),
            summary=_strip_html(entry.get("summary", "")),
            link=entry.get("link", ""),
            source=name,
            published=published,
        ))
        if limit and len(items) >= limit:
            break
    return items


def _entry_datetime(entry) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
    return None


def _strip_html(text: str) -> str:
    # Rough — good enough for RSS summaries
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# LLM

def call_ollama(host: str, model: str, prompt: str, timeout_s: int = 120) -> str:
    response = httpx.post(
        f"{host.rstrip('/')}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def summarize_item(
    item: Item, template: str, interests: str, config: dict, verbose: bool = False,
) -> str | None:
    prompt = template.format(
        interests=interests,
        source=item.source,
        title=item.title,
        summary=item.summary[:800],
    )
    raw = call_ollama(config["ollama"]["host"], config["ollama"]["model"], prompt)
    if verbose:
        print(f"    TITLE: {item.title[:80]}", file=sys.stderr)
        print(f"    RAW:   {raw[:200]}", file=sys.stderr)
    return _extract_summary(raw)


_PREFIX_NOISE = ("INCLUDE", "SUMMARY", "SUMMARY:", "REPLY:", "RESPONSE:", "ANSWER:")


def _extract_summary(raw: str) -> str | None:
    """Parse the model's reply into None (SKIP) or a clean one-sentence summary."""
    # Strip quotes and whitespace, split into lines
    lines = [ln.strip().strip('"').strip("'") for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]  # drop blank lines

    for line in lines:
        upper = line.upper().rstrip(":.")
        if upper == "SKIP":
            return None
        # Ignore prefix noise ("INCLUDE", "SUMMARY:", etc.) and keep looking
        if upper in _PREFIX_NOISE:
            continue
        # Strip a leading "INCLUDE:" / "SUMMARY:" if glued to the sentence
        for noise in _PREFIX_NOISE:
            if upper.startswith(noise):
                line = line[len(noise):].lstrip(":-. ").strip()
                break
        if line:
            return line
    return None


def write_intro(digest_items: list[tuple[Item, str]], template: str, config: dict) -> str:
    bullets = "\n".join(f"- {line}" for _, line in digest_items)
    prompt = template.format(bullets=bullets, date=dt.date.today().isoformat())
    return call_ollama(config["ollama"]["host"], config["ollama"]["model"], prompt)


# ---------------------------------------------------------------------------
# Assembly

def render_digest(
    intro: str,
    digest_items: list[tuple[Item, str]],
    now: dt.datetime,
) -> str:
    lines = [
        f"Morning Brief — {now.strftime('%A, %b %d %Y')}",
        "=" * 50,
        "",
        intro,
        "",
        "NEWS",
    ]
    for item, summary in digest_items:
        lines.append(f"- [{item.source}] {summary}")
        lines.append(f"  {item.link}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main

def main() -> int:
    # Make stderr unbuffered so --verbose progress shows up live, even
    # when piped to `tee` or a log file.
    try:
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except AttributeError:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Print each article title and the raw LLM response (for debugging)")
    ap.add_argument("--no-open", action="store_true",
                    help="Don't open the HTML brief in a browser after generating")
    args = ap.parse_args()

    here = Path(__file__).parent
    config_path = args.config if args.config.is_absolute() else here / args.config
    config = load_config(config_path)

    summarize_tpl = load_prompt(here / "prompts" / "summarize.txt")
    intro_tpl = load_prompt(here / "prompts" / "intro.txt")

    lookback = int(config.get("lookback_hours", 24))
    per_feed_cap = args.limit or int(config.get("per_feed_limit", 10))

    print(f"[{_ts()}] Fetching {len(config['feeds'])} feeds...", file=sys.stderr)
    all_items: list[Item] = []
    for feed in config["feeds"]:
        try:
            items = fetch_feed(feed["url"], feed["name"], lookback, per_feed_cap)
            print(f"  {feed['name']}: {len(items)} items", file=sys.stderr)
            all_items.extend(items)
        except Exception as e:
            print(f"  {feed['name']}: ERROR {e}", file=sys.stderr)

    if args.dry_run:
        print(f"[{_ts()}] Dry run — fetched {len(all_items)} items, skipping LLM.", file=sys.stderr)
        for it in all_items[:20]:
            print(f"  [{it.source}] {it.title}")
        return 0

    if not all_items:
        print("No items in lookback window. Nothing to summarize.")
        return 0

    print(f"[{_ts()}] Summarizing {len(all_items)} items via {config['ollama']['model']}...", file=sys.stderr)
    digest: list[tuple[Item, str]] = []
    for i, item in enumerate(all_items, 1):
        try:
            summary = summarize_item(
                item, summarize_tpl, config.get("interests", ""), config,
                verbose=args.verbose,
            )
        except Exception as e:
            print(f"  [{i}/{len(all_items)}] ERROR: {e}", file=sys.stderr)
            continue
        if summary:
            digest.append((item, summary))
            print(f"  [{i}/{len(all_items)}] kept", file=sys.stderr)
        else:
            print(f"  [{i}/{len(all_items)}] skipped", file=sys.stderr)

    max_items = int(config.get("max_digest_items", 8))
    digest = digest[:max_items]

    print(f"[{_ts()}] Writing intro...", file=sys.stderr)
    intro = write_intro(digest, intro_tpl, config) if digest else "Quiet morning — not much to report."

    now = dt.datetime.now()
    text_output = render_digest(intro, digest, now)

    # Pretty terminal rendering if rich is available; plain text otherwise
    _print_terminal(intro, digest, now)

    # Always write text + HTML outputs beside each other
    out_path = config.get("output_path")
    if out_path:
        out_file = Path(out_path)
        if not out_file.is_absolute():
            out_file = here / out_file
        out_file = out_file.expanduser()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        date_suffix = dt.date.today().isoformat()
        txt_path = out_file.with_name(f"{out_file.stem}-{date_suffix}{out_file.suffix}")
        html_path = txt_path.with_suffix(".html")

        txt_path.write_text(text_output)
        print(f"[{_ts()}] Wrote {txt_path}", file=sys.stderr)

        try:
            from render_html import render_brief_html
            html_output = render_brief_html(
                intro=intro,
                digest_items=digest,
                now=now,
                model=config["ollama"]["model"],
            )
            html_path.write_text(html_output)
            print(f"[{_ts()}] Wrote {html_path}", file=sys.stderr)

            if not args.no_open:
                _open_in_browser(html_path)
        except Exception as e:
            print(f"[{_ts()}] HTML render failed: {e}", file=sys.stderr)

    return 0


def _open_in_browser(path: Path) -> None:
    """Open the HTML brief in the user's default browser."""
    import subprocess
    import webbrowser

    # xdg-open picks the configured default browser on Linux; fall back to
    # Python's webbrowser module (which handles macOS and other platforms).
    try:
        subprocess.Popen(
            ["xdg-open", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"[{_ts()}] Opened in browser", file=sys.stderr)
        return
    except FileNotFoundError:
        pass

    try:
        webbrowser.open(path.as_uri())
        print(f"[{_ts()}] Opened in browser", file=sys.stderr)
    except Exception as e:
        print(f"[{_ts()}] Could not auto-open: {e}", file=sys.stderr)


def _print_terminal(intro: str, digest: list[tuple[Item, str]], now: dt.datetime) -> None:
    """Pretty terminal rendering (if rich is available), else plain text."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.rule import Rule
        from rich.text import Text
    except ImportError:
        print(render_digest(intro, digest, now))
        return

    console = Console()
    date_str = now.strftime("%A, %B %d %Y")

    header = Text()
    header.append("Morning Brief\n", style="bold #d4a574")
    header.append(date_str, style="#8f8d87")
    console.print(Panel(header, border_style="#6b553d", padding=(0, 2)))
    console.print()

    console.print(Text(intro, style="italic"))
    console.print()

    if not digest:
        console.print("[dim]Quiet morning — nothing notable in the feeds.[/dim]")
        return

    console.print(Rule("News", style="#6b553d"))
    for item, summary in digest:
        source_tag = f"[bold #d4a574][{item.source}][/bold #d4a574]"
        link = item.link
        line = Text.from_markup(f"  {source_tag} ")
        if link:
            line.append(summary, style=f"link {link}")
        else:
            line.append(summary)
        console.print(line)
        if link:
            console.print(f"    [dim]{link}[/dim]")
    console.print()


def _ts() -> str:
    return time.strftime("%H:%M:%S")


if __name__ == "__main__":
    sys.exit(main())
