"""Semantic diffing for the federal AI use case inventory. Methodology v0.1; code v1.0."""

from __future__ import annotations

import csv
import io
import os
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

CORE_FIELDS = ["uid", "agency", "bureau", "name", "stage",
               "impact_status", "description"]


def _provenance_path() -> Path:
    return CANONICAL_PATH.parent / "provenance.txt"


def _summary_path() -> Path:
    return CANONICAL_PATH.parent.parent / "SUMMARY.md"


def _read_provenance() -> str:
    p = _provenance_path()
    return p.read_text(encoding="utf-8").strip() if p.exists() else "(no prior snapshot recorded)"


def _write_provenance(label: str) -> None:
    p = _provenance_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(label + "\n", encoding="utf-8")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def fetch_csv(url: str, timeout: int = 120) -> str:
    headers = {"User-Agent": "inventory-watch/1.0"}
    if "api.github.com" in url:
        headers["Accept"] = "application/vnd.github.raw+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def archive_snapshot(text: str, today: str) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{today}.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def read_rows(text: str) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    return headers, [dict(r) for r in reader]


def schema_fields(cfg: dict) -> tuple[list[str], list[str]]:
    year = str(cfg["schema_year"])
    extra = cfg["schemas"][year].get("extra") or {}
    fields = CORE_FIELDS + [k for k in extra if k not in CORE_FIELDS]
    text_fields = list(cfg.get("text_fields") or ["description"])
    return fields, text_fields


def _stage_bucket(raw: str) -> str:
    s = _collapse(raw).casefold()
    if not s:
        return "(unstated)"
    if "pre-deploy" in s or "predeploy" in s:
        return "pre-deployment"
    if "deploy" in s:
        return "deployed"
    if "pilot" in s:
        return "pilot"
    if "retire" in s:
        return "retired"
    return s


def _norm_impact(raw: str, impact_map: dict) -> str:
    s = _collapse(raw).casefold()
    if not s or s in ("n/a", "na"):
        return "unstated"
    if s in impact_map:
        return impact_map[s]
    if "presumed" in s:
        return "declassified"
    if "not high" in s or s in ("no", "false"):
        return "not-high-impact"
    if "high" in s or s in ("yes", "true"):
        return "high-impact"
    return s


def normalize(rows: list[dict], headers: list[str], cfg: dict) -> list[dict]:
    year = str(cfg["schema_year"])
    schema = cfg["schemas"][year]
    core_map = {k: v for k, v in schema.items() if k in CORE_FIELDS}
    extra_map = schema.get("extra") or {}

    missing = [k for k, col in core_map.items() if col not in headers]
    if missing:
        wanted = {k: core_map[k] for k in missing}
        raise SystemExit(
            "Schema mapping failed for fields "
            f"{wanted}.\nActual headers were:\n  " + "\n  ".join(headers) +
            "\nEdit config/schemas.yaml so every mapped column matches a real "
            "header exactly, then rerun."
        )
    absent_extra = [k for k, col in extra_map.items() if col not in headers]
    if absent_extra:
        print(f"Note: extra fields not found in source and left empty: {absent_extra}")

    impact_map = {k.casefold(): v for k, v in cfg["impact_normalization"].items()}
    out = []
    for r in rows:
        rec = {f: _collapse(r.get(core_map[f], "")) for f in CORE_FIELDS}
        for f, col in extra_map.items():
            rec[f] = _collapse(r.get(col, ""))
        rec["impact_status"] = _norm_impact(rec["impact_status"], impact_map)
        if not rec["uid"]:
            rec["uid"] = f"synth::{rec['agency']}::{rec['name']}".casefold()
        out.append(rec)
    return out


@dataclass
class MatchResult:
    pairs: list[tuple[dict, dict, str]] = field(default_factory=list)
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


def diff_pairs(pairs, fields, text_fields):
    changes, tier_moves = [], []
    for old, new, how in pairs:
        delta = {}
        for f in fields:
            if f == "uid":
                continue
            a, b = old.get(f, ""), new.get(f, "")
            if a != b:
                delta[f] = (a, b)
        if delta:
            changes.append({"old": old, "new": new, "how": how, "delta": delta})
        if "impact_status" in delta:
            frm, to = delta["impact_status"]
            tier_moves.append({"uid": new["uid"], "agency": new["agency"],
                               "name": new["name"], "from": frm, "to": to})
    return changes, tier_moves


def _row_line(r: dict) -> str:
    return (f"- **{r['name']}** ({r['agency']}, `{r['uid']}`) — "
            f"{r['impact_status']}, {r.get('stage') or 'stage unstated'}")


