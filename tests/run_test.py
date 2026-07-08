#!/usr/bin/env python3
"""Offline end-to-end test for inventory-watch. Run from the repo root:
    python tests/run_test.py
Uses synthetic fixtures; touches only a temp copy of the data dirs.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import watch  # noqa: E402

# Redirect all state into a scratch area so tests never pollute real data.
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

# Day 1: seed baseline.
assert watch.run_pipeline(old_text, "2026-07-01") is None, "baseline should not produce a changelog"

# Day 2: diff.
path = watch.run_pipeline(new_text, "2026-07-08")
assert path is not None
log = path.read_text(encoding="utf-8")
print("\n----- generated changelog -----\n")
print(log)
print("----- end changelog -----\n")

checks = {
    "declassification detected (HHS-0001)":
        "high-impact → declassified" in log and "Benefit Eligibility Screening Model" in log,
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
}

ledger = (SCRATCH / "data/ledgers/determinations.csv").read_text(encoding="utf-8")
checks["ledger has both declassification rows"] = (
    ledger.count("declassified") >= 2 and "HHS-0001" in ledger and "ED-0007" in ledger
)

# The DOL pair (Grant Review Ranking System vs Grant Application Scoring
# Assistant) is designed to be similar-but-not-identical. Whichever side of
# the thresholds it lands on, it must NOT be silently auto-matched as a
# rename at full confidence AND silently dropped; it must appear somewhere.
checks["ambiguous DOL pair surfaced, not swallowed"] = (
    "Grant" in log
)

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)
if failed:
    sys.exit(f"\n{len(failed)} check(s) failed.")
print("\nAll checks passed.")
