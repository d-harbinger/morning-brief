"""
Morning Brief — web UI for editing config.yaml and triggering runs.

Runs on http://127.0.0.1:4747 (localhost only — do not expose to network).

Usage:
    python webui.py
    # or: ./brief-web.sh

Open http://localhost:4747 in your browser.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import yaml
from flask import Flask, jsonify, redirect, render_template_string, request, url_for


HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"
TIMER_SOURCE = HERE / "systemd" / "morning-brief-daily.timer"
TIMER_INSTALLED = Path.home() / ".config" / "systemd" / "user" / "morning-brief-daily.timer"
PORT = 4747
HOST = "127.0.0.1"

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers

def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict) -> None:
    # Dump with reasonable formatting — preserve block literals for 'interests'
    class LiteralStr(str):
        pass

    def literal_representer(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")

    yaml.add_representer(LiteralStr, literal_representer)

    # Wrap interests as literal block for readability
    if "interests" in config and isinstance(config["interests"], str):
        config["interests"] = LiteralStr(config["interests"])

    with CONFIG_PATH.open("w") as f:
        yaml.dump(config, f, sort_keys=False, allow_unicode=True, default_flow_style=False)


def ollama_models() -> list[str]:
    """Query Ollama for installed models. Returns [] if unreachable."""
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Schedule (systemd timer) management

import re as _re

_ONCALENDAR_RE = _re.compile(r"^\s*OnCalendar\s*=\s*\*-\*-\*\s+(\d{2}):(\d{2})(?::\d{2})?\s*$")


def read_schedule() -> list[str]:
    """Return list of 'HH:MM' times from the daily timer file, or []."""
    for path in (TIMER_INSTALLED, TIMER_SOURCE):
        if path.exists():
            times = []
            for line in path.read_text().splitlines():
                m = _ONCALENDAR_RE.match(line)
                if m:
                    times.append(f"{m.group(1)}:{m.group(2)}")
            if times:
                return times
    return []


def write_schedule(times: list[str]) -> dict:
    """Rewrite the daily timer with the given 'HH:MM' list. Sync + reload systemd.

    Returns {'ok': bool, 'message': str, 'installed': bool}.
    """
    # Validate
    clean: list[str] = []
    for t in times:
        t = t.strip()
        m = _re.match(r"^(\d{1,2}):(\d{2})$", t)
        if not m:
            return {"ok": False, "message": f"Bad time format: {t!r}. Use HH:MM."}
        hh, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return {"ok": False, "message": f"Time out of range: {t}"}
        clean.append(f"{hh:02d}:{mm:02d}")
    if not clean:
        return {"ok": False, "message": "At least one time is required."}

    oncalendar_lines = "\n".join(f"OnCalendar=*-*-* {t}:00" for t in clean)
    unit_body = (
        "[Unit]\n"
        "Description=Morning Brief — daily catch-up trigger\n"
        "\n"
        "[Timer]\n"
        f"{oncalendar_lines}\n"
        "Persistent=true\n"
        "Unit=morning-brief.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )

    TIMER_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    TIMER_SOURCE.write_text(unit_body)

    installed = False
    if TIMER_INSTALLED.exists() or TIMER_INSTALLED.parent.exists():
        try:
            TIMER_INSTALLED.parent.mkdir(parents=True, exist_ok=True)
            TIMER_INSTALLED.write_text(unit_body)
            installed = True
        except Exception as e:
            return {"ok": False, "message": f"Wrote source but could not update "
                                             f"installed unit: {e}"}

    # Reload + restart timer so the new schedule takes effect
    if installed:
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"],
                           check=True, capture_output=True, text=True, timeout=10)
            subprocess.run(["systemctl", "--user", "restart", "morning-brief-daily.timer"],
                           check=True, capture_output=True, text=True, timeout=10)
        except subprocess.CalledProcessError as e:
            return {"ok": False, "message": f"systemctl failed: {e.stderr.strip() or e}"}
        except FileNotFoundError:
            return {"ok": False, "message": "systemctl not found on PATH."}

    msg = f"Saved {len(clean)} time(s)."
    if not installed:
        msg += " Source file updated; run ./install.sh to activate on systemd."
    return {"ok": True, "message": msg, "installed": installed}


# ---------------------------------------------------------------------------
# Routes

@app.get("/")
def index():
    config = load_config()
    models = ollama_models()
    schedule = read_schedule()
    return render_template_string(
        TEMPLATE,
        config=config,
        models=models,
        schedule=schedule,
        schedule_installed=TIMER_INSTALLED.exists(),
        config_json=json.dumps(config, indent=2),
    )


@app.post("/schedule")
def save_schedule_route():
    data = request.get_json() or {}
    times = data.get("times") or []
    result = write_schedule(times)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.post("/save")
def save():
    data = request.get_json() or {}
    config = load_config()

    # Patch only known top-level fields
    if "model" in data:
        config.setdefault("ollama", {})["model"] = data["model"].strip()
    if "interests" in data:
        config["interests"] = data["interests"].strip() + "\n"
    if "lookback_hours" in data:
        config["lookback_hours"] = int(data["lookback_hours"])
    if "per_feed_limit" in data:
        config["per_feed_limit"] = int(data["per_feed_limit"])
    if "max_digest_items" in data:
        config["max_digest_items"] = int(data["max_digest_items"])
    if "feeds" in data:
        clean_feeds = []
        for f in data["feeds"]:
            name = (f.get("name") or "").strip()
            url = (f.get("url") or "").strip()
            if not (name and url):
                continue
            entry: dict = {"name": name, "url": url}
            limit_raw = f.get("limit")
            if limit_raw not in (None, "", "null"):
                try:
                    entry["limit"] = int(limit_raw)
                except (TypeError, ValueError):
                    pass
            clean_feeds.append(entry)
        config["feeds"] = clean_feeds

    save_config(config)
    return jsonify({"ok": True})


@app.post("/generate")
def generate():
    """Kick off a brief generation in the background; return immediately."""
    python_exe = str(HERE / ".venv" / "bin" / "python")
    if not Path(python_exe).exists():
        python_exe = sys.executable

    proc = subprocess.Popen(
        [python_exe, str(HERE / "brief.py"), "--no-open"],
        cwd=str(HERE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return jsonify({"ok": True, "pid": proc.pid})


@app.get("/brief/today")
def brief_today():
    """Redirect to today's HTML brief if it exists."""
    import datetime as dt
    today = dt.date.today().isoformat()
    html_path = HERE / "output" / f"brief-{today}.html"
    if not html_path.exists():
        return ("No brief for today yet — hit Generate.", 404)
    # Serve the file inline
    return app.send_static_file(str(html_path)) if False else (
        html_path.read_text(), 200, {"Content-Type": "text/html; charset=utf-8"}
    )