def write_changelog(today, res, changes, tier_moves, first_seen_declassified,
                    prov_old, prov_new, text_fields):
    CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# Inventory changes — {today}", "",
             f"Derived from: `{prov_old}` → `{prov_new}`", ""]

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

    practice_changes = []
    for c in changes:
        hi_delta = {f: v for f, v in c["delta"].items() if f.startswith("hi_")}
        if hi_delta:
            practice_changes.append((c, hi_delta))
    if practice_changes:
        lines += [f"## Minimum-practice reporting changes ({len(practice_changes)})", ""]
        for c, hi_delta in practice_changes:
            lines.append(f"- **{c['new']['name']}** ({c['new']['agency']}, `{c['new']['uid']}`):")
            for f, (a, b) in hi_delta.items():
                if f in text_fields:
                    lines.append(f"  - {f}: text revised")
                else:
                    lines.append(f"  - {f}: {a or '(empty)'} → {b or '(empty)'}")
        lines.append("")

    if res.added:
        lines += [f"## Added ({len(res.added)})", ""]
        lines += [_row_line(r) for r in res.added] + [""]
    if res.removed:
        lines += [f"## Removed ({len(res.removed)})", ""]
        lines += [_row_line(r) for r in res.removed] + [""]

    other = [c for c in changes
             if {f for f in c["delta"]} - {"impact_status"} - {f for f in c["delta"] if f.startswith("hi_")}]
    if other:
        lines += [f"## Changed ({len(other)})", ""]
        for c in other:
            lines.append(f"- **{c['new']['name']}** ({c['new']['agency']}, "
                         f"`{c['new']['uid']}`, matched by {c['how']}):")
            for f, (a, b) in c["delta"].items():
                if f == "impact_status" or f.startswith("hi_"):
                    continue
                if f in text_fields:
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

    if len(lines) == 4:
        lines += ["No changes detected.", ""]

    path = CHANGELOG_DIR / f"{today}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def update_index(today, res, tier_moves):
    entry = (f"- [{today}](changelogs/{today}.md) — "
             f"{len(res.added)} added, {len(res.removed)} removed, "
             f"{len(tier_moves)} tier movement(s)")
    header = "# inventory-watch changelog index\n\n"
    existing = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else header
    INDEX_PATH.write_text(existing.rstrip() + "\n" + entry + "\n", encoding="utf-8")


def append_ledger(today, tier_moves, first_seen_declassified):
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


def write_review(res):
    if not res.review:
        return
    with open(REVIEW_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["old_uid", "old_name", "new_uid", "new_name", "agency", "ratio"])
        for o, n, ratio in res.review:
            w.writerow([o["uid"], o["name"], n["uid"], n["name"], o["agency"], f"{ratio:.3f}"])


def _count(rows, key):
    counts = {}
    for r in rows:
        v = r.get(key, "") or "(empty)"
        counts[v] = counts.get(v, 0) + 1
    return counts


def _md_counts(counts, limit=None):
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit:
        items = items[:limit]
    return [f"| {k} | {v} |" for k, v in items]


def write_summary(today, rows, fields, snapshot_label):
    lines = [f"# Inventory summary — {today}", "",
             f"Source snapshot: `{snapshot_label}` · {len(rows)} use cases", "",
             "All figures below are counts of values as published in the source file.", "",
             "## Status", "", "| status | count |", "| --- | --- |"]
    lines += _md_counts(_count(rows, "impact_status"))

    stage_counts = {}
    for r in rows:
        b = _stage_bucket(r.get("stage", ""))
        stage_counts[b] = stage_counts.get(b, 0) + 1
    lines += ["", "## Stage (all use cases)", "", "| stage | count |", "| --- | --- |"]
    lines += _md_counts(stage_counts)

    hi_rows = [r for r in rows if r["impact_status"] == "high-impact"]
    de_rows = [r for r in rows if r["impact_status"] == "declassified"]
    hi_deployed = [r for r in hi_rows if _stage_bucket(r.get("stage", "")) == "deployed"]

    lines += ["", f"## High-impact use cases by agency ({len(hi_rows)} total)", "",
              "| agency | count |", "| --- | --- |"]
    lines += _md_counts(_count(hi_rows, "agency"), limit=20)

    hi_stage = {}
    for r in hi_rows:
        b = _stage_bucket(r.get("stage", ""))
        hi_stage[b] = hi_stage.get(b, 0) + 1
    lines += ["", "## High-impact use cases by stage", "", "| stage | count |", "| --- | --- |"]
    lines += _md_counts(hi_stage)

    if de_rows:
        lines += ["", f"## Presumed high-impact, determined not ({len(de_rows)} total)", "",
                  "| agency | count |", "| --- | --- |"]
        lines += _md_counts(_count(de_rows, "agency"), limit=20)

    hi_fields = [f for f in fields if f.startswith("hi_")]
    if hi_fields and hi_rows:
        lines += ["", f"## Minimum-practice reporting among deployed high-impact use cases ({len(hi_deployed)} of {len(hi_rows)})", "",
                  "Under OMB M-25-21, the minimum risk-management practices apply to "
                  "deployed high-impact AI. Pre-existing deployed use cases had until "
                  "April 3, 2026 to implement the practices or discontinue use, subject "
                  "to extensions and waivers. Value counts below are restricted to "
                  "high-impact use cases whose published stage is deployed.", ""]
        for f in hi_fields:
            lines += [f"### {f}", "", "| value | count |", "| --- | --- |"]
            lines += _md_counts(_count(hi_deployed, f), limit=6)
            lines.append("")

    if "vendor" in fields and hi_rows:
        lines += ["## Vendors named on high-impact use cases", "",
                  "| vendor_name value | count |", "| --- | --- |"]
        lines += _md_counts(_count(hi_rows, "vendor"), limit=20)
        lines.append("")

    if "withheld" in fields:
        lines += ["## is_withheld values", "", "| value | count |", "| --- | --- |"]
        lines += _md_counts(_count(rows, "withheld"))
        lines.append("")

    path = _summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def save_canonical(rows, fields):
    CANONICAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CANONICAL_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows({f: r.get(f, "") for f in fields} for r in rows)


