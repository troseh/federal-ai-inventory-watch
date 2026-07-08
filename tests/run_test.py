#!/usr/bin/env python3
"""Offline end-to-end test. Run from the repo root: python tests/run_test.py"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import watch

SCRATCH = ROOT / "tests" / "_scratch"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
for attr, rel in [("SNAPSHOT_DIR", "data/snapshots"),
                  ("CANONICAL_PATH", "data/canonical/latest.csv"),
                  ("LEDGER_PATH", "data/ledgers/determinations.csv"),
                  ("REVIEW_PATH", "data/needs_review.csv"),
                  ("CHANGELOG_DIR", "changelogs"),
                  ("INDEX_PATH", "CHANGELOG.md")]:
    setattr(watch, attr, SCRATCH / rel)

old_text = (ROOT / "tests/fixtures/old.csv").read_text(encoding="utf-8")
new_text = (ROOT / "tests/fixtures/new.csv").read_text(encoding="utf-8")

assert watch.run_pipeline(old_text, "2026-07-01") is None
path = watch.run_pipeline(new_text, "2026-07-08")
assert path is not None
log = path.read_text(encoding="utf-8")
print("\n----- generated changelog -----\n")
print(log)
print("----- end changelog -----\n")

summary = (SCRATCH / "data" / "SUMMARY.md").read_text(encoding="utf-8")
ledger = (SCRATCH / "data/ledgers/determinations.csv").read_text(encoding="utf-8")

checks = {
    "declassification detected (HHS-0001)":
        "high-impact → declassified" in log,
    "rename matched across uid change (VA-0003 → VA-0088)":
        "matched by rename@" in log and "Claims Documents Classifier v2" in log,
    "stage change captured (SSA-0005)":
        "stage: Pre-Deployment → Pilot" in log,
    "removal detected (TREAS-0004)":
        "Refund Anomaly Detector" in log and "## Removed" in log,
    "additions detected (ED-0007, USDA-0008)":
        "SNAP Document Verifier" in log,
    "first-appearance declassification flagged (ED-0007)":
        "entered the inventory already determined out" in log,
    "practice change surfaced in dedicated section (VA)":
        "Minimum-practice reporting changes" in log and
        "hi_ongoing_monitoring: In-progress → Yes - Monitoring Established" in log,
    "ledger has both declassification rows":
        ledger.count("declassified") >= 2 and "HHS-0001" in ledger and "ED-0007" in ledger,
    "summary conditions practices on deployed stage":
        "Minimum-practice reporting among deployed high-impact use cases" in summary,
    "summary has stage table":
        "## Stage (all use cases)" in summary,
    "ambiguous DOL pair surfaced, not swallowed":
        "Grant" in log,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)
if failed:
    sys.exit(f"\n{len(failed)} check(s) failed.")
print("\nAll checks passed.")
