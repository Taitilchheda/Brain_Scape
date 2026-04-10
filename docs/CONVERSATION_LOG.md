# Brain_Scape — Conversation Log & Context

This document preserves the full context of the implementation conversation, including design decisions, architectural reasoning, and implementation details that shaped the codebase.

---

## Source Documents

The project was designed by synthesizing three input documents:

1. **Brain_Scape main idea.txt** — High-level vision, 10 core features, processing pipeline overview, phased rollout strategy
2. **Understanding_how_Brain_Scape_works.txt** — Detailed layer-by-layer component descriptions, folder structure, data flow, specific tool choices (FSL, ANTs, nnU-Net, VTK, Prefect, etc.)
3. **architecture.md** — System architecture, data models (users, scans, jobs, annotations tables), API endpoint contracts, RBAC permission matrix, security requirements, deployment topology, open problems

All three documents were read in their entirety and cross-referenced to produce a unified implementation plan that resolves inconsistencies and fills gaps.

---

## Conversation Flow

### Message 1: User Request
> "refer to the 3 docs in the directory and make a detailed implementaion plan of the project"

The user pointed to three documentation files in the project directory. I read all three documents and produced a comprehensive implementation plan organized in 3 phases with 13 steps for Phase 1 alone.

### Message 2: Plan Approval
> (User approved the plan via the plan mode approval mechanism)

The plan was approved and I began implementing Phase 1 step by step.

### Implementation Sequence

The implementation followed the dependency order from the plan:

1. **Step 1.1** — Project scaffolding (requirements.txt, setup.py, docker-compose.yml, Makefile, .env.example, .gitignore, all 6 config YAMLs)
2. **Step 1.2** — Data layer scripts (download_atlases.sh, seed_openneuro.py)
3. **Step 1.3** — Ingestion layer (format_detector, anonymizer, converter, ocr_extractor, validator)
4. **Step 1.4** — Preprocessing layer (skull_stripper, motion_corrector, slice_timer, denoiser, intensity_normalizer, atlas_registrar)
5. **Step 1.5** — Analysis engine (segmentor, voxel_scorer, damage_classifier, confidence_scorer)
6. **Step 1.6** — Reconstruction layer (mesh_builder, region_labeler, damage_overlay, gif_exporter, mesh_exporter)
7. **Step 1.7** — LLM + RAG layer (rag_engine, qa_engine, report_generator, prompt_templates)
8. **Step 1.8** — Compliance layer (phi_scrubber, encryption, audit_logger, rbac, consent_manager)
9. **Step 1.9** — MLOps layer (pipeline, tracking, registry, api, task_queue, Dockerfile, prometheus, grafana)
10. **Step 1.10** — Frontend (index.html, brain_viewer.js, damage_overlay.js, clinician_report.html)
11. **Step 1.11** — Tests (6 test files covering all layers)
12. **Step 1.12** — Notebooks & scripts (5 Jupyter notebooks, ingest.py, run_pipeline.sh)
13. **Step 1.13** — Database schema (Alembic config, 001_initial_schema migration)

### Context Window Continuation
The conversation reached the context limit during test creation and was resumed. All prior work was summarized and continued from the notebooks and database migration step.

---

## Key Design Decisions Made During Implementation

### 1. Fallback Pattern for All External Tools
Every module that depends on an external neuroimaging tool (FSL, ANTs, nnU-Net, VTK) includes a pure-Python fallback implementation. This was a deliberate choice so the codebase can be developed and tested without requiring GPU access or installing heavy neuroimaging toolchains.

Examples:
- `skull_stripper.py`: FSL BET → Otsu intensity threshold fallback
- `atlas_registrar.py`: ANTs SyN → FSL FNIRT → simple affine fallback
- `segmentor.py`: nnU-Net v2 → intensity-threshold fallback
- `mesh_builder.py`: VTK marching cubes → scikit-image fallback
- `rag_engine.py`: Weaviate/Pinecone → in-memory dict fallback

### 2. Severity Color Contract (Single Source of Truth)
The 5-level severity color scheme is defined once in `configs/models.yaml` and referenced everywhere:
- `analysis/classification/damage_classifier.py` — Python enum
- `reconstruction/damage_overlay.py` — Mesh vertex coloring
- `frontend/viewer/damage_overlay.js` — JavaScript overlay
- `frontend/report/clinician_report.html` — Report legend
- `mlops/serve/api.py` — API response format

