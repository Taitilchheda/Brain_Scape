# Brain_Scape — Full Implementation Plan

Synthesized from three source documents:
1. **Brain_Scape main idea.txt** — Vision, features, processing pipeline, phased rollout
2. **Understanding_how_Brain_Scape_works.txt** — Layer-by-layer component detail, folder structure, data flow
3. **architecture.md** — System architecture, data models, API contracts, security, deployment

---

## Phase 1: Core Platform (MVP)

**Goal:** End-to-end pipeline producing research-grade outputs on public datasets.
**Exit criteria:** Complete pipeline in < 30 min wall time; segmentation Dice >= 0.80; all PHI scrubbing tests pass; audit log operational.

---

### Step 1.1: Project Scaffolding & Dev Environment

**Status: COMPLETE**

Files created:
- `requirements.txt` — Pinned Python dependencies (neuroimaging, DL, serving, MLOps, compliance, LLM/RAG, OCR, reports, testing)
- `.gitignore` — Excludes data, models, outputs, secrets
- `.env.example` — All env vars: DB, Redis, S3, LLM, RAG, JWT, encryption, compliance, MLflow, worker, GPU, monitoring
- `setup.py` — Package configuration with all sub-modules and console_scripts entry points
- `docker-compose.yml` — 9 containers: api (2 replicas), worker-cpu, worker-gpu, postgres, redis, minio, mlflow, prometheus, grafana
- `Makefile` — Shortcuts: setup, up, down, test, pipeline, ingest, lint, clean, db-init, download-atlases, seed-data

Config files:
- `configs/pipeline.yaml` — Stage toggles, timeout settings, checkpoint/resume config
- `configs/preprocessing.yaml` — FSL BET threshold, MCFLIRT config, smoothing FWHM, ANTs SyN registration params, atlas file paths
- `configs/models.yaml` — nnU-Net config, 5-level severity color contract, severity thresholds, confidence weights (0.5/0.3/0.2), promotion gates (Dice>=0.82, ECE<=0.05, diff F1>=0.75)
- `configs/llm.yaml` — LLM provider, RAG config (top_k=5, embedding dimension), report generation params, voice config
- `configs/serve.yaml` — API port/workers, Celery config, S3 storage, mesh decimation target, signed URL expiry
- `configs/compliance.yaml` — PHI scrubbing entities, DICOM/EXIF tags to scrub, RBAC role permissions matrix, audit logging, data residency

---

### Step 1.2: Data Layer & Atlas Setup

**Status: COMPLETE**

Files created:
- `scripts/download_atlases.sh` — Downloads MNI152, AAL3, Brodmann, Desikan-Killiany atlas files
- `scripts/seed_openneuro.py` — Downloads sample OpenNeuro datasets (ds000105, ds000208, ds000247, ds000103)

---

### Step 1.3: Ingestion Layer

**Status: COMPLETE**

Files created:
- `ingestion/__init__.py`
- `ingestion/format_detector.py` — `ScanFormat` enum, `detect_format()` function with 4-stage detection (directory scan, extension, magic bytes, library probing), metadata extraction per format
- `ingestion/anonymizer.py` — `PHIScrubber` class with synchronous Presidio-based PHI scrubbing, DICOM series anonymization, EXIF removal, hash-based replacement tokens
- `ingestion/converter.py` — `FormatConverter` class converting DICOM/NIfTI/EDF/images to .nii.gz, DICOM-to-NIfTI stacking, EDF reshaping, OCR pipeline for images
- `ingestion/ocr_extractor.py` — `OCRExtractor` class with header-region-only OCR, regex-based metadata pattern extraction
- `ingestion/validator.py` — `ScanValidator` class with `ValidationResult` dataclass, SNR estimation, dimension/FOV/resolution checks, per-format validation

---

### Step 1.4: Preprocessing Layer

**Status: COMPLETE**

