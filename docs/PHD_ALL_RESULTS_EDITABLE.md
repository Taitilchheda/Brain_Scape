# Brain_Scape Comprehensive Editable Results Document

Prepared: 2026-04-19

This is a single fully editable Markdown document that consolidates validated results, publication charts, comparison tables, reconstructed MRI views with hotspots, and DICOM-style panels.

## 1) Editing Guide
- This file is plain Markdown and fully editable.
- All tables are editable directly in this file.
- All images are linked from local project paths and can be replaced by regenerating assets.
- To change values, update this document and or regenerate source outputs listed in Section 12.

## 2) Canonical Data Sources
- Cohort and metrics JSON: docs/publication_metrics_latest.json
- Validation appendix: docs/PHD_PUBLICATION_VALIDATION.md
- Final publication charts: docs/final-publication/svg/
- Reconstruction case visuals: docs/final-publication/cases/
- Perfect-brain showcase visuals: docs/final-publication/perfect-brain-showcase/
- Additional result and evaluation visuals: docs/results-svg/

## 3) Cohort Flow and Descriptor
### Cohort Flow
| Item | Value |
|---|---:|
| Total detected analysis files | 71 |
| Included publication rows | 49 |
| Excluded rows | 22 |
| Excluded scan_conf_metrics_only | 22 |
| Duplicate scan IDs in included cohort | 0 |

### Cohort Descriptor
| Descriptor | Value |
|---|---:|
| MRI_T1 scans | 45 |
| fMRI scans | 4 |
| Atlas AAL3 rows | 49 |
| Scan quality limited | 26 |
| Scan quality fair | 23 |
| Provenance uploaded | 49 |

## 4) Primary Results Table (95% CI)
| Metric | Mean | 95% CI Low | 95% CI High |
|---|---:|---:|---:|
| Overall confidence | 0.723 | 0.715 | 0.729 |
| Triage score | 8.19 | 6.56 | 9.91 |
| Flagged regions | 3.12 | 2.51 | 3.78 |
| Severe regions | 1.06 | 0.69 | 1.45 |
| Flagged volume (mm3) | 6939.2 | 5310.7 | 8662.1 |
| Severe volume (mm3) | 3113.6 | 2016.9 | 4308.9 |
| Mean region confidence (%) | 78.42 | 74.60 | 81.85 |
| Highest region burden (%) | 25.39 | 23.61 | 27.21 |

## 5) Comparison Tables
### Risk Distribution Comparison (Wilson 95% CI)
| Risk Band | Count | Percent | 95% CI Low | 95% CI High |
|---|---:|---:|---:|---:|
| High | 23 | 46.94% | 33.70% | 60.62% |
| Moderate | 4 | 8.16% | 3.22% | 19.19% |
| Low | 22 | 44.90% | 31.85% | 58.69% |

### Severity Distribution Comparison
| Severity | Count | Percent |
|---|---:|---:|
| BLUE | 159 | 40.56% |
| GREEN | 80 | 20.41% |
| YELLOW | 67 | 17.09% |
| ORANGE | 34 | 8.67% |
| RED | 52 | 13.27% |

### Top Regions (Severity >= 2)
| Region | Frequency | Mean Burden (%) | Mean Volume (mm3) |
|---|---:|---:|---:|
| Precentral_R | 35 | 22.10 | 1525.7 |
| Hippocampus_R | 21 | 28.61 | 1865.7 |
| Precentral_L | 19 | 24.70 | 4787.6 |
| Hippocampus_L | 19 | 26.37 | 2662.7 |
| Parietal_Inf_L | 19 | 24.57 | 1616.8 |
| Temporal_Mid_L | 17 | 23.50 | 1609.4 |

### Governance Comparison
| Governance Metric | Value |
|---|---:|
| Total audit events | 430 |
| Allowed | 400 |
| Denied | 30 |
| Unique users | 10 |
| Unique actions | 31 |
| Audit completeness | 100.0% |
| Denied reason role_not_allowed | 30 |

### Case-Level Comparison (Reconstruction Cases)
| Case | Scan ID | Risk | Overall Confidence | Triage | Flagged Regions | Severe Regions | Flagged Vol (mm3) | Severe Vol (mm3) | Mean Region Confidence (%) | Highest Region Burden (%) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Zafiq (CUST-69D772) | 088b7515-bcfb-441c-85d0-f0e24f2f7300 | high | 0.701 | 16.30 | 5 | 3 | 13873.0 | 9603.0 | 90.00 | 31.90 |
| Uploaded Patient (UPLOAD-4B11D116) | 4b11d116-1e3e-4bef-a077-01f06d462523 | high | 0.701 | 17.60 | 5 | 4 | n/a | n/a | n/a | n/a |
| Uploaded Patient (UPLOAD-3C872FBF) | 3c872fbf-6fb5-4f2e-9ad0-e3156696f4a4 | low | 0.683 | 2.47 | 1 | 0 | 1380.0 | 0.0 | 62.61 | 18.60 |

### Derived Comparison Ratios
| Derived Comparator | Value |
|---|---:|
| Mean flagged to severe region ratio | 2.94 |
| High-to-low risk count ratio | 1.05 |
| Allowed-to-denied audit ratio | 13.33 |

## 6) Final Publication Graph Set (SVG)
### Cohort and Core Metrics
![Cohort Flow](final-publication/svg/final_01_cohort_flow.svg)
![Core Metrics with CI](final-publication/svg/final_02_core_metrics_ci.svg)
![Risk Distribution with CI](final-publication/svg/final_03_risk_distribution_ci.svg)
![Severity Distribution](final-publication/svg/final_04_severity_distribution.svg)
![Top Regions](final-publication/svg/final_05_top_regions.svg)
![Governance](final-publication/svg/final_06_governance.svg)