The levels are: BLUE (0, #4A90D9), GREEN (1, #27AE60), YELLOW (2, #F1C40F), ORANGE (3, #E67E22), RED (4, #E74C3C).

### 3. Synchronous PHI Gate
PHI anonymization in `ingestion/anonymizer.py` is a synchronous, blocking operation that MUST complete before any data enters an async queue. This is a compliance requirement — PHI never travels unmasked through the system.

### 4. Two-Pass LLM Chain
Report generation uses a two-pass approach:
- Pass 1: Structured extraction from analysis JSON into an intermediate representation
- Pass 2a (Clinician): Full technical depth with Brodmann labels, voxel volumes, confidence intervals, citations
- Pass 2b (Patient, Phase 2): Plain English, visual-first, emotional framing

### 5. Async Job Pattern
The API uses an async pattern:
- `POST /ingest` returns a job_id immediately (< 500ms)
- Client polls `GET /status/{job_id}` for progress
- Client fetches results when status becomes "complete"
- This is essential because neuroimaging pipelines take minutes to hours

### 6. Confidence Scoring Weights
Three-component model with configurable weights:
- Ensemble agreement: 50% (w1=0.5)
- Scan quality: 30% (w2=0.3)
- Registration accuracy: 20% (w3=0.2)

Two thresholds:
- Clinical confidence >= 0.5: included in clinical reports
- Display confidence >= 0.3: shown on 3D viewer

### 7. Model Promotion Gates
Automated quality gates for model promotion (defined in `mlops/registry.py`):
- Dice score >= 0.82
- Expected Calibration Error (ECE) <= 0.05
- Differential diagnosis F1 >= 0.75
- Promotion to production requires JWT with `ml_admin` role

### 8. Append-Only Audit Logging
The audit log (`compliance/audit_logger.py`) is append-only. No UPDATE or DELETE operations are permitted. This is a HIPAA compliance requirement.

### 9. Consent Model
Two consent categories:
- Opt-in (must explicitly grant): `longitudinal_analysis`, `research_contribution`
- Opt-out (granted by default, can revoke): `data_sharing`

Attempting to use an opt-in feature without consent raises `PermissionError`.

### 10. RBAC Permission Matrix
Three roles with distinct permissions:
- **Clinician**: Full access to all endpoints (reports, meshes, annotations, queries)
- **Researcher**: Anonymized access only (no PHI endpoints, no annotation)
- **Patient**: Own scans only (no annotation, no clinician reports)

---

## Architectural Decisions Not in Original Docs

These decisions were made during implementation to fill gaps or resolve inconsistencies in the source documents:

1. **Fernet for encryption** — The architecture doc specified AES-256. Python's `cryptography` library provides Fernet (which uses AES-128-CBC + HMAC-SHA256) as a higher-level, safer API. For true AES-256-GCM, the code notes the upgrade path.

2. **JSONL for file-based audit logging** — Rather than CSV or custom format, JSONL (JSON Lines) allows structured querying and easy parsing while maintaining append-only semantics.

3. **Prefect for orchestration** — The architecture doc mentioned Celery for task queuing. Prefect was added as the orchestration layer on top, with Celery handling the actual task execution. This gives both a DAG-level workflow (Prefect) and a task-level queue (Celery).

4. **Phase 2/3 endpoint stubs** — The API includes `/prognosis/{scan_id}` and `/longitudinal` endpoints that return `{"status": "coming_soon"}` rather than 404. This allows frontend development against known endpoint contracts.

5. **In-memory fallbacks** — For all vector stores and databases, in-memory fallbacks allow the system to run in development without requiring Weaviate/Pinecone, PostgreSQL, or Redis installations.

6. **Database migration via Alembic** — The architecture doc specified SQL table definitions. These were implemented as Alembic migrations for proper schema versioning and upgrade/downgrade support.

---

## Module Dependency Graph

```
                    User Upload
                        │
                        ▼
                  ┌──────────┐
                  │ Ingestion │ (format_detector → validator → anonymizer → converter)
                  └────┬─────┘
                       │
                       ▼
                ┌─────────────┐
                │ Preprocessing│ (skull_strip → motion_correct → slice_time → denoise → normalize → atlas_register)
                └──────┬──────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
     ┌─────────────┐   ┌────────────┐
     │  Analysis    │   │Reconstruction│
     │ (segment →  │   │ (mesh →    │
     │  score →    │   │  label →   │
     │  classify)  │   │  overlay → │
     │             │   │  export)   │
     └──────┬──────┘   └─────┬──────┘
              │                 │
              ▼                 ▼
        ┌─────────────────────────┐
        │    LLM + RAG Layer      │ (RAG → QA → Report)
        └────────────┬────────────┘
                     │
                     ▼
              ┌─────────────┐
              │    MLOps     │ (Pipeline → Tracking → Registry → API → Queue)
              └─────────────┘
                     │
              ┌──────┴──────┐
              ▼             ▼
     ┌──────────┐   ┌──────────┐
     │Compliance│   │Frontend  │
     │(RBAC,    │   │(Three.js │
     │ Audit,   │   │ viewer)  │
     │ Encrypt) │   │          │
     └──────────┘   └──────────┘
```

---

## Data Flow

```
Raw Scan → Format Detect → Validate → PHI Scrub → Convert to NIfTI
    │
    ▼
Skull Strip → Motion Correct → Slice Time → Denoise → Normalize → Atlas Register
    │
    ├─→ Segment → Voxel Score → Classify → Confidence
    │         │
    │         └─→ Analysis JSON (single source of truth)
    │                   │
    ▼                   ▼
Mesh Build → Region Label → Damage Overlay → Export (GLB/OBJ/STL/GIF)
                        │
                        ▼
            RAG Retrieve → QA Answer → Report Generate → PDF
                        │
                        ▼
              API (FastAPI) → Celery Queue → Job Status → Client
                        │
                        ▼
              Audit Log (append-only) → Compliance Check (RBAC + Consent)
```

---

## Configuration Files Detail

### `configs/pipeline.yaml`
- Stage toggles (enable/disable any preprocessing stage)
- Timeout settings (30 min for registration, 15 min for segmentation)
- Checkpoint/resume: partial results stored, resume from last completed stage

### `configs/preprocessing.yaml`
- FSL BET threshold: 0.5
- MCFLIRT reference volume: "middle"
- Slice timing order: "interleaved"
- Gaussian smoothing FWHM: 6.0mm
- ANTs SyN max iterations: [100, 70, 50, 20]
- Atlas file paths: configurable locations in data/atlases/

### `configs/models.yaml`
- nnU-Net: trainer, planner, fold, checkpoint paths
- Severity levels: 0-4 with hex colors and labels
- Severity thresholds: volume_pct >= 50% → RED, >= 30% → ORANGE, >= 10% → YELLOW, > 0% → GREEN
- Confidence weights: w1=0.5 (ensemble), w2=0.3 (quality), w3=0.2 (registration)
- Model promotion gates: Dice >= 0.82, ECE <= 0.05, diff F1 >= 0.75

### `configs/llm.yaml`
- Provider: openai (configurable)
- Model: gpt-4 (configurable)
- RAG: top_k=5, embedding_dim=768, score_threshold=0.7
- Report: max_tokens=4096, temperature=0.3
- Voice: Whisper medium model, 3-second latency target

### `configs/serve.yaml`
- API: port=8000, workers=4
- Celery: broker=redis://localhost:6379/0
- S3: endpoint=localhost:9000, bucket=brainscape
- Mesh: decimation_target=150000 polygons
- Signed URL expiry: 3600 seconds

### `configs/compliance.yaml`
- PHI entities: PERSON_NAME, DATE, EMAIL, PHONE, MRN, LOCATION, ORGANIZATION
- DICOM tags to scrub: PatientName, PatientID, PatientBirthDate, ReferringPhysicianName, etc.
- RBAC matrix: clinician (full access), researcher (anonymized only), patient (own scans only)
- Audit: storage=file, log_dir=data/audit
- Data residency: default_region=us-east-1, gdpr_regions=[eu-west-1]

---

## Test Coverage Summary

| Test File | Tests | Key Areas |
|-----------|-------|-----------|
| `test_ingestion.py` | Format detection, validation, PHI scrubbing | Detects NIfTI, compressed, image formats; validates SNR, dimensions; scrubs names, dates, emails, phones |
| `test_preprocessing.py` | Normalization, denoising, stage order | Z-score/min-max normalization, Gaussian smoothing, pipeline stage enforcement |
| `test_analysis.py` | Severity levels, classification, confidence | 5-level color contract, healthy/severe/moderate cases, confidence weights, JSON contract fields |
| `test_llm.py` | Prompts, RAG, QA, reports | Template rendering, embedding, chunking, fallback answers, citations, executive summary |
| `test_compliance.py` | RBAC, encryption, audit, consent | JWT creation/validation, role permissions, endpoint matching, encryption roundtrip, append-only log, opt-in/opt-out |
| `test_api.py` | Endpoints, auth, async | Health check, ingest auth, report access control, export formats, Phase 2/3 stubs |

---

## Memory & Context Notes

- All module implementations follow the same pattern: primary implementation using the specified tool (FSL, ANTs, nnU-Net, VTK, Weaviate) with a pure-Python fallback
- The severity color contract (#4A90D9, #27AE60, #F1C40F, #E67E22, #E74C3C) is the single most referenced configuration in the codebase
- The analysis JSON contract (with schema_version field) is the interface between analysis and LLM layers
- All API endpoints follow the async job pattern (POST returns job_id, GET /status polls)
- PHI anonymization is always synchronous and blocking — this is a hard requirement
- The system is designed so every component can be tested independently without the full stack