Stage order (MUST be preserved):
1. `skull_stripper.py` — FSL BET (threshold 0.5), Otsu intensity fallback, morphological cleanup
2. `motion_corrector.py` — FSL MCFLIRT, simple cross-correlation fallback, configurable reference volume
3. `slice_timer.py` — Interleaved/sequential slice ordering, linear interpolation correction
4. `denoiser.py` — Gaussian smoothing + NLMeans, FWHM-to-sigma conversion
5. `intensity_normalizer.py` — Z-score, min-max, histogram matching methods, percentile clipping
6. `atlas_registrar.py` — ANTs SyN (Python API + CLI), FSL FNIRT fallback (FLIRT + FNIRT), Dice overlap quality metric

Files created:
- `preprocessing/__init__.py`
- `preprocessing/skull_stripper.py`
- `preprocessing/motion_corrector.py`
- `preprocessing/slice_timer.py`
- `preprocessing/denoiser.py`
- `preprocessing/intensity_normalizer.py`
- `preprocessing/atlas_registrar.py`

---

### Step 1.5: Analysis Engine (Core)

**Status: COMPLETE**

Files created:
- `analysis/__init__.py`
- `analysis/segmentation/__init__.py`
- `analysis/segmentation/segmentor.py` — `BrainSegmentor` with nnU-Net v2 primary + intensity-threshold fallback, GPU inference config
- `analysis/segmentation/voxel_scorer.py` — `VoxelScorer` with per-region severity scoring, atlas intersection, volume calculations (mm^3 and %)
- `analysis/segmentation/confidence_scorer.py` — `ConfidenceScorer` with 3-component model (ensemble agreement 50%, scan quality 30%, registration accuracy 20%)
- `analysis/classification/__init__.py`
- `analysis/classification/damage_classifier.py` — `DamageClassifier` with 5-level color contract (BLUE/GREEN/YELLOW/ORANGE/RED), dual classification methods
- `analysis/classification/confidence_scorer.py` — (consolidated into segmentation)

Phase 2 stubs:
- `analysis/connectivity/__init__.py`
- `analysis/fusion/__init__.py`
- `analysis/longitudinal/__init__.py`

---

### Step 1.6: Reconstruction Layer

**Status: COMPLETE**

Files created:
- `reconstruction/__init__.py`
- `reconstruction/mesh_builder.py` — `MeshBuilder` with VTK marching cubes + scikit-image fallback, quadric decimation (100k-200k target), Laplacian smoothing
- `reconstruction/region_labeler.py` — `RegionLabeler` with AAL/Brodmann/DK atlas intersection, vertex-to-voxel mapping, region aggregation
- `reconstruction/damage_overlay.py` — `DamageOverlay` with per-vertex severity coloring, face-level majority vote, JSON damage map output
- `reconstruction/gif_exporter.py` — `GIFExporter` with Matplotlib 3D rendering + Pillow fallback, configurable frames/resolution/fps
- `reconstruction/mesh_exporter.py` — `MeshExporter` with .glb (Draco), .obj, .stl export, trimesh primary + VTK fallback

---

### Step 1.7: LLM + RAG Layer

**Status: COMPLETE**

Files created:
- `llm/__init__.py`
- `llm/rag_engine.py` — `RAGEngine` with Weaviate/Pinecone support, BioBERT/PubMedBERT embeddings, document chunking, top-k retrieval with score threshold
- `llm/qa_engine.py` — `QAEngine` with scan-aware context building, fallback template-based answers, citation extraction, confidence computation, Whisper voice transcription stub
- `llm/report_generator.py` — `ReportGenerator` with two-pass chain (structured extraction -> clinician/patient rendering), ReportLab/WeasyPrint PDF generation, executive summary generation
- `llm/prompt_templates.py` — All LLM templates centralized: QA_SYSTEM_PROMPT, REPORT_SYSTEM_PROMPT_CLINICIAN/PATIENT, PROGNOSIS_SYSTEM_PROMPT, and template functions for qa, clinician_report, patient_report, prognosis, rag_retrieval

---

### Step 1.8: Compliance Layer

