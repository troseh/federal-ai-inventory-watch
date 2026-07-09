# federal-ai-inventory-watch

Continuous public change tracking for the U.S. federal AI use case inventory.

Federal agencies are required to inventory their AI use cases annually
(Advancing American AI Act, Pub. L. No. 117-263, div. G, title LXXII,
subtitle B). OMB consolidates the agency inventories into public CSVs
([2025 repository](https://github.com/ombegov/2025-Federal-Agency-AI-Use-Case-Inventory))
and updates them on a rolling basis. The updates arrive without a changelog.
This project watches the consolidated file and publishes:

- **A dated changelog** (`changelogs/`): use cases added, removed, and
  changed, with field-level detail. Changes to the nine minimum-practice
  reporting fields on high-impact use cases appear in their own section.
- **A determinations ledger** (`data/ledgers/determinations.csv`): every
  movement into or out of the high-impact tier, as a time series — including
  use cases that enter the inventory already determined out of the presumed
  high-impact category.
- **A weekly statistical summary** (`data/SUMMARY.md`): counts of published
  values — status, stage, high-impact by agency, determinations by agency,
  minimum-practice reporting restricted to deployed high-impact use cases,
  vendors named on high-impact use cases, and withheld flags.
- **Raw snapshots** (`data/snapshots/`): an archive of each fetched version
  of the source file, independent of the source repository's fate.

Under OMB Memorandum M-25-21, a use case presumed high-impact may be
determined not high-impact by an agency official, which removes it from the
minimum risk-management practices. Each determination is published as a
status value in a single year's file. The ledger records those values across
files, over time.

## Scope

Every changelog line, ledger row, and summary figure is produced from the
source files by the rules stated in Methodology, and each run's input is
archived in `data/snapshots/`, so any output can be re-derived from the
snapshots that produced it. The pipeline contains one judgment lane,
ambiguous identity matches, and every candidate in it lands in
`data/needs_review.csv` and the changelog for a human call.

## Reading the ledger

Ledger columns: `date, uid, agency, name, from, to`. A row records that the
published status of a use case changed between two snapshot dates, or that
a use case first appeared already determined out of the presumed tier.
Where the source files include a justification for a determination, it is
preserved in the raw snapshot for that date.

## Reading the summary

All summary figures are counts of values as published. Two calibration
points for the minimum-practice tables: the practices apply to deployed
high-impact AI, so the tables are restricted to use cases whose published
stage is deployed, with the restricted count stated in the heading; and at
least one agency states that empty cells reflect data not collected per OMB
guidance, so blank counts are reported as blanks, without further reading.
Pre-existing deployed high-impact use cases had until April 3, 2026 to
implement the practices or discontinue use, subject to extensions and
waivers (OMB M-25-21).

## Run behavior

The workflow runs Mondays and on manual dispatch. If the fetched source
file is byte-identical to the last archived snapshot, the run exits without
writing. If the file changed but no field-level differences survive
normalization, the canonical state and summary refresh without a changelog.
A changelog is written only when there is something to report.

## Setup

1. Create a public GitHub repository and upload these files.
2. Settings → Actions → General → Workflow permissions → read and write.
3. Trigger the workflow once from the Actions tab. On a schema mismatch it
   prints the live file's actual headers; edit `config/schemas.yaml` to
   match them exactly and rerun. The first successful run seeds the
   baseline snapshot, ledger, and summary.
4. When OMB publishes a new inventory year: add a schema block to
   `config/schemas.yaml`, update `source.url`, and flip `schema_year`.
   Identity matching carries rows across the transition.

Local test (no network needed): `python tests/run_test.py`

## Methodology, v0.1 (code v1.0)

Identity across snapshots is assigned by rule, in order:

1. **Exact**: identical use case ID.
2. **Rename**: within the same agency, name similarity ≥ 0.85
   (`difflib.SequenceMatcher` on casefolded, whitespace-collapsed names),
   assigned greedily from highest ratio down, one-to-one.
3. **Review**: pairs scoring 0.70–0.85 go to `data/needs_review.csv` and the
   changelog for a human call.
4. Everything else is an addition or removal.

Rows published without a use case ID receive a synthetic ID from
agency + name. A **declassification** is any matched pair whose status
moves from high-impact to another value, or any row whose first appearance
is already in the presumed-but-determined-not category. Status values are
normalized by rule: values containing "presumed" map to declassified, then
"not high" to not-high-impact, then "high" to high-impact; empty and N/A
map to unstated. Stage values are bucketed the same way (pre-deployment,
deployed, pilot, retired). Threshold or rule changes bump the methodology
version here and in `src/watch.py`.

## Known characteristics of the source data

These are properties of the published files, recorded here so summary
readers can interpret the counts: some use cases carry no status value;
vendor names are not normalized across entries (the same vendor can appear
under multiple spellings); `hi_public_consultation` values are published as
list literals; and the inventory excludes the Department of Defense,
elements of the intelligence community, and non-public use cases.

## Corrections

If an entry here misstates what the source files show, open a GitHub issue
with the use case ID and the date. Confirmed errors are corrected in the
ledger with a note, and the original row is retained.

## Citation

If you use the ledger, changelogs, or summaries, cite this repository and
the snapshot date(s) the figures derive from. The underlying data is OMB's
consolidated federal AI use case inventory, cited separately.

## License and status

Maintained in a personal capacity as an exploratory research instrument.
