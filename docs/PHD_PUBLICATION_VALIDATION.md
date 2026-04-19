# Brain_Scape Publication Validation Appendix

Prepared: 2026-04-19

## 1. Scope and Claim Level
This appendix reports repository-derived internal validation for PhD manuscript-quality Results reporting.
Claims are limited to reproducibility, internal consistency, and governance traceability within this dataset.

## 2. Data Provenance and Cohort Flow
- Analysis source: outputs/analysis
- Audit source: logs/audit
- Total analysis files detected: 71
- Included in publication cohort: 49
- Excluded rows: 22
- Exclusion pattern (scan_conf_metrics_only): 22
- Duplicate scan IDs in included cohort: 0

Inclusion rule: rows must include non-empty region-level damage summaries and triage/risk outputs.
Rows missing only derived metric fields were retained and backfilled deterministically from region-level data.

## 3. Cohort Descriptor
| Descriptor | Value |
|---|---:|
| MRI_T1 scans | 45 |
| fMRI scans | 4 |
| Atlas AAL3 | 49 |
| Scan quality: limited | 26 |
| Scan quality: fair | 23 |
| Provenance: uploaded | 49 |

## 4. Primary Outcomes with 95% Confidence Intervals
| Metric | Mean [95% CI] |
|---|---:|
| Overall confidence | 0.723 [0.715, 0.729] |
| Triage score | 8.19 [6.56, 9.91] |
| Flagged regions | 3.12 [2.51, 3.78] |
| Severe regions | 1.06 [0.69, 1.45] |
| Flagged volume (mm3) | 6939.2 [5310.7, 8662.1] |
| Severe volume (mm3) | 3113.6 [2016.9, 4308.9] |
| Mean region confidence (%) | 78.42 [74.60, 81.85] |
| Highest region burden (%) | 25.39 [23.61, 27.21] |

## 5. Risk Stratification (Wilson 95% CI)
| Risk band | Count | Percent [95% CI] |
|---|---:|---:|
| High | 23 | 46.94% [33.70, 60.62] |
| Moderate | 4 | 8.16% [3.22, 19.19] |
| Low | 22 | 44.90% [31.85, 58.69] |

## 6. Severity Distribution
| Severity | Count | Percent |
|---|---:|---:|
| BLUE | 159 | 40.56% |
| GREEN | 80 | 20.41% |
| YELLOW | 67 | 17.09% |
| ORANGE | 34 | 8.67% |
| RED | 52 | 13.27% |

## 7. Top Affected Regions (Severity >= 2)
| Region | Frequency | Mean burden (%) | Mean volume (mm3) |
|---|---:|---:|---:|
| Precentral_R | 35 | 22.10 | 1525.7 |
| Hippocampus_R | 21 | 28.61 | 1865.7 |
| Precentral_L | 19 | 24.70 | 4787.6 |
| Hippocampus_L | 19 | 26.37 | 2662.7 |
| Parietal_Inf_L | 19 | 24.57 | 1616.8 |
| Temporal_Mid_L | 17 | 23.50 | 1609.4 |

## 8. Governance and Auditability
| Governance metric | Value |
|---|---:|
| Total audit events | 430 |
| ALLOWED events | 400 |
| DENIED events | 30 |
| Unique users | 10 |
| Unique actions | 31 |
| Audit completeness | 100.0% |

- Denied reason role_not_allowed: 30

## 9. Data Integrity Checks
- QC issue count: 0
- Checks run: value ranges, severe<=flagged consistency, duplicate scan IDs, and audit-field completeness

## 10. Publication-Ready Interpretation
- The dataset demonstrates a reproducible integrated pipeline with stable confidence and triage outputs across 49 publication-eligible scans.
- Governance controls are active and verifiable with explicit denied-event traceability.
- This is internal validation; external multi-center and prospective clinical validation remain future work.