**Status: COMPLETE**

Files created:
- `compliance/__init__.py`
- `compliance/phi_scrubber.py` — Singleton `PHIScrubber` wrapping Presidio, with `scrub()` and `check_for_phi()` methods
- `compliance/encryption.py` — `EncryptionManager` with Fernet AES-256 encryption, file encrypt/decrypt, key generation
- `compliance/audit_logger.py` — `AuditLogger` with file-based and postgres storage, append-only JSONL format, query capability
- `compliance/rbac.py` — `RBACManager` with JWT creation/validation, permission matrix (clinician/researcher/patient), endpoint pattern matching, PERMISSIONS dict, 15-min access token, 7-day refresh token
- `compliance/consent_manager.py` — `ConsentManager` with grant/revoke/check/require_consent methods, opt-in vs opt-out features (longitudinal_analysis, research_contribution = opt-in; data_sharing = opt-out), audit logging integration

---

### Step 1.9: MLOps Layer (Serving + Monitoring)

**Status: COMPLETE**

Files created:
- `mlops/__init__.py`
- `mlops/pipeline.py` — Prefect `@flow` decorated `brainscape_pipeline()` with 7 tasks (ingest, preprocess, reconstruct, analyze, generate_report, export, register), each with retries and timeouts
- `mlops/tracking.py` — `TrackingManager` with MLflow logging (parameters, metrics, tags) and file-based fallback
- `mlops/registry.py` — `ModelRegistry` with automated promotion gates (Dice>=0.82, ECE<=0.05, diff F1>=0.75), staging->production promotion requiring ml_admin JWT
- `mlops/serve/__init__.py`
- `mlops/serve/api.py` — FastAPI app with all endpoints: /health, /ingest, /status/{job_id}, /mesh/{scan_id}, /report/{scan_id}, /query, /prognosis/{scan_id} (Phase 2), /longitudinal (Phase 2), /annotate (Phase 3), /export/{scan_id}, RBAC middleware
- `mlops/serve/task_queue.py` — Celery app with process_scan, run_segmentation, run_llm_query, update_job_status tasks
- `mlops/serve/Dockerfile` — Python 3.11-slim base, FSL + ANTs installation, requirements, atlas directories
- `mlops/monitoring/prometheus.yml` — Scrape configs for api, workers, redis, postgres
- `mlops/monitoring/grafana_dashboard.json` — 7 panels: jobs by status, duration by stage, queue depth, GPU utilization, confidence P50, LLM latency, API rate

---

### Step 1.10: Frontend (Basic)

**Status: COMPLETE**

Files created:
- `frontend/index.html` — Dark-themed layout with 3D viewer panel, side panel with damage overlay legend, region list, Q&A input, export buttons, status bar
- `frontend/viewer/brain_viewer.js` — Three.js 3D viewer with GLTFLoader + DRACOLoader, orbit controls, click-to-inspect regions, upload/poll/scan workflow
- `frontend/viewer/damage_overlay.js` — Severity level toggles, opacity slider, region isolation, region list population
- `frontend/report/clinician_report.html` — Print-optimized CSS, damage assessment table, differential diagnosis section, methodology section, disclaimer

---

### Step 1.11: Tests

**Status: COMPLETE**

Files created:
- `tests/__init__.py`
- `tests/test_ingestion.py` — Tests for format detection (NIfTI, compressed, image, unknown), validation (valid scan, tiny volume rejection), PHI scrubbing (person names, dates, emails, phones, clinical content preservation, empty text)
- `tests/test_preprocessing.py` — Tests for zscore/minmax normalization, output file creation, Gaussian smoothing, stage ordering enforcement
- `tests/test_analysis.py` — Tests for severity level definitions (5 levels, unique colors), classification (healthy, severe, moderate, sorting), confidence scoring (high/low/weights/thresholds), scan quality score range, analysis JSON contract required fields
- `tests/test_llm.py` — Tests for prompt template rendering (qa, clinician, patient, prognosis), RAG embedding/chunking, QA fallback answers, citation extraction, report executive summary (with/without damage)
- `tests/test_compliance.py` — Tests for RBAC (token creation/validation, expiration, role permissions, endpoint matching), encryption roundtrip, audit logging (events, denied access, querying), consent (grant/revoke/check, opt-in/opt-out, require_consent raises)
- `tests/test_api.py` — Tests for health check, ingest auth, patient clinician report restriction, export, Phase 2/3 endpoint status

