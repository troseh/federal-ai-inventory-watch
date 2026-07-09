"""Page watcher: archives and diffs agency AI governance pages. Code v1.0."""

from __future__ import annotations

import difflib
import html
import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAGES_CONFIG = ROOT / "config" / "pages.yaml"
PAGES_DIR = ROOT / "data" / "pages"
MANUAL_DIR = ROOT / "data" / "manual"
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


def _xlsx_text(raw: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        s = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
        shared = [html.unescape(re.sub(r"<[^>]+>", "", m))
                  for m in re.findall(r"<si>(.*?)</si>", s, re.S)]
    lines = []
    for name in sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        xml = z.read(name).decode("utf-8", "replace")
        for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
            vals = []
            for cell in re.findall(r"<c\b[^>]*?(?:/>|>.*?</c>)", row, re.S):
                t = re.search(r'\bt="([^"]+)"', cell)
                v = re.search(r"<v>(.*?)</v>", cell, re.S)
                if v is None:
                    t2 = re.search(r"<t[^>]*>(.*?)</t>", cell, re.S)
                    vals.append(html.unescape(t2.group(1)) if t2 else "")
                    continue
                val = html.unescape(v.group(1))
                if t and t.group(1) == "s":
                    try:
                        val = shared[int(val)]
                    except (ValueError, IndexError):
                        pass
                vals.append(val)
            if any(x.strip() for x in vals):
                lines.append(" | ".join(x.strip() for x in vals).rstrip(" |"))
    return "\n".join(lines)


def extract_text(raw: bytes, kind: str) -> str:
    if kind == "xlsx":
        text = _xlsx_text(raw)
    elif kind == "pdf":
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
        if s.get("manual"):
            status = "manual (file unreadable)" if fails else "manual"
        else:
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
        pstate["manual"] = bool(p.get("manual"))
        pdir = PAGES_DIR / pid
        latest_path = pdir / "latest.txt"
        if p.get("manual"):
            mdir = MANUAL_DIR / pid
            files = sorted(f for f in mdir.glob("*") if f.is_file()) if mdir.exists() else []
            if not files:
                pstate["fail_streak"] = 0
                print(f"{pid}: no manual capture yet")
                continue
            try:
                raw = files[-1].read_bytes()
                text = extract_text(raw, p.get("kind", "html"))
            except Exception as exc:
                pstate["fail_streak"] = pstate.get("fail_streak", 0) + 1
                if pstate["fail_streak"] == 1:
                    events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                                  f"Manual file unreadable: `{files[-1].name}`: `{exc}`\n")
                print(f"{pid}: manual file unreadable ({exc})")
                continue
            pstate["fail_streak"] = 0
            old = latest_path.read_text(encoding="utf-8") if latest_path.exists() else None
            if old == text:
                print(f"{pid}: unchanged (manual)")
                continue
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"{today}-{files[-1].name}").write_bytes(raw)
            (pdir / f"{today}.txt").write_text(text, encoding="utf-8")
            latest_path.write_text(text, encoding="utf-8")
            pstate["last_changed"] = today
            if old is None:
                events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                              f"First manual capture archived (`{files[-1].name}`, "
                              f"{len(text)} chars of text).\n")
                print(f"{pid}: first manual capture")
            else:
                delta = len(text) - len(old)
                excerpt = "\n".join(_diff_excerpt(old, text))
                events.append(f"## {p['agency']} — {p['label']} (`{pid}`)\n\n"
                              f"Manual capture changed ({delta:+d} chars, `{files[-1].name}`). "
                              f"Archived versions in `data/pages/{pid}/`.\n\n"
                              f"```diff\n{excerpt}\n```\n")
                print(f"{pid}: manual capture changed ({delta:+d} chars)")
            continue
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
        kind = p.get("kind", "html")
        ext = {"pdf": "pdf", "html": "html", "xlsx": "xlsx"}.get(kind, "txt")
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