### Reconstruction and Workflow Evidence
![3D Reconstruction Accuracy](final-publication/svg/final_07_3d_reconstruction_accuracy.svg)
![Atlas Mapping](final-publication/svg/final_08_atlas_mapping.svg)
![Region Marking](final-publication/svg/final_09_region_marking.svg)
![DICOM Workstation](final-publication/svg/final_10_dicom_workstation.svg)

## 7) Additional Results and Evaluation Graphs (SVG)
### Results Charts
![Core Metrics Table Chart](results-svg/results_table_core_metrics.svg)
![Risk Distribution Chart](results-svg/results_chart_risk_distribution.svg)
![Severity Donut Chart](results-svg/results_chart_severity_donut.svg)
![Top Regions Analytics](results-svg/results_visual_analytics_top_regions.svg)
![Governance Analytics](results-svg/results_visual_analytics_governance.svg)
![Comparison Exemplar Bubble](results-svg/results_comparison_exemplar_bubble.svg)
![Comparison Exemplar Table](results-svg/results_comparison_exemplar_table.svg)

### Evaluation and Validation Dashboards
![Evaluation Results Validation Dashboard](results-svg/eval_results_validation_dashboard.svg)
![Target vs Achieved Metrics](results-svg/eval_metric_table_target_vs_achieved.svg)
![Reliability Success P95](results-svg/eval_reliability_success_p95.svg)
![Calibration ECE Summary](results-svg/eval_calibration_ece_summary.svg)
![Clinician Benchmark Agreement](results-svg/eval_agreement_clinician_benchmark.svg)
![Governance Allowed Denied Completeness](results-svg/eval_governance_allowed_denied_completeness.svg)

## 8) Reconstructed MRI and DICOM Panels with Hotspots
### Case 1: Zafiq (CUST-69D772)
![Case 1 3D Reconstruction](final-publication/cases/088b7515-bcfb-441c-85d0-f0e24f2f7300/3d_reconstruction.png)
![Case 1 3D Region Marking](final-publication/cases/088b7515-bcfb-441c-85d0-f0e24f2f7300/3d_region_marking.png)
![Case 1 DICOM Projections](final-publication/cases/088b7515-bcfb-441c-85d0-f0e24f2f7300/dicom_projections.png)
![Case 1 DICOM Damage Overlay](final-publication/cases/088b7515-bcfb-441c-85d0-f0e24f2f7300/dicom_damage_overlay.png)

### Case 2: Uploaded Patient (UPLOAD-4B11D116)
![Case 2 3D Reconstruction](final-publication/cases/4b11d116-1e3e-4bef-a077-01f06d462523/3d_reconstruction.png)
![Case 2 3D Region Marking](final-publication/cases/4b11d116-1e3e-4bef-a077-01f06d462523/3d_region_marking.png)
![Case 2 DICOM Projections](final-publication/cases/4b11d116-1e3e-4bef-a077-01f06d462523/dicom_projections.png)
![Case 2 DICOM Damage Overlay](final-publication/cases/4b11d116-1e3e-4bef-a077-01f06d462523/dicom_damage_overlay.png)

### Case 3: Uploaded Patient (UPLOAD-3C872FBF)
![Case 3 3D Reconstruction](final-publication/cases/3c872fbf-6fb5-4f2e-9ad0-e3156696f4a4/3d_reconstruction.png)
![Case 3 3D Region Marking](final-publication/cases/3c872fbf-6fb5-4f2e-9ad0-e3156696f4a4/3d_region_marking.png)
![Case 3 DICOM Projections](final-publication/cases/3c872fbf-6fb5-4f2e-9ad0-e3156696f4a4/dicom_projections.png)
![Case 3 DICOM Damage Overlay](final-publication/cases/3c872fbf-6fb5-4f2e-9ad0-e3156696f4a4/dicom_damage_overlay.png)

## 9) Perfect Brain Showcase (Human Cortical Template)
![Perfect Brain Surface](final-publication/perfect-brain-showcase/perfect_brain_surface.png)
![Perfect Brain Hotspots](final-publication/perfect-brain-showcase/perfect_brain_hotspots.png)
![DICOM MRI Series](final-publication/perfect-brain-showcase/dicom_mri_series.png)
![DICOM MRI Hotspots](final-publication/perfect-brain-showcase/dicom_mri_hotspots.png)

## 10) Mermaid Diagram Sources (Editable Flow Specs)
- final-publication/mmd/final_01_cohort_flow.mmd
- final-publication/mmd/final_02_core_metrics_ci.mmd
- final-publication/mmd/final_03_risk_distribution_ci.mmd
- final-publication/mmd/final_04_severity_distribution.mmd
- final-publication/mmd/final_05_top_regions.mmd
- final-publication/mmd/final_06_governance.mmd

## 11) Asset Checklist
- Validated publication metrics and confidence intervals: included
- Cohort flow, descriptor, governance and QC summary tables: included
- Core publication SVG panels: included
- Additional evaluation SVG panels: included
- Reconstruction MRI and DICOM visuals with hotspot overlays: included
- Perfect-brain showcase visuals: included
- Case-level comparison table: included

## 12) Regeneration Commands
- tools/compute_publication_validation.py
- tools/generate_final_publication_assets.py
- tools/generate_actual_reconstruction_images.py
- tools/generate_perfect_brain_showcase.py

## 13) Notes
- This file is designed to be directly edited for manuscript writing, poster preparation, or export conversion.
- If any image does not render in your editor preview, the path still remains editable and valid for static site or report generation workflows.
