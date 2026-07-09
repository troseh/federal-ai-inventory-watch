"""Page watcher: archives and diffs agency AI governance pages. Code v1.0."""

from __future__ import annotations

import difflib
import json
import re
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAGES_CONFIG = ROOT / "config" / "pages.yaml"
PAGES_DIR = ROOT / "data" / "pages"
STATE_PATH = ROOT / "data" / "pages" / "state.json"
STATUS_PATH = ROOT / "data" / "PAGES.md"
CHANGELOG_DIR = ROOT / "changelogs"


def load_pages_config() -> list[dict]:
    with open(PAGES_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["pages"]


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "inventory-watch-pages/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class _TextHTML(HTMLParser):
    SKIP = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.chunks.append(data.strip())


def extract_text(raw: bytes, kind: str) -> str:
    if kind == "pdf":
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif kind == "html":
        parser = _TextHTML()
        parser.feed(raw.decode("utf-8", errors="replace"))
        text = "\n".join(parser.chunks)
    else:
        text = raw.decode("utf-8", errors="replace")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")


def _diff_excerpt(old: str, new: str, limit: int = 40) -> list[str]:
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(),
                                lineterm="", n=1)
    out = []
    for i, line in enumerate(diff):
        if i >= limit:
            out.append(f"... (diff truncated at {limit} lines)")
            break
        out.append(line)
    return out


def write_status(pages: list[dict], state: dict) -> None:
    lines = ["# Watched pages", "",
             "Agency AI governance pages under watch. `last changed` is the most "
             "recent date the extracted text of the page differed from the prior "
             "archived version. Archived versions are in `data/pages/<id>/`.", "",
             "| id | agency | page | last changed | status |",
             "| --- | --- | --- | --- | --- |"]
    for p in pages:
        s = state.get(p["id"], {})
        last = s.get("last_changed", "(no capture yet)")
        fails = s.get("fail_streak", 0)
        status = f"unreachable ×{fails}" if fails else "ok"
        lines.append(f"| {p['id']} | {p['agency']} | [{p['label']}]({p['url']}) "
                     f"| {last} | {status} |")
    text = "\n".join(lines) + "\n"
    if not STATUS_PATH.exists() or STATUS_PATH.read_text(encoding="utf-8") != text:
        STATUS_PATH.write_text(text, encoding="utf-8")


def run_live(today: str | None = None) -> None:
    today = today or date.today().isoformat()
    pages = load_pages_config()
    state = load_state()
    events: list[str] = []

    for p in pages:
        pid = p["id"]
        pstate = state.setdefault(pid, {})
        pdir = PAGES_DIR / pid
        latest_path = pdir / "latest.txt"
        try:
            raw = fetch_bytes(p["url"])
            text = extract_text(raw, p.get("kind", "html"))
        except Exception as exc:
            pstate["fail_streak"] = pstate.get("fail_streak", 0) + 1
            if pstate["fail_streak"] == 1:
                events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                              f"Unreachable: `{exc}`\n")
            print(f"{pid}: unreachable ({exc})")
            continue

        was_failing = pstate.get("fail_streak", 0) > 0
        pstate["fail_streak"] = 0
        if was_failing:
            events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                          "Reachable again.\n")

        old = latest_path.read_text(encoding="utf-8") if latest_path.exists() else None
        if old == text:
            print(f"{pid}: unchanged")
            continue

        pdir.mkdir(parents=True, exist_ok=True)
        ext = "pdf" if p.get("kind") == "pdf" else "html" if p.get("kind", "html") == "html" else "txt"
        (pdir / f"{today}.{ext}").write_bytes(raw)
        (pdir / f"{today}.txt").write_text(text, encoding="utf-8")
        latest_path.write_text(text, encoding="utf-8")

        if old is None:
            pstate["last_changed"] = today
            events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                          f"First capture archived ({len(text)} chars of text).\n")
            print(f"{pid}: first capture")
        else:
            pstate["last_changed"] = today
            delta = len(text) - len(old)
            excerpt = "\n".join(_diff_excerpt(old, text))
            events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                          f"Text changed ({delta:+d} chars). Archived versions in "
                          f"`data/pages/{pid}/`.\n\n```diff\n{excerpt}\n```\n")
            print(f"{pid}: changed ({delta:+d} chars)")

    save_state(state)
    write_status(pages, state)

    if events:
        CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)
        path = CHANGELOG_DIR / f"pages-{today}.md"
        body = [f"# Watched-page changes — {today}", ""] + events
        path.write_text("\n".join(body), encoding="utf-8")
        print(f"Page changelog written: {path.relative_to(ROOT)}")
    else:
        print("No watched-page changes.")


if __name__ == "__main__":
    run_live()