---

### Step 1.12: Notebooks & Scripts

**Status: COMPLETE**

Files created:
- `notebooks/01_data_exploration.ipynb` — Load scans, visualize orthogonal slices, intensity histograms, SNR estimation, format detection
- `notebooks/02_preprocessing.ipynb` — Walk through all 6 preprocessing stages with before/after visualization
- `notebooks/03_reconstruction.ipynb` — Mesh building, region labeling, damage overlay, GIF/3D export
- `notebooks/04_analysis.ipynb` — Segmentation, voxel scoring, damage classification, confidence assessment, analysis JSON contract
- `notebooks/05_llm_pipeline.ipynb` — RAG retrieval, Q&A, report generation, PDF export
- `scripts/ingest.py` — CLI ingestion script (detect format, validate, anonymize, convert)
- `scripts/run_pipeline.sh` — One-command full pipeline (ingest -> preprocess -> Prefect pipeline)

---

### Step 1.13: Database Schema

**Status: COMPLETE**

Files created:
- `migrations/alembic.ini` — Alembic configuration pointing to Postgres
- `migrations/env.py` — Alembic environment for online/offline migrations
- `migrations/script.py.mako` — Migration template
- `migrations/versions/001_initial_schema.py` — Full schema with 6 tables:
  - `users` — id (UUID), email (unique), password_hash, role (clinician/researcher/patient), institution_id, timestamps
  - `scans` — id (UUID), patient_id (FK), original_filename, original_format, modality, status (uploaded/processing/complete/failed), anonymized_path, original_path, scan_metadata (JSON), timestamps
  - `jobs` — id (UUID), scan_id (FK), user_id (FK), status (queued/preprocessing/reconstructing/analyzing/generating/complete/failed), stage, progress_pct, error_message, pipeline_config (JSON), result_path, timestamps
  - `annotations` — id (UUID), scan_id (FK), user_id (FK), mesh_face_id, comment, marker_type, version, created_at
  - `audit_logs` — id (UUID), timestamp, user_id, role, action, resource_id, outcome (ALLOWED/DENIED), ip_address, session_id, details (JSON)
  - `consent_records` — id (UUID), patient_id (FK), feature, status (granted/revoked), granted_by, revoked_by, timestamps. Unique on (patient_id, feature)

---

## Phase 2: Clinical Intelligence

**Status: NOT STARTED**

**Goal:** Differentiate as a diagnostic decision support tool. Begin regulated pilot.
**Exit criteria:** Differential diagnosis F1 >= 0.75; patient report validated by neurologist panel; HIPAA compliance audit passed; begin IRB-approved pilot.

### Step 2.1: Differential Diagnosis Engine
- CNN encoder (ResNet-50 backbone pretrained on BraTS) + Transformer attention
- Multi-label softmax over 8 etiologies: stroke, hemorrhage, TBI, tumour, MS, dementia, encephalitis, hypoxic injury
- File: `analysis/classification/differential_diagnosis.py`

### Step 2.2: Longitudinal Temporal Analysis
- Compare multiple scans of same patient over time
- Delta maps, atrophy rate, treatment response tracking
- File: `analysis/longitudinal/temporal_comparator.py`

### Step 2.3: Multimodal Fusion
- Weighted late fusion of EEG + fMRI + DTI maps
- File: `analysis/fusion/multimodal_fuser.py`

### Step 2.4: Connectivity Analysis
- Structural: MRtrix3 white matter fiber tractography
- Functional: nilearn resting-state fMRI network analysis
- Files: `analysis/connectivity/structural_connectivity.py`, `analysis/connectivity/functional_connectivity.py`

