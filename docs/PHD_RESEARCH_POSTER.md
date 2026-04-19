# Brain_Scape: Clinically Oriented End-to-End Neuroimaging Intelligence Platform
## 3D Reconstruction, Risk Stratification, and LLM-Augmented Reporting with Compliance-by-Design

### Author
Taitil Chheda (PhD Research Candidate)

### Date
2026-04-19

---

## Abstract
Brain_Scape is an end-to-end neuroimaging intelligence platform that transforms uploaded MRI/fMRI data into structured analysis outputs, region-level severity mapping, 3D mesh artifacts, clinician-ready reports, and auditable governance trails. The system integrates ingestion, preprocessing, segmentation/classification, reconstruction, report generation, and compliance controls in a single pipeline. This poster presents implementation-level and output-level evidence from project artifacts currently available in the repository.

---

## 1. Motivation
Neuroimaging workflows often require multiple disconnected tools for preprocessing, lesion characterization, reporting, and compliance. Brain_Scape addresses this by unifying:
- Data ingestion and PHI-aware processing
- Atlas-aligned regional severity analysis
- 3D reconstruction and export for visual interpretation
- LLM-supported reporting and question answering
- Role-based governance with append-only audit logging

---

## 2. Research Objectives
1. Build a reproducible, modular neuroimaging pipeline from upload to report.
2. Provide clinically interpretable outputs (region burden, severity bands, confidence).
3. Maintain governance readiness (RBAC, consent traceability, auditability).
4. Support translational usage through API-driven and viewer-driven workflows.

---

## 3. System Overview
Brain_Scape consists of six technical layers:
1. Ingestion: format detection, validation, anonymization, conversion to NIfTI.
2. Preprocessing: skull stripping, motion correction, slice timing, denoising, intensity normalization, atlas registration.
3. Analysis: segmentation, voxel scoring, severity classification, confidence scoring.
4. Reconstruction: mesh generation, region labeling, damage overlay, export.
5. LLM/RAG: clinical report generation and scan-aware Q&A.
6. Compliance/MLOps: RBAC, encryption, consent, audit logging, API serving.

---

## 4. Experimental Snapshot (Repository Artifacts)
### Data and outputs considered
- Analysis JSON artifacts: 49
- Report PDFs: 7
- Export mesh objects: 5
- Demo mesh objects: 10
- Package JSON artifacts: 5

### Cohort descriptor (from analysis outputs)
- Total analyzed scans: 49
- Modality split: MRI_T1 (45), fMRI (4)
- Atlas: AAL3 for all analyzed scans (49)
- Provenance source: uploaded (49)
- Scan quality labels: limited (26), fair (23)

---

## 5. Quantitative Results
### 5.1 Cohort-level summary metrics
| Metric | Value |
|---|---:|
| Number of analyzed scans | 49 |
| Mean overall confidence | 0.723 |
| Mean triage score | 8.19 |
| Mean flagged regions | 3.12 |
| Mean severe regions | 1.06 |
| Mean flagged volume (mm3) | 6939.2 |
| Mean severe volume (mm3) | 3113.6 |
| Mean region confidence (%) | 78.42 |
| Mean highest regional burden (%) | 25.39 |

### 5.2 Risk-band stratification
| Risk band | Count |
|---|---:|
| High | 23 |
| Moderate | 4 |
| Low | 22 |

### 5.3 Severity label distribution across region summaries
| Severity label | Count | Percent |
|---|---:|---:|
| BLUE | 159 | 40.56 |
| GREEN | 80 | 20.41 |
| YELLOW | 67 | 17.09 |
| ORANGE | 34 | 8.67 |
| RED | 52 | 13.27 |

### 5.4 Most frequently flagged regions (severity >= 2)
| Anatomical region | Frequency | Mean burden (%) | Mean volume (mm3) |
|---|---:|---:|---:|
| Precentral_R | 35 | 22.10 | 1525.7 |
| Hippocampus_R | 21 | 28.61 | 1865.7 |
| Parietal_Inf_L | 19 | 24.57 | 1616.8 |
| Precentral_L | 19 | 24.70 | 4787.6 |
| Hippocampus_L | 19 | 26.37 | 2662.7 |
| Temporal_Mid_L | 17 | 23.50 | 1609.4 |

---

## 6. Exemplar Case Panel (for poster figure row)
| Case | Scan ID | Risk | Triage | Flagged regions | Severe regions | Flagged volume (mm3) | Key high-burden regions |
|---|---|---|---:|---:|---:|---:|---|
| High-risk exemplar | f5cfb886-0781-4ee3-935c-f80da1bf1fa3 | High | 19.88 | 7 | 4 | 18130 | Hippocampus_L (RED), Temporal_Mid_L (RED), Precentral_L (RED) |
| Moderate-risk exemplar | 8d43d3ce-5f4d-46f8-b3f2-47415c88c024 | Moderate | 6.98 | 4 | 0 | 6855 | Hippocampus_R (ORANGE), Parietal_Inf_L (YELLOW), Occipital_Sup_L (YELLOW) |
| Low-risk exemplar | 9fc2b355-338b-4629-a951-62c59423f37e | Low | 2.34 | 1 | 0 | 1380 | Temporal_Mid_L (YELLOW) |

---

## 7. Governance and Compliance Evidence
### Audit-trail metrics (JSONL audit logs)
- Total audited events: 430
- ALLOWED: 400
- DENIED: 30
- Unique users observed: 10
- Unique audited actions: 31

### Denial behavior (policy enforcement)
- All denials mapped to reason: role_not_allowed
- Most denied action: POST /signoff/demo-scan-002 (27 denials)

### Outcome by role
- clinician, ALLOWED: 362
- patient, ALLOWED: 37
- patient, DENIED: 30
- researcher, ALLOWED: 1

Interpretation: authorization controls are active and auditable, with explicit denial traces for policy violations.

---

## 8. Translational Outputs
The current pipeline generates artifacts that are directly showcaseable in clinical research demos:
- Structured analysis JSON for downstream quantification
- Clinician and patient PDF reports (where available)
- 3D mesh artifacts for interactive visualization
- Package metadata/provenance bundles for traceability

---

## 9. Limitations
- Current evidence is repository-output based and not an external clinical trial.
- Some modules rely on fallback paths when external tools are unavailable.
- Prospective multi-site validation and reader studies are pending.

---

## 10. Next Research Steps
1. External validation on benchmark and hospital datasets.
2. Reader studies comparing clinician agreement with and without Brain_Scape support.
3. Longitudinal outcome correlation with triage and burden metrics.
4. Formal deployment hardening for regulated environments.

---

## 11. Suggested Poster Figure Layout
1. Left column: Problem, objectives, architecture diagram.
2. Center column: Cohort metrics tables and risk stratification chart.
3. Right column: Exemplar case panel and governance evidence.
4. Footer: Limitations, future work, and reproducibility notes.

---

## Reproducibility Note
All values above were computed from current repository outputs and audit logs at the date shown in this poster draft.
Publication-authoritative numbers and confidence intervals are tracked in `docs/PHD_PUBLICATION_VALIDATION.md` and `docs/publication_metrics_latest.json`, generated by `tools/compute_publication_validation.py`.