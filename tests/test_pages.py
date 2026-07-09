#!/usr/bin/env python3
"""Offline test for the page watcher. Run from repo root: python tests/test_pages.py"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import pages

SCRATCH = ROOT / "tests" / "_pscratch"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
pages.PAGES_DIR = SCRATCH / "data" / "pages"
pages.STATE_PATH = SCRATCH / "data" / "pages" / "state.json"
pages.STATUS_PATH = SCRATCH / "data" / "PAGES.md"
pages.CHANGELOG_DIR = SCRATCH / "changelogs"

CONFIG = [
    {"id": "alpha", "agency": "AAA", "label": "Alpha plan", "url": "http://x/a", "kind": "html"},
    {"id": "beta", "agency": "BBB", "label": "Beta plan", "url": "http://x/b", "kind": "html"},
    {"id": "gamma", "agency": "CCC", "label": "Gamma inventory", "url": "http://x/c", "kind": "text", "manual": True},
]
V1 = {"http://x/a": b"<html><body><h1>Plan</h1><p>We intend no waivers.</p></body></html>",
      "http://x/b": b"<html><body><p>Stable text.</p></body></html>"}
V2 = {"http://x/a": b"<html><body><h1>Plan</h1><p>One waiver was issued for system Z.</p></body></html>",
      "http://x/b": b"<html><body><p>Stable text.</p></body></html>"}

pages.MANUAL_DIR = SCRATCH / "data" / "manual"
pages.load_pages_config = lambda: CONFIG

(SCRATCH / "data" / "manual" / "gamma").mkdir(parents=True)
(SCRATCH / "data" / "manual" / "gamma" / "2026-07-01-inv.csv").write_text("id,name\n1,alpha system\n")

serve = V1
pages.fetch_bytes = lambda url, timeout=60: serve[url]
pages.run_live("2026-07-01")

serve = V2
(SCRATCH / "data" / "manual" / "gamma" / "2026-07-08-inv.csv").write_text("id,name\n1,alpha system\n2,beta system\n")
pages.run_live("2026-07-08")

log = (SCRATCH / "changelogs" / "pages-2026-07-08.md").read_text(encoding="utf-8")
status = (SCRATCH / "data" / "PAGES.md").read_text(encoding="utf-8")
print(log)

checks = {
    "change detected on alpha": "Alpha plan" in log and "Text changed" in log,
    "diff excerpt shows waiver line": "One waiver was issued" in log,
    "unchanged beta absent from changelog": "Beta plan" not in log,
    "status table has last-changed dates": "| alpha |" in status and "2026-07-08" in status,
    "both versions archived": (SCRATCH / "data/pages/alpha/2026-07-01.txt").exists()
                              and (SCRATCH / "data/pages/alpha/2026-07-08.txt").exists(),
    "manual capture diffed": "Gamma inventory" in log and "beta system" in log,
    "manual status shown": "| gamma |" in status and "manual" in status,
}
failed = [k for k, ok in checks.items() if not ok]
for k, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + k)
if failed:
    sys.exit(f"{len(failed)} failed")
print("\nAll page-watch checks passed.")