### Step 2.5: Tiered Patient Report
- Plain English patient mode in report generator
- Visual-first, minimal jargon, emotional framing
- Files: Update `llm/report_generator.py`, add `frontend/report/patient_report.html`

### Step 2.6: Prognosis Timeline Generator
- Probabilistic recovery trajectory based on damage, age, published outcomes
- File: `llm/prognosis_generator.py`

### Step 2.7: Voice Query Interface
- Whisper ASR (medium model, locally hosted) for audio transcription
- File: `llm/voice_interface.py`

### Step 2.8: Recovery Recommendations
- Region-mapped short-term and long-term recommendations
- Integrated into report_generator.py and prompt_templates.py

---

## Phase 3: Collaboration & Surgical Planning

**Status: NOT STARTED**

**Goal:** Platform for clinical teams; integration with hospital infrastructure.
**Exit criteria:** PACS integration tested; annotation collaboration tested with >= 3 concurrent users; FDA SaMD pre-submission initiated.

### Step 3.1: Collaborative Annotation Workspace
- Three.js Raycaster, WebSocket real-time sync, versioned annotations
- Files: `frontend/viewer/annotation_layer.js`, `mlops/serve/ws_server.py`

### Step 3.2: Treatment Planning Overlay
- Eloquent cortex mapping, surgical no-go zones, intervention viability
- File: `analysis/treatment/planning_overlay.py`

### Step 3.3: PACS / RIS / HL7 FHIR Integration
- DICOM WADO-RS for PACS connectivity, HL7 FHIR facade
- Requires hospital IT partner

### Step 3.4: Institutional Dashboards
- Aggregate stats, audit tools, utilization dashboards, GDPR data residency
- Grafana dashboards with institutional scope

---

## Build Order (Critical Path)

```
1.1 Scaffolding ─────────┐
  ├── 1.2 Data & Atlases  │
  ├── 1.8 Compliance      │
  └── 1.13 Database       │
        │                  │
        ▼                  │
1.3 Ingestion ───────────┤
        │                  │
        ▼                  │
1.4 Preprocessing ───────┤
        │                  │
        ▼                  │
1.5 Analysis Engine ─────┤
        │                  │
        ├── 1.6 Reconstruction
        │       │          │
        │       └── 1.10 Frontend
        │                  │
        └── 1.7 LLM + RAG ┤
                │          │
                └── 1.9 MLOps

1.11 Tests (after all layers) ── DONE
1.12 Notebooks & Scripts ──────── DONE
```

Steps 1.2, 1.8, and 1.13 can proceed in parallel with 1.3-1.7 after 1.1 is complete.

---

## Verification Plan

### End-to-End Test (Phase 1)
1. Download an OpenNeuro T1w MRI scan via `scripts/seed_openneuro.py`
2. Upload via `POST /ingest` — verify job_id returned in < 500ms
3. Poll `GET /status/{job_id}` — verify pipeline progresses through all stages
4. Verify complete pipeline runs in < 30 min wall time
5. Fetch `GET /mesh/{scan_id}` — verify .glb loads in Three.js viewer
6. Fetch `GET /report/{scan_id}?mode=clinician` — verify PDF contains structured findings
7. Post `POST /query` with "What regions are damaged?" — verify cited response
8. Run `pytest tests/` — all tests pass
9. Verify no PHI present in any output artifact
10. Verify audit log contains entries for every API call made

### Model Quality Gates
- nnU-Net segmentation Dice >= 0.80 on held-out OpenNeuro test set
- Confidence scores in valid range [0, 1]
- Analysis JSON matches schema contract

### Compliance Verification
- PHI scrubbing test: upload scan with embedded PHI, verify no PHI in pipeline outputs
- RBAC test: researcher token cannot access PHI endpoints
- Audit log: append-only, entries for all access events
- Encryption: round-trip encrypt/decrypt verification