# ---------------------------------------------------------------------------
# Template

TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morning Brief — Config</title>
<style>
  :root {
    --bg: #12141a;
    --bg-card: #1a1d26;
    --bg-input: #0e1016;
    --text: #e8e6e1;
    --text-dim: #8f8d87;
    --accent: #d4a574;
    --accent-hover: #e8bb86;
    --danger: #c47a6e;
    --border: #2a2e3a;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #faf8f4;
      --bg-card: #ffffff;
      --bg-input: #f5f2ec;
      --text: #1a1d26;
      --text-dim: #6b6862;
      --accent: #8b5a2b;
      --accent-hover: #6b4520;
      --danger: #a14a3a;
      --border: #e5e1d9;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2.5rem 1.5rem 5rem;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    font-size: 16px; line-height: 1.5;
  }
  main { max-width: 780px; margin: 0 auto; }
  header { border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 2rem; }
  .eyebrow { color: var(--accent); font-size: 0.75rem; letter-spacing: 0.15em;
    text-transform: uppercase; font-weight: 600; }
  h1 { margin: 0.3rem 0; font-size: 1.8rem; font-weight: 700; letter-spacing: -0.02em; }
  .sub { color: var(--text-dim); font-size: 0.9rem; }
  section { margin-bottom: 2rem; background: var(--bg-card); padding: 1.25rem 1.5rem;
    border-radius: 10px; border: 1px solid var(--border); }
  h2 { margin: 0 0 0.25rem; font-size: 1.1rem; }
  .hint { color: var(--text-dim); font-size: 0.85rem; margin-top: 0; margin-bottom: 1rem; }
  label { display: block; font-size: 0.8rem; color: var(--text-dim);
    margin-bottom: 0.3rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
  input[type=text], input[type=url], input[type=number], select, textarea {
    width: 100%; padding: 0.55rem 0.7rem;
    background: var(--bg-input); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px;
    font-family: inherit; font-size: 0.95rem;
  }
  input:focus, select:focus, textarea:focus {
    outline: none; border-color: var(--accent);
  }
  textarea { min-height: 8rem; resize: vertical; line-height: 1.45; }
  .row { display: grid; grid-template-columns: 170px 1fr 70px auto; gap: 0.5rem;
    align-items: center; margin-bottom: 0.5rem; }
  .row input { margin: 0; }
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
  button {
    padding: 0.55rem 1rem; border: 1px solid var(--accent);
    background: var(--accent); color: var(--bg);
    border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.9rem;
    font-family: inherit;
  }
  button:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
  button.ghost { background: transparent; color: var(--accent); }
  button.ghost:hover { background: var(--bg-input); }
  button.danger { background: transparent; border-color: transparent; color: var(--danger);
    padding: 0.3rem 0.5rem; font-size: 1.1rem; font-weight: 500; }
  button.danger:hover { background: var(--bg-input); }
  .actions { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 0.5rem; }
  .sticky-save {
    position: sticky; bottom: 1rem; background: var(--bg-card);
    border: 1px solid var(--accent); padding: 0.75rem 1rem;
    border-radius: 10px; display: flex; justify-content: space-between;
    align-items: center; gap: 1rem; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
  }
  .status { font-size: 0.85rem; color: var(--text-dim); }
  .status.ok { color: var(--accent); }
  .status.err { color: var(--danger); }
  .model-row { display: flex; gap: 0.5rem; }
  .model-row select, .model-row input { flex: 1; }
</style>
</head>
<body>
<main>

<header>
  <div class="eyebrow">Morning Brief</div>
  <h1>Configuration</h1>
  <div class="sub">Edits save to <code>config.yaml</code>. Next run picks them up.</div>
</header>

<section>
  <h2>Model</h2>
  <p class="hint">Which Ollama model the brief uses.
    {% if models %}Detected {{ models|length }} installed.{% else %}Ollama not reachable — enter model name manually.{% endif %}</p>
  <div class="model-row">
    <select id="model-select">
      {% for m in models %}
      <option value="{{ m }}" {% if m == config.get('ollama',{}).get('model') %}selected{% endif %}>{{ m }}</option>
      {% endfor %}
      <option value="__custom__">Other (type below)…</option>
    </select>
    <input id="model-custom" type="text" placeholder="e.g. qwen2.5:7b-instruct"
           value="{{ config.get('ollama',{}).get('model','') }}">
  </div>
</section>

<section>
  <h2>Interests</h2>
  <p class="hint">Free-text description of what you care about. Be specific. The LLM uses this as flavor when summarizing.</p>
  <textarea id="interests">{{ config.get('interests','') | trim }}</textarea>
</section>

<section>
  <h2>Limits</h2>
  <div class="grid3">
    <div>
      <label>Lookback hours</label>
      <input id="lookback_hours" type="number" min="1" max="168"
             value="{{ config.get('lookback_hours', 24) }}">
    </div>
    <div>
      <label>Per-feed cap</label>
      <input id="per_feed_limit" type="number" min="1" max="100"
             value="{{ config.get('per_feed_limit', 10) }}">
    </div>
    <div>
      <label>Max brief items</label>
      <input id="max_digest_items" type="number" min="1" max="50"
             value="{{ config.get('max_digest_items', 8) }}">
    </div>
  </div>
</section>

<section>
  <h2>Feeds</h2>
  <p class="hint">Any RSS or Atom URL works. <strong>Limit</strong> is optional — if blank, the default per-feed cap above applies. Use it to weight feeds.</p>
  <div class="row" style="font-size:0.72rem; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.3rem;">
    <span>Name</span><span>URL</span><span>Limit</span><span></span>
  </div>
  <div id="feeds">
    {% for feed in config.get('feeds', []) %}
    <div class="row feed-row">
      <input type="text" class="f-name" value="{{ feed.name }}" placeholder="Name">
      <input type="url" class="f-url" value="{{ feed.url }}" placeholder="https://…">
      <input type="number" class="f-limit" min="1" max="100" value="{{ feed.limit if feed.limit is not none else '' }}" placeholder="—">
      <button type="button" class="danger" onclick="this.closest('.row').remove()">×</button>
    </div>
    {% endfor %}
  </div>
  <div class="actions">
    <button class="ghost" type="button" onclick="addFeed()">+ Add feed</button>
  </div>
</section>

<section>
  <h2>Schedule</h2>
  <p class="hint">
    Times (24-hour, HH:MM) when the brief auto-generates each day.
    {% if not schedule_installed %}<br><strong>Note:</strong> systemd timer not installed yet — run <code>./install.sh</code> first to activate these.{% endif %}
  </p>
  <div id="schedule">
    {% for t in schedule %}
    <div class="row time-row" style="grid-template-columns: 1fr auto;">
      <input type="time" class="f-time" value="{{ t }}" step="60">
      <button type="button" class="danger" onclick="this.closest('.row').remove()">×</button>
    </div>
    {% endfor %}
    {% if not schedule %}
    <div class="row time-row" style="grid-template-columns: 1fr auto;">
      <input type="time" class="f-time" value="07:00" step="60">
      <button type="button" class="danger" onclick="this.closest('.row').remove()">×</button>
    </div>
    {% endif %}
  </div>
  <div class="actions">
    <button class="ghost" type="button" onclick="addTime()">+ Add time</button>
    <button type="button" onclick="saveSchedule()">Save schedule</button>
  </div>
</section>

<section>
  <h2>Actions</h2>
  <div class="actions">
    <button type="button" onclick="generateNow()">Generate brief now</button>
    <a href="/brief/today" target="_blank"><button class="ghost" type="button">View today's brief</button></a>
  </div>
</section>

<div class="sticky-save">
  <span class="status" id="status">Unsaved changes will be lost on reload.</span>
  <button type="button" onclick="saveAll()">Save</button>
</div>

</main>

<script>
function addFeed(name = "", url = "", limit = "") {
  const row = document.createElement("div");
  row.className = "row feed-row";
  row.innerHTML = `
    <input type="text" class="f-name" value="${name}" placeholder="Name">
    <input type="url" class="f-url" value="${url}" placeholder="https://…">
    <input type="number" class="f-limit" min="1" max="100" value="${limit}" placeholder="—">
    <button type="button" class="danger" onclick="this.closest('.row').remove()">×</button>
  `;
  document.getElementById("feeds").appendChild(row);
}

function currentConfig() {
  const sel = document.getElementById("model-select");
  const custom = document.getElementById("model-custom").value.trim();
  const model = sel.value === "__custom__" ? custom : sel.value;

  const feeds = Array.from(document.querySelectorAll(".feed-row")).map(r => {
    const lim = r.querySelector(".f-limit").value.trim();
    return {
      name: r.querySelector(".f-name").value.trim(),
      url: r.querySelector(".f-url").value.trim(),
      limit: lim === "" ? null : +lim,
    };
  }).filter(f => f.name && f.url);

  return {
    model,
    interests: document.getElementById("interests").value,
    lookback_hours: +document.getElementById("lookback_hours").value,
    per_feed_limit: +document.getElementById("per_feed_limit").value,
    max_digest_items: +document.getElementById("max_digest_items").value,
    feeds,
  };
}

function setStatus(msg, cls = "") {
  const s = document.getElementById("status");
  s.textContent = msg;
  s.className = "status " + cls;
}

async function saveAll() {
  const body = JSON.stringify(currentConfig());
  setStatus("Saving…");
  try {
    const r = await fetch("/save", { method: "POST",
      headers: { "Content-Type": "application/json" }, body });
    if (!r.ok) throw new Error(r.statusText);
    setStatus("Saved. Next run will use the new settings.", "ok");
  } catch (e) {
    setStatus("Save failed: " + e.message, "err");
  }
}

async function generateNow() {
  setStatus("Triggering generation (this takes a minute or two)…");
  try {
    const r = await fetch("/generate", { method: "POST" });
    if (!r.ok) throw new Error(r.statusText);
    setStatus("Generation started in the background. Click 'View today's brief' when done.", "ok");
  } catch (e) {
    setStatus("Generate failed: " + e.message, "err");
  }
}

function addTime(value = "12:00") {
  const row = document.createElement("div");
  row.className = "row time-row";
  row.style.gridTemplateColumns = "1fr auto";
  row.innerHTML = `
    <input type="time" class="f-time" value="${value}" step="60">
    <button type="button" class="danger" onclick="this.closest('.row').remove()">×</button>
  `;
  document.getElementById("schedule").appendChild(row);
}

async function saveSchedule() {
  const times = Array.from(document.querySelectorAll(".f-time"))
    .map(el => el.value).filter(v => v);
  if (times.length === 0) {
    setStatus("Add at least one time.", "err");
    return;
  }
  setStatus("Saving schedule…");
  try {
    const r = await fetch("/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ times }),
    });
    const result = await r.json();
    if (!r.ok || !result.ok) throw new Error(result.message || r.statusText);
    setStatus(result.message, "ok");
  } catch (e) {
    setStatus("Save failed: " + e.message, "err");
  }
}

// Sync custom model input with select
document.getElementById("model-select").addEventListener("change", (e) => {
  const custom = document.getElementById("model-custom");
  if (e.target.value !== "__custom__") custom.value = e.target.value;
});
</script>

</body>
</html>
"""


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"No config at {CONFIG_PATH}", file=sys.stderr)
        return 1

    print(f"Morning Brief web UI → http://{HOST}:{PORT}")
    print("Ctrl-C to stop.")
    app.run(host=HOST, port=PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
