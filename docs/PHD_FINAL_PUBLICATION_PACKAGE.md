# Brain_Scape Final Publication Package

Prepared date: 2026-04-19

## 1. Publication Status
This file is the final PhD manuscript-ready consolidation for Results and validation evidence.
All values are sourced from docs/publication_metrics_latest.json and generated through tools/compute_publication_validation.py.

## 2. Cohort Flow
- Total detected analysis files: 71
- Publication-eligible rows: 49
- Excluded rows: 22
- Excluded scan_conf_metrics_only rows: 22
- Included cohort duplicate scan IDs: 0

## 3. Cohort Descriptor
| Descriptor | Value |
|---|---:|
| MRI_T1 scans | 45 |
| fMRI scans | 4 |
| Atlas AAL3 | 49 |
| Scan quality limited | 26 |
| Scan quality fair | 23 |
| Provenance uploaded | 49 |

## 4. Core Outcomes with 95% CI
| Metric | Mean | 95% CI low | 95% CI high |
|---|---:|---:|---:|
| Overall confidence | 0.723 | 0.715 | 0.729 |
| Triage score | 8.19 | 6.56 | 9.91 |
| Flagged regions | 3.12 | 2.51 | 3.78 |
| Severe regions | 1.06 | 0.69 | 1.45 |
| Flagged volume mm3 | 6939.2 | 5310.7 | 8662.1 |
| Severe volume mm3 | 3113.6 | 2016.9 | 4308.9 |
| Mean region confidence pct | 78.42 | 74.60 | 81.85 |
| Highest region burden pct | 25.39 | 23.61 | 27.21 |

## 5. Risk Distribution with Wilson 95% CI
| Risk band | Count | Percent | 95% CI low | 95% CI high |
|---|---:|---:|---:|---:|
| High | 23 | 46.94% | 33.70% | 60.62% |
| Moderate | 4 | 8.16% | 3.22% | 19.19% |
| Low | 22 | 44.90% | 31.85% | 58.69% |

## 6. Severity Distribution
| Severity | Count | Percent |
|---|---:|---:|
| BLUE | 159 | 40.56% |
| GREEN | 80 | 20.41% |
| YELLOW | 67 | 17.09% |
| ORANGE | 34 | 8.67% |
| RED | 52 | 13.27% |

## 7. Top Regions Severity GE 2
| Region | Frequency | Mean burden pct | Mean volume mm3 |
|---|---:|---:|---:|
| Precentral_R | 35 | 22.10 | 1525.7 |
| Hippocampus_R | 21 | 28.61 | 1865.7 |
| Precentral_L | 19 | 24.70 | 4787.6 |
| Hippocampus_L | 19 | 26.37 | 2662.7 |
| Parietal_Inf_L | 19 | 24.57 | 1616.8 |
| Temporal_Mid_L | 17 | 23.50 | 1609.4 |

## 8. Governance
| Metric | Value |
|---|---:|
| Total audit events | 430 |
| Allowed | 400 |
| Denied | 30 |
| Unique users | 10 |
| Unique actions | 31 |
| Audit completeness | 100.0% |
| Denied reason role_not_allowed | 30 |

## 9. Figure Asset Set
SVG files:
- docs/final-publication/svg/final_01_cohort_flow.svg
- docs/final-publication/svg/final_02_core_metrics_ci.svg
- docs/final-publication/svg/final_03_risk_distribution_ci.svg
- docs/final-publication/svg/final_04_severity_distribution.svg
- docs/final-publication/svg/final_05_top_regions.svg
- docs/final-publication/svg/final_06_governance.svg
- docs/final-publication/svg/final_07_3d_reconstruction_accuracy.svg
- docs/final-publication/svg/final_08_atlas_mapping.svg
- docs/final-publication/svg/final_09_region_marking.svg
- docs/final-publication/svg/final_10_dicom_workstation.svg

Mermaid files:
- docs/final-publication/mmd/final_01_cohort_flow.mmd
- docs/final-publication/mmd/final_02_core_metrics_ci.mmd
- docs/final-publication/mmd/final_03_risk_distribution_ci.mmd
- docs/final-publication/mmd/final_04_severity_distribution.mmd
- docs/final-publication/mmd/final_05_top_regions.mmd
- docs/final-publication/mmd/final_06_governance.mmd

## 10. Regeneration
1. Run tools/compute_publication_validation.py to refresh validated metrics.
2. Run tools/generate_final_publication_assets.py to refresh this package and all diagrams.

## 11. Actual Reconstruction and DICOM Visuals
These are real image renders (not metric-only charts) generated from exported mesh data and paired analysis metadata.

Case folders:
- docs/final-publication/cases/README.md
- docs/final-publication/cases/088b7515-bcfb-441c-85d0-f0e24f2f7300/README.md
- docs/final-publication/cases/4b11d116-1e3e-4bef-a077-01f06d462523/README.md

Gallery:
- docs/final-publication/ACTUAL_RECON_DICOM_GALLERY.md

Generation command:
- tools/generate_actual_reconstruction_images.py

## 12. Perfect Brain Showcase
This dedicated folder provides a clean, publication-style "perfect brain" presentation with hotspot overlays and MRI-style DICOM panels.

Anatomical source:
- fsaverage human cortical template surfaces (left and right pial meshes)

Showcase files:
- docs/final-publication/perfect-brain-showcase/README.md
- docs/final-publication/perfect-brain-showcase/perfect_brain_surface.png
- docs/final-publication/perfect-brain-showcase/perfect_brain_hotspots.png
- docs/final-publication/perfect-brain-showcase/dicom_mri_series.png
- docs/final-publication/perfect-brain-showcase/dicom_mri_hotspots.png

Generation command:
- tools/generate_perfect_brain_showcase.py
