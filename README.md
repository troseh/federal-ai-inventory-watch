# federal-ai-inventory-watch

Continuous public change tracking for the U.S. federal AI use case inventory.

Federal agencies are required to inventory their AI use cases annually
(Advancing American AI Act, Pub. L. No. 117-263, div. G, title LXXII,
subtitle B). OMB consolidates the agency inventories into public CSVs
([2025 repository](https://github.com/ombegov/2025-Federal-Agency-AI-Use-Case-Inventory))
and updates them on a rolling basis. The updates arrive without a changelog.
This project watches the consolidated file and publishes, weekly:

- **A dated changelog** (`changelogs/`): use cases added, removed, and
  changed, with field-level detail.
- **A determinations ledger** (`data/ledgers/determinations.csv`): every
  movement into or out of the high-impact tier, as a time series — including
  systems that enter the inventory already determined out of the presumed
  high-impact category.
- **Raw snapshots** (`data/snapshots/`): an archive of each fetched version
  of the source file, independent of the source repository's fate.

Under OMB Memorandum M-25-21, a use case presumed high-impact may be
determined not high-impact by an agency official, which removes it from the
minimum risk-management practices. Each determination is published as a
status value in a single year's file. The ledger records those values across
files, over time.

## Scope

Every changelog line and ledger row is produced from the source files by the
rules stated in Methodology, and each run's input is archived in
`data/snapshots/`, so any output can be re-derived from the snapshots that
produced it. The pipeline contains one judgment lane — ambiguous identity
matches — and it is never auto-decided: candidates land in
`data/needs_review.csv` and are listed in the changelog for a human call.

## Reading the ledger

Ledger columns: `date, uid, agency, name, from, to`. A row records that the
published status of a use case changed between two snapshot dates. Where the
source files include a justification for a determination, it is preserved in
the raw snapshot for that date.

## Setup (one time, ~15 minutes)

1. Create a **public GitHub repository** and upload these files.
2. Run `python run.py --inspect` (locally, or trigger the Action once and
   read the log). It prints the live CSV's actual column headers.
3. Edit `config/schemas.yaml` so each mapped column matches a real header
   **exactly**. The pipeline refuses to run on a partial mapping and names
   the fields that failed.
4. Run `python run.py --run` once to seed the baseline snapshot. Commit.
5. The included GitHub Action (`.github/workflows/watch.yml`) runs every
   Monday and commits any changes it finds. It can also be triggered
   manually from the Actions tab.
6. When OMB publishes a new inventory year with a new schema: add a schema
   block to `config/schemas.yaml`, update `source.url`, and flip
   `schema_year`. Identity matching carries rows across the transition.

Local test (no network needed): `python tests/run_test.py`

## Methodology, v0.1

Identity across snapshots is assigned by rule, in order:

1. **Exact**: identical use case ID.
2. **Rename**: within the same agency, name similarity ≥ 0.85
   (`difflib.SequenceMatcher` on casefolded, whitespace-collapsed names),
   assigned greedily from highest ratio down, one-to-one.
3. **Review**: pairs scoring 0.70–0.85 go to `data/needs_review.csv` and the
   changelog for a human call.
4. Everything else is an addition or removal.

Rows published without a use case ID receive a synthetic ID from
agency + name. A **declassification** is any matched pair whose status moves
from high-impact to another value, or any row whose first appearance is
already "presumed high-impact, but determined not high-impact."

Threshold or rule changes bump the methodology version here and in
`src/watch.py`. Limits inherited from the source data: the inventory
excludes the Department of Defense, elements of the intelligence community,
and non-public use cases; this project sees what agencies publish.

## Corrections

If an entry here misstates what the source files show, open a GitHub issue
with the use case ID and the date. Confirmed errors are corrected in the
ledger with a note, and the original row is retained.

## License and status

Maintained in a personal capacity.
