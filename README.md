# Morning Brief

A small, local, daily news digest. Pulls RSS feeds, asks a local LLM (via
Ollama) to triage and summarize them, and opens a styled digest in your
browser when you sit down at your PC in the morning.

- **100% local.** No cloud APIs, no subscriptions, no credentials.
- **Runs on modest hardware.** Designed around a 3B model on CPU.
- **Automatic.** Systemd triggers on login (30s delay) and at 07:00 daily,
  with catch-up if the PC was off.
- **Editable via web UI.** Localhost-only form for feeds, interests, model,
  limits.

---

## Quick Reference

| What you want to do | How |
|---|---|
| Fresh brief right now | `brief` (alias) |
| Edit feeds / interests / model | `brief-edit` (alias) → web UI at `http://127.0.0.1:4747` |
| Test run with a few items | `python brief.py --limit 3` |
| See what the LLM replied per item | `python brief.py --verbose --no-open` |
| Fetch-only, no LLM | `python brief.py --dry-run` |
| Check scheduled timers | `systemctl --user list-timers \| grep morning-brief` |
| Inspect failures | `journalctl --user -u morning-brief.service -n 50` |

---

## How it works

```
┌────────────────────────────────────────┐
│ Python (deterministic)                 │
│  • Fetch RSS feeds                     │
│  • For each item, one LLM call:        │
│      "one sentence" OR "SKIP"          │
│  • Collect kept items                  │
│  • One more LLM call for a 2-sentence  │
│    intro                               │
│  • Render → text + HTML                │
│  • Open HTML in default browser        │
└────────────────────────────────────────┘
```

The LLM never plans, calls tools, or drives the pipeline. It only does two
narrow jobs: "summarize one article in one sentence, or SKIP," and "write a
2-sentence intro." Both are things a 3B model can handle reliably.

Everything else — fetching, filtering, rendering, writing files, scheduling,
opening the browser — is plain Python. That's what makes the whole thing
work on a small local model.

---

## Files

```
morning-brief/
├── brief.py                      ← main pipeline (fetch, summarize, render, open)
├── render_html.py                ← HTML renderer (self-contained, styled)
├── webui.py                      ← Flask web UI for editing config
├── config.yaml                   ← feeds, interests, model, limits
├── prompts/
│   ├── summarize.txt             ← per-item triage/summarize prompt
│   └── intro.txt                 ← intro-writing prompt
├── requirements.txt              ← Python deps
│
├── brief-web.sh                  ← launches the web UI
├── install.sh                    ← installs systemd user timers
├── uninstall.sh                  ← removes them
│
├── systemd/
│   ├── morning-brief.service.template   ← path templated at install time
│   ├── morning-brief-boot.timer          ← fires 30s after login
│   └── morning-brief-daily.timer         ← fires at 07:00, persistent
│
├── output/                       ← generated briefs (gitignored)
├── _archive/                     ← old Hermes-shaped scaffold
└── README.md
```

---

## Setup

One-time, on the machine you'll actually run it on.

### 1. Install Ollama + pull a small model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b-instruct          # ~1.9 GB
ollama run qwen2.5:3b-instruct "hi"       # sanity check
```

Ollama runs as a systemd service; it listens on `http://localhost:11434`.

### 2. Set up the Python env

