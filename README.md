# inventory-watch

Continuous, public change tracking for the U.S. federal AI use case inventory.

OMB consolidates agency AI use case inventories into public CSVs
([2025 repository](https://github.com/ombegov/2025-Federal-Agency-AI-Use-Case-Inventory))
and updates them on a rolling basis. No changelog accompanies those updates.
This project watches the consolidated file and publishes, weekly:

- **A dated changelog** (`changelogs/`): use cases added, removed, and changed,
  with field-level detail.
- **A determinations ledger** (`data/ledgers/determinations.csv`): every
  movement into or out of the high-impact tier, cumulatively, over time —
  including systems that enter the inventory already determined out of the
  presumed high-impact category.
- **Raw snapshots** (`data/snapshots/`): a durable archive of each fetched
  version of the source file, independent of the source repository's fate.

The determinations ledger is the point. "High-impact" is a determination
before it is a description: under OMB M-25-21, an agency official may
determine that a use case presumed high-impact is not, which removes it from
the minimum risk-management practices. Those determinations are procedural
acts recorded nowhere as a time series. This ledger is that time series.

## What this project does not do

It reports what OMB's own published files say changed. It does not score,
rate, or evaluate any system, and it makes no claim about whether any system
serves its purpose. Interpretive layers, if any, will live in a separate
project with their own documented methodology.

## Setup (one time, ~15 minutes)

1. Create a **public GitHub repository** and upload these files.
2. Run `python run.py --inspect` (locally, or trigger the Action once and
   read the log). It prints the live CSV's actual column headers.
3. Edit `config/schemas.yaml` so each mapped column matches a real header
   **exactly**. The pipeline refuses to run on a partial mapping and names
   the fields that failed.
4. Run `python run.py --run` once to seed the baseline snapshot. Commit.
5. The included GitHub Action (`.github/workflows/watch.yml`) then runs
   every Monday and commits any changes it finds. It can also be triggered
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
3. **Review**: pairs scoring 0.70–0.85 are never auto-decided; they are
   written to `data/needs_review.csv` and listed in the changelog for a
   human call.
4. Everything else is an addition or removal.

Rows published without a use case ID receive a synthetic ID from
agency + name. A **declassification** is any matched pair whose status moves
from high-impact to any other value, or any row whose first appearance is
already "presumed high-impact, but determined not high-impact."

Threshold or rule changes bump the methodology version in `src/watch.py`
and are noted here. Known limits inherited from the source data: the
inventory excludes the Department of Defense, elements of the intelligence
community, and non-public use cases; this project can only see what agencies
publish.

## Corrections

If an agency or member of the public believes an entry here misstates what
the source files show, open a GitHub issue with the use case ID and the
date. Confirmed errors are corrected in the ledger with a note, not silently
overwritten.

## License and status

Maintained in a personal capacity. Add a LICENSE file before publishing
(MIT suggested).
