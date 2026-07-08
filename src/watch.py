"""inventory-watch: semantic diffing for the federal AI use case inventory.

Pipeline stages:
  1. fetch      - download the current consolidated CSV, archive a raw snapshot
  2. normalize  - map the year's schema onto canonical fields
  3. match      - pair rows across snapshots (exact uid, then fuzzy within agency)
  4. diff       - field-level changes, additions, removals, tier movements
  5. report     - dated markdown changelog + cumulative determinations ledger

Methodology (v0.1, frozen; changes require a version bump in this docstring):
  - Exact match: identical normalized uid.
  - Rename match: within the same agency, name similarity >= rename_threshold
    (difflib SequenceMatcher on casefolded, whitespace-collapsed names),
    assigned greedily from highest ratio down, one-to-one.
  - Ambiguous: ratios in [review_threshold, rename_threshold) are never
    auto-decided; they are written to data/needs_review.csv.
  - A "declassification" is any matched pair whose canonical impact_status
    moves from high-impact to any other value, or whose status is
    "declassified" (presumed high-impact, determined not) on first appearance.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "schemas.yaml"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
CANONICAL_PATH = ROOT / "data" / "canonical" / "latest.csv"
LEDGER_PATH = ROOT / "data" / "ledgers" / "determinations.csv"
REVIEW_PATH = ROOT / "data" / "needs_review.csv"
CHANGELOG_DIR = ROOT / "changelogs"
INDEX_PATH = ROOT / "CHANGELOG.md"

CANONICAL_FIELDS = ["uid", "agency", "bureau", "name", "stage",
                    "impact_status", "description"]


# ----------------------------------------------------------------- config --

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ------------------------------------------------------------------ fetch --

def fetch_csv(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "inventory-watch/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def archive_snapshot(text: str, today: str) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{today}.csv"
    path.write_text(text, encoding="utf-8")
    return path


# -------------------------------------------------------------- normalize --

def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def read_rows(text: str) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    return headers, [dict(r) for r in reader]


def normalize(rows: list[dict], headers: list[str], cfg: dict) -> list[dict]:
    year = str(cfg["schema_year"])
    mapping = cfg["schemas"][year]
    missing = [k for k, col in mapping.items() if col not in headers]
    if missing:
        wanted = {k: mapping[k] for k in missing}
        raise SystemExit(
            "Schema mapping failed for fields "
            f"{wanted}.\nActual headers were:\n  " + "\n  ".join(headers) +
            "\nEdit config/schemas.yaml so every mapped column matches a real "
            "header exactly, then rerun. (`python run.py --inspect` prints "
            "headers without running the pipeline.)"
        )
    impact_map = {k.casefold(): v for k, v in cfg["impact_normalization"].items()}
    out = []
    for r in rows:
        rec = {f: _collapse(r.get(mapping[f], "")) for f in CANONICAL_FIELDS}
        raw_status = rec["impact_status"].casefold()
        rec["impact_status"] = impact_map.get(raw_status, rec["impact_status"] or "unstated")
        if not rec["uid"]:
            # Synthesize a stable uid for rows published without one.
            rec["uid"] = f"synth::{rec['agency']}::{rec['name']}".casefold()
        out.append(rec)
    return out


# ------------------------------------------------------------------ match --

@dataclass
class MatchResult:
    pairs: list[tuple[dict, dict, str]] = field(default_factory=list)  # (old, new, how)
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    review: list[tuple[dict, dict, float]] = field(default_factory=list)


def _name_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _collapse(a).casefold(), _collapse(b).casefold()).ratio()


def match(old: list[dict], new: list[dict], rename_t: float, review_t: float) -> MatchResult:
    res = MatchResult()
    old_by_uid = {r["uid"]: r for r in old}
    new_by_uid = {r["uid"]: r for r in new}

    for uid, n in new_by_uid.items():
        if uid in old_by_uid:
            res.pairs.append((old_by_uid[uid], n, "uid"))

    matched_old = {o["uid"] for o, _, _ in res.pairs}
    matched_new = {n["uid"] for _, n, _ in res.pairs}
    leftovers_old = [r for r in old if r["uid"] not in matched_old]
    leftovers_new = [r for r in new if r["uid"] not in matched_new]

    # Fuzzy rename pass, blocked by agency, greedy best-first, one-to-one.
    candidates = []
    for o in leftovers_old:
        for n in leftovers_new:
            if o["agency"].casefold() != n["agency"].casefold():
                continue
            ratio = _name_ratio(o["name"], n["name"])
            if ratio >= review_t:
                candidates.append((ratio, o, n))
    candidates.sort(key=lambda t: t[0], reverse=True)

    used_old, used_new = set(), set()
    for ratio, o, n in candidates:
        if o["uid"] in used_old or n["uid"] in used_new:
            continue
        if ratio >= rename_t:
            res.pairs.append((o, n, f"rename@{ratio:.2f}"))
            used_old.add(o["uid"]); used_new.add(n["uid"])
        else:
            res.review.append((o, n, ratio))

    res.removed = [r for r in leftovers_old if r["uid"] not in used_old]
    res.added = [r for r in leftovers_new if r["uid"] not in used_new]
    return res


# ------------------------------------------------------------------- diff --

def diff_pairs(pairs) -> tuple[list[dict], list[dict]]:
    """Return (field_changes, tier_moves)."""
    changes, tier_moves = [], []
    for old, new, how in pairs:
        delta = {f: (old[f], new[f]) for f in CANONICAL_FIELDS
                 if f != "uid" and old[f] != new[f]}
        if delta:
            changes.append({"old": old, "new": new, "how": how, "delta": delta})
        if "impact_status" in delta:
            frm, to = delta["impact_status"]
            tier_moves.append({"uid": new["uid"], "agency": new["agency"],
                               "name": new["name"], "from": frm, "to": to})
    return changes, tier_moves


# ----------------------------------------------------------------- report --

def _row_line(r: dict) -> str:
    return f"- **{r['name']}** ({r['agency']}, `{r['uid']}`) — {r['impact_status']}, {r['stage'] or 'stage unstated'}"


def write_changelog(today: str, res: MatchResult, changes, tier_moves,
                    first_seen_declassified) -> Path:
    CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# Inventory changes — {today}", ""]

    if tier_moves or first_seen_declassified:
        lines += ["## High-impact tier movements", ""]
        for m in tier_moves:
            arrow = "⬇" if m["from"] == "high-impact" else "⬆" if m["to"] == "high-impact" else "→"
            lines.append(f"- {arrow} **{m['name']}** ({m['agency']}, `{m['uid']}`): "
                         f"{m['from']} → {m['to']}")
        for r in first_seen_declassified:
            lines.append(f"- ⚑ **{r['name']}** ({r['agency']}, `{r['uid']}`): "
                         "entered the inventory already determined out of the "
                         "presumed high-impact tier")
        lines.append("")

    if res.added:
        lines += [f"## Added ({len(res.added)})", ""]
        lines += [_row_line(r) for r in res.added] + [""]
    if res.removed:
        lines += [f"## Removed ({len(res.removed)})", ""]
        lines += [_row_line(r) for r in res.removed] + [""]

    other = [c for c in changes if set(c["delta"]) - {"impact_status"}]
    if other:
        lines += [f"## Changed ({len(other)})", ""]
        for c in other:
            lines.append(f"- **{c['new']['name']}** ({c['new']['agency']}, "
                         f"`{c['new']['uid']}`, matched by {c['how']}):")
            for f, (a, b) in c["delta"].items():
                if f == "description":
                    lines.append(f"  - {f}: text revised")
                else:
                    lines.append(f"  - {f}: {a or '(empty)'} → {b or '(empty)'}")
        lines.append("")

    if res.review:
        lines += [f"## Needs human review ({len(res.review)})", "",
                  "Possible renames below the auto-match threshold; see "
                  "`data/needs_review.csv`.", ""]
        for o, n, ratio in res.review:
            lines.append(f"- {o['name']} ↔ {n['name']} ({o['agency']}, ratio {ratio:.2f})")
        lines.append("")

    if len(lines) == 2:
        lines += ["No changes detected.", ""]

    path = CHANGELOG_DIR / f"{today}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def update_index(today: str, res: MatchResult, tier_moves) -> None:
    entry = (f"- [{today}](changelogs/{today}.md) — "
             f"{len(res.added)} added, {len(res.removed)} removed, "
             f"{len(tier_moves)} tier movement(s)")
    header = "# inventory-watch changelog index\n\n"
    existing = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else header
    INDEX_PATH.write_text(existing.rstrip() + "\n" + entry + "\n", encoding="utf-8")


def append_ledger(today: str, tier_moves, first_seen_declassified) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LEDGER_PATH.exists()
    with open(LEDGER_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["date", "uid", "agency", "name", "from", "to"])
        for m in tier_moves:
            w.writerow([today, m["uid"], m["agency"], m["name"], m["from"], m["to"]])
        for r in first_seen_declassified:
            w.writerow([today, r["uid"], r["agency"], r["name"],
                        "(first appearance)", "declassified"])


def write_review(res: MatchResult) -> None:
    if not res.review:
        return
    with open(REVIEW_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["old_uid", "old_name", "new_uid", "new_name", "agency", "ratio"])
        for o, n, ratio in res.review:
            w.writerow([o["uid"], o["name"], n["uid"], n["name"], o["agency"], f"{ratio:.3f}"])


# ------------------------------------------------------------- state io ---

def save_canonical(rows: list[dict]) -> None:
    CANONICAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CANONICAL_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CANONICAL_FIELDS)
        w.writeheader()
        w.writerows(rows)


def load_canonical() -> list[dict] | None:
    if not CANONICAL_PATH.exists():
        return None
    with open(CANONICAL_PATH, newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


# ------------------------------------------------------------------ runs ---

def run_pipeline(new_text: str, today: str | None = None) -> Path | None:
    cfg = load_config()
    today = today or date.today().isoformat()
    headers, raw_rows = read_rows(new_text)
    new_rows = normalize(raw_rows, headers, cfg)

    old_rows = load_canonical()
    if old_rows is None:
        save_canonical(new_rows)
        declass = [r for r in new_rows if r["impact_status"] == "declassified"]
        append_ledger(today, [], declass)
        print(f"Baseline seeded: {len(new_rows)} use cases "
              f"({len(declass)} already determined out of the presumed tier).")
        return None

    m = cfg["matching"]
    res = match(old_rows, new_rows, m["rename_threshold"], m["review_threshold"])
    changes, tier_moves = diff_pairs(res.pairs)
    first_seen_declassified = [r for r in res.added if r["impact_status"] == "declassified"]

    path = write_changelog(today, res, changes, tier_moves, first_seen_declassified)
    update_index(today, res, tier_moves)
    append_ledger(today, tier_moves, first_seen_declassified)
    write_review(res)
    save_canonical(new_rows)
    print(f"Changelog written: {path.relative_to(ROOT)}")
    return path


def run_live() -> None:
    cfg = load_config()
    today = date.today().isoformat()
    text = fetch_csv(cfg["source"]["url"])
    archive_snapshot(text, today)
    run_pipeline(text, today)


def inspect() -> None:
    cfg = load_config()
    text = fetch_csv(cfg["source"]["url"])
    headers, rows = read_rows(text)
    print(f"Fetched {len(rows)} rows. Headers:")
    for h in headers:
        print(f"  {h!r}")
    print("\nCopy the exact header strings into config/schemas.yaml.")


if __name__ == "__main__":
    if "--inspect" in sys.argv:
        inspect()
    else:
        run_live()