```bash
cd ~/Projects/morning-brief
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Personalize `config.yaml`

Either edit the file directly, or launch the web UI:

```bash
./brief-web.sh       # opens http://127.0.0.1:4747
```

Set:
- **Interests** — free-text. Be specific. "Linux kernel, Rust, agent tooling,
  not consumer gadgets" beats vague "tech news".
- **Feeds** — any RSS/Atom URL works. The repo ships with ~9 curated ones.
- **Model** — swap to any Ollama model you've pulled.

### 4. Try a small run

```bash
source .venv/bin/activate
python brief.py --limit 3
```

You should see:
- Feed fetch status per source
- Per-item kept/skipped decisions
- A prettified terminal preview (via `rich`)
- `output/brief-YYYY-MM-DD.txt` and `.html` written
- Browser tab opens with the HTML brief

### 5. Install the systemd timers

```bash
./install.sh
```

This copies the service + timers into `~/.config/systemd/user/` with the
correct repo path substituted in (it uses wherever `install.sh` lives on
your machine, so the repo can be anywhere).

Verify:

```bash
systemctl --user list-timers | grep morning-brief
```

Both timers should be active.

### 6. Set up shell aliases (optional but nice)

These call `brief.py` directly — no systemd round-trip — so they're instant
and show live progress in your terminal.

On fish:

```fish
alias --save brief='~/Projects/morning-brief/.venv/bin/python ~/Projects/morning-brief/brief.py --force'
alias --save brief-edit='~/Projects/morning-brief/brief-web.sh'
```

On bash/zsh, add to `~/.bashrc` or `~/.zshrc`:

```bash
alias brief='~/Projects/morning-brief/.venv/bin/python ~/Projects/morning-brief/brief.py --force'
alias brief-edit='~/Projects/morning-brief/brief-web.sh'
```

`brief` always regenerates (via `--force`). The scheduled timers still use
idempotency — if today's brief already exists when the timer fires, it just
opens the existing one.

---

## Daily use

The system runs itself after setup. Behavior:

| Scenario | What happens |
|---|---|
| PC boots; you log in at 8:30 AM | 30s after login, brief generates and opens in your browser |
| PC already running at 7:00 AM | Daily timer fires; brief generates and opens |
| PC was off at 7:00 AM; you log in at noon | Catch-up timer fires 30s after login |
| PC stays on across midnight | Next day's 7:00 AM timer runs normally |
| You reboot mid-day | Boot timer fires, sees today's brief already exists, just opens it (no regen) |
| You want a fresh brief on demand | `brief` |
| You just want to look at today's brief | open `output/brief-YYYY-MM-DD.html` directly |
| You want to edit feeds/interests | `brief-edit` |

Idempotency: the wrapper checks `output/brief-YYYY-MM-DD.html`. If it exists,
it just opens it — no redundant LLM calls.

---

## Customization

### Tuning what gets surfaced

In rough order of impact:

1. **Sharpen `interests:`** in `config.yaml`. Most leverage for least effort.
   Include explicit exclusions ("NOT interested in: crypto, celebrity news").
2. **Switch to a bigger model** (if your hardware allows). `qwen2.5:7b-instruct`
   is a noticeable step up from 3B; `qwen2.5:14b` again noticeable over 7B.
3. **Edit `prompts/summarize.txt`** to change tone, length, or filtering
   strictness. Small models follow examples better than abstract rules —
   add a couple of examples of GOOD and BAD replies.
4. **Drop feeds that always get SKIP'd.** They're costing you model time.
5. **Lower `max_digest_items`** for a tighter brief.

### Changing the visual style

`render_html.py` is a single file with inline CSS. Change the CSS variables
at the top of the `PAGE_TEMPLATE` to recolor. Structure is simple and
templated — easy to modify.

### Changing the pipeline shape

`brief.py` is ~200 lines, single file. The pipeline is linear: fetch →
summarize → render. To add a step (weather, calendar, email triage),
slot it in `main()` before the digest render.

### Extending with new sources

Obvious next adds (none currently wired, just ideas):

- **Weather** — Open-Meteo (free, no key). One `httpx.get()` call. Include
  today's forecast in the intro.
- **Calendar** — CalDAV client, list today's events.
- **Email triage** — IMAP, classify as "reply needed / archive / noise."
- **GitHub notifications** — authenticated API call to `/notifications`.
- **Watched topics** — run a Google Alerts-style search against a specific
  topic and feed results in.

### Delivering beyond the browser

`brief.py` currently writes files and opens a browser. To send elsewhere:

- **Telegram** — bot API, one `httpx.post()` to `/bot<token>/sendMessage`.
  Markdown-friendly.
- **Email** — `smtplib`, one call. The HTML file is already well-formatted;
  inline it.
- **Discord** — webhook URL, one `httpx.post()`.

Keep the LLM out of delivery — make those plain HTTP calls, never agentic.

---

## Architecture notes (for future implementations)

### Design principles

- **Demote the LLM.** Each LLM call has one narrow job. Code does everything
  the code can. Small models fail at orchestration, not at classification/
  summarization.
- **One pipeline, not many.** Avoid separate "small model flow" vs "big
  model flow." Design for the smallest supported model; bigger models
  just cruise.
- **Fail gracefully per item.** One feed times out, the rest still work.
  One LLM call errors, the next one runs. No single failure kills the brief.
- **Config > code.** Any knob users touch lives in `config.yaml` (plus
  prompts). Code changes shouldn't be needed for normal tuning.
- **Self-contained output.** HTML is a single file with inline CSS, no
  external assets. Portable, emailable, archivable.

### What a small-model harness looks like

If you extend this, keep this shape:

```
Python   ──calls LLM──▶  narrow, structured prompt with example outputs
Python   ──filters──▶    parse / validate / retry
Python   ──calls LLM──▶  next narrow prompt
...
```

Don't give a small model "here are 20 tools, figure it out" — it'll fumble.
Let code decide what to call next; let the LLM only fill in cells.

### Swapping models up the ladder

The pipeline is model-agnostic. Same config + prompts work at any tier:

| Model scale | Typical quality |
|---|---|
| 1.5B | Barely coherent. Expect malformed outputs. |
| 3B   | This project's target. Works well enough for summarization. |
| 7-8B | Significantly better prose; still quick on CPU. |
| 14B+ | Near-API quality. Slow on CPU; comfortable on GPU. |
| API  | Change base URL + add API key. Instant, expensive. |

To try an API model, point the Ollama host setting at an OpenAI-compatible
endpoint — any provider that speaks that format works.

---

## Security model

This is one of the safer local-automation setups you can run.

### No risk from:
- **Cloud data leakage** — no outbound calls except RSS feed fetches.
- **Credential theft** — there are no credentials in this stack.
- **Network exposure** — Ollama binds to localhost; web UI binds to
  127.0.0.1:4747; systemd service runs as your user, not root.
- **XSS in the HTML brief** — all strings are HTML-escaped before rendering.

### Real but minor risk:
- **LLM prompt injection via RSS content.** A malicious article could
  contain text trying to manipulate the summary. Worst case: a weird line
  in your brief. No code execution possible.
- **Phishing links in feeds.** If a feed is compromised and injects bad
  links, those links end up in your brief. Your browser's normal defenses
  apply. Same risk as reading the feed in any RSS reader.
- **Python supply chain.** `pip install` trusts PyPI. Deps are mainstream
  (feedparser, httpx, pyyaml, rich, flask). Pin versions if paranoid.

### Verification:
```bash
ss -tlnp | grep 11434           # Ollama: should be 127.0.0.1, not 0.0.0.0
ss -tlnp | grep 4747            # Web UI when running: should also be 127.0.0.1
systemctl --user show morning-brief.service | grep UID   # should be your uid, not 0
```

Treat LLM summaries as **untrusted content** — useful signal, not gospel.
Click through before acting on anything important.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| systemd exit 203 | Path wrong in service, or script not executable | Re-run `./install.sh` from the real repo path |
| `brief` hangs for minutes | Normal first run on CPU — model load + per-item inference | Open a second terminal, `tail -f output/run.log` |
| All items `skipped` | Interests too narrow, or model over-conservative | Sharpen interests; check `--verbose` output |
| Model replies with prefix (`INCLUDE\n...`) | Prompt drift from a different model | Parser handles common prefixes; if still leaking, tighten prompt |
| Feed keeps timing out | Slow upstream | Raise timeout in `brief.py` `fetch_feed()`, or drop the feed |
| HTML doesn't auto-open | No `xdg-open` on PATH | Install `xdg-utils`; or open the file manually |
| Web UI can't reach Ollama | Ollama daemon not running | `systemctl start ollama` (or `systemctl --user start ollama`) |

Logs to check, in order:
1. `systemctl --user status morning-brief.service` — unit state
2. `journalctl --user -u morning-brief.service -n 50 --no-pager` — full errors

---

## Cost

- **Electricity.** Brief runs for ~1-2 minutes on CPU, once a day.
- **Disk.** One ~2GB model, plus a few KB of brief files per day.
- **Everything else.** Free.

No API keys, no subscriptions, no cloud egress.

---

## License

Do whatever you want with this. It's yours now.
# morning-brief