def load_canonical(fields):
    if not CANONICAL_PATH.exists():
        return None
    with open(CANONICAL_PATH, newline="", encoding="utf-8") as fh:
        rows = [dict(r) for r in csv.DictReader(fh)]
    for r in rows:
        for f in fields:
            r.setdefault(f, "")
    return rows


def run_pipeline(new_text, today=None, snapshot_label=None):
    cfg = load_config()
    today = today or date.today().isoformat()
    snapshot_label = snapshot_label or f"data/snapshots/{today}.csv"
    fields, text_fields = schema_fields(cfg)
    headers, raw_rows = read_rows(new_text)
    new_rows = normalize(raw_rows, headers, cfg)

    old_rows = load_canonical(fields)
    if old_rows is None:
        save_canonical(new_rows, fields)
        _write_provenance(snapshot_label)
        declass = [r for r in new_rows if r["impact_status"] == "declassified"]
        append_ledger(today, [], declass)
        write_summary(today, new_rows, fields, snapshot_label)
        counts = _count(new_rows, "impact_status")
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        print(f"Baseline seeded: {len(new_rows)} use cases "
              f"({len(declass)} already determined out of the presumed tier).")
        print(f"Status counts: {summary}")
        return None

    m = cfg["matching"]
    res = match(old_rows, new_rows, m["rename_threshold"], m["review_threshold"])
    changes, tier_moves = diff_pairs(res.pairs, fields, text_fields)
    first_seen_declassified = [r for r in res.added if r["impact_status"] == "declassified"]

    nothing = not (res.added or res.removed or changes or res.review)
    if nothing:
        save_canonical(new_rows, fields)
        write_summary(today, new_rows, fields, snapshot_label)
        _write_provenance(snapshot_label)
        print("No field-level changes detected; state refreshed, no changelog written.")
        return None

    prov_old = _read_provenance()
    path = write_changelog(today, res, changes, tier_moves,
                           first_seen_declassified, prov_old, snapshot_label, text_fields)
    update_index(today, res, tier_moves)
    append_ledger(today, tier_moves, first_seen_declassified)
    write_review(res)
    save_canonical(new_rows, fields)
    write_summary(today, new_rows, fields, snapshot_label)
    _write_provenance(snapshot_label)
    print(f"Changelog written: {path.relative_to(ROOT)}")
    return path


def run_live():
    cfg = load_config()
    today = date.today().isoformat()
    text = fetch_csv(cfg["source"]["url"])
    prev_label = _read_provenance()
    prev_path = ROOT / prev_label
    if prev_path.is_file() and prev_path.read_text(encoding="utf-8") == text:
        print("Source file unchanged since last snapshot; nothing to do.")
        return
    snap = archive_snapshot(text, today)
    try:
        label = str(snap.relative_to(ROOT))
    except ValueError:
        label = str(snap)
    run_pipeline(text, today, label)


def inspect():
    cfg = load_config()
    text = fetch_csv(cfg["source"]["url"])
    headers, rows = read_rows(text)
    print(f"Fetched {len(rows)} rows. Headers:")
    for h in headers:
        print(f"  {h!r}")


if __name__ == "__main__":
    if "--inspect" in sys.argv:
        inspect()
    else:
        run_live()
