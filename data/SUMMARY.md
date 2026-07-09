# Inventory summary — 2026-07-09

Source snapshot: `data/snapshots/2026-07-09.csv` · 3611 use cases

All figures below are counts of values as published in the source file.

## Status

| status | count |
| --- | --- |
| not-high-impact | 2630 |
| high-impact | 445 |
| unstated | 426 |
| declassified | 110 |

## Stage (all use cases)

| stage | count |
| --- | --- |
| pre-deployment | 1479 |
| deployed | 1040 |
| pilot | 440 |
| (unstated) | 338 |
| retired | 314 |

## High-impact use cases by agency (445 total)

| agency | count |
| --- | --- |
| VA | 215 |
| DOJ | 114 |
| DHS | 55 |
| DOE | 29 |
| SSA | 9 |
| NCUA | 5 |
| TREAS | 4 |
| USDA | 4 |
| STATE | 3 |
| EPA | 2 |
| HHS | 2 |
| DOL | 1 |
| FDIC | 1 |
| NASA | 1 |

## High-impact use cases by stage

| stage | count |
| --- | --- |
| deployed | 227 |
| pre-deployment | 140 |
| retired | 55 |
| pilot | 23 |

## Presumed high-impact, determined not (110 total)

| agency | count |
| --- | --- |
| DHS | 49 |
| DOJ | 32 |
| HHS | 13 |
| DOE | 5 |
| NASA | 3 |
| TREAS | 3 |
| STB | 2 |
| USDA | 2 |
| EPA | 1 |

## Minimum-practice reporting among deployed high-impact use cases (227 of 445)

Under OMB M-25-21, the minimum risk-management practices apply to deployed high-impact AI. Pre-existing deployed use cases had until April 3, 2026 to implement the practices or discontinue use, subject to extensions and waivers. Value counts below are restricted to high-impact use cases whose published stage is deployed.

### hi_assessment_completed

| value | count |
| --- | --- |
| (empty) | 101 |
| In-progress | 90 |
| Yes | 36 |

### hi_testing_conducted

| value | count |
| --- | --- |
| (empty) | 102 |
| In-progress | 81 |
| Yes | 44 |

### hi_potential_impacts

| value | count |
| --- | --- |
| (empty) | 102 |
| Consistent with Executive Orders and OMB guidance, the case owner relied on DOJ AI governance practices to evaluate impacts and risks. | 73 |
| The key risk is the degradation of the TVS verification to degrade overtime based on the parameters of assessment for comparing images to templates. The facial recognition does not enter or retrieve data, it is only comparative. | 7 |
| The AI-enabled facial recognition service may return too many candidates, resulting in the collection of irrelevant personal information. Mitigation: The service only returns candidates meeting a set confidence score threshold, ranking results by highest confidence. Potential matches are used as investigative leads and require full validation through the investigative process. | 4 |
| In-Progress - potential impacts will be identified during AI Impact Assessment. | 3 |
| None Identified | 2 |

### hi_independent_review

| value | count |
| --- | --- |
| (empty) | 102 |
| In-progress | 89 |
| CAIO Review | 31 |
| Internal Independent Review | 4 |
| Oversight Board Review | 1 |

### hi_ongoing_monitoring

| value | count |
| --- | --- |
| (empty) | 102 |
| In-progress | 85 |
| Yes - Monitoring Established | 40 |

### hi_training_established

| value | count |
| --- | --- |
| (empty) | 102 |
| Training In-progress | 81 |
| Training Established | 41 |
| b) Development of monitoring protocols is in-progess | 2 |
| a) Yes, sufficient monitoring protocols have been established | 1 |

### hi_failsafe_presence

| value | count |
| --- | --- |
| (empty) | 101 |
| In-progress | 81 |
| Yes | 35 |
| Not Applicable | 10 |

### hi_appeal_process

| value | count |
| --- | --- |
| (empty) | 101 |
| Appeal Process In-progress | 78 |
| Not Applicable | 28 |
| Appeal Process Established | 16 |
| Appeal Precluded by Law | 4 |

### hi_public_consultation

| value | count |
| --- | --- |
| [] | 101 |
| ['In-progress'] | 80 |
| ['Other'] | 22 |
| ['Usability Testing'] | 11 |
| ['a) Direct usability testing', 'b) General solicitations of feedback and comments from the public'] | 5 |
| ['Public Feedback Solicitations'] | 3 |

## Vendors named on high-impact use cases

| vendor_name value | count |
| --- | --- |
| (empty) | 330 |
| NEC | 5 |
| AI Service Provider | 4 |
| Law Enforcement Sensitive (LES) | 4 |
| SAS | 4 |
| Axon | 3 |
| IBM | 3 |
| Microsoft | 3 |
| Palantir | 3 |
| Thomson Reuters | 3 |
| Veritone | 3 |
| Advanced Technologies Group | 2 |
| Amazon | 2 |
| Axon Enterprise, Inc. | 2 |
| Microsoft / OpenAI | 2 |
| Motorola | 2 |
| Not available | 2 |
| AIS | 1 |
| Airlines Reporting Corporation | 1 |
| Airship AI Holdings Inc. | 1 |

## is_withheld values

| value | count |
| --- | --- |
| No | 2452 |
| (empty) | 1132 |
| Yes - Disclosure Risk | 20 |
| Yes - Prohibited by Law | 4 |
| Other | 3 |

