# Brain_Scape

End-to-end neuro-imaging intelligence platform — 3D brain reconstruction, AI-powered damage analysis, multimodal RAG, LLMs, and clinical-grade MLOps.

---

## What Is Brain_Scape?

Brain_Scape transforms raw MRI/fMRI/EEG scans into interactive 3D brain models with color-coded damage overlays, clinician-grade reports with literature citations, and a conversational Q&A engine — all backed by a HIPAA-compliant, audit-logged pipeline.

**Core capabilities:**

- **Ingestion**: Auto-detect scan format (DICOM, NIfTI, EDF, images) → validate → anonymize PHI → convert to NIfTI
- **Preprocessing**: Skull strip → motion correction → slice timing → denoising → intensity normalization → atlas registration (MNI152)
- **Analysis**: nnU-Net v2 segmentation → voxel-level severity scoring → 5-level color classification (BLUE/GREEN/YELLOW/ORANGE/RED) → 3-component confidence model
- **Reconstruction**: VTK marching cubes mesh → atlas region labeling → damage overlay → export GLB/OBJ/STL + 360-degree GIF
- **LLM + RAG**: PubMed/clinical literature retrieval → scan-aware Q&A → two-pass clinician report generation → PDF export
- **Compliance**: RBAC (clinician/researcher/patient) → AES-256 encryption → append-only audit log → patient consent management
- **MLOps**: Prefect orchestration → MLflow tracking → Celery + Redis async jobs → FastAPI REST API → Prometheus + Grafana monitoring

---

## Project Structure

```
BrainScape/
├── README.md                          ← You are here
├── docs/
│   ├── IMPLEMENTATION_PLAN.md         ← Full phased implementation plan
│   ├── PROGRESS.md                    ← What's built, what's next
│   └── CONVERSATION_LOG.md            ← Full conversation history & context
├── requirements.txt
├── setup.py
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
├── configs/
│   ├── pipeline.yaml
│   ├── preprocessing.yaml
│   ├── models.yaml
│   ├── llm.yaml
│   ├── serve.yaml
│   └── compliance.yaml
├── data/
│   ├── raw/                           ← Ingested scans (anonymized)
│   ├── processed/                     ← Preprocessing outputs
│   ├── registered/                    ← MNI152-registered volumes
│   ├── atlases/                      ← MNI152, AAL3, Brodmann, DK
│   └── samples/                      ← OpenNeuro sample datasets
├── ingestion/
│   ├── format_detector.py             ← Auto-detect scan format
│   ├── anonymizer.py                  ← Presidio PHI scrubbing (sync gate)
│   ├── converter.py                   ← DICOM/NIfTI/EDF/images → .nii.gz
│   ├── ocr_extractor.py               ← Tesseract metadata extraction
│   └── validator.py                   ← SNR, dimension, FOV checks
├── preprocessing/
│   ├── skull_stripper.py              ← FSL BET / Otsu fallback
│   ├── motion_corrector.py            ← FSL MCFLIRT / cross-correlation
│   ├── slice_timer.py                 ← Interleaved acquisition correction
│   ├── denoiser.py                    ← Gaussian / NLMeans smoothing
│   ├── intensity_normalizer.py        ← Z-score / min-max / histogram matching
│   └── atlas_registrar.py             ← ANTs SyN / FSL FNIRT fallback
├── analysis/
│   ├── segmentation/
│   │   ├── segmentor.py               ← nnU-Net v2 / intensity-threshold fallback
│   │   └── voxel_scorer.py            ← Per-region severity + volume metrics
│   ├── classification/
│   │   ├── damage_classifier.py        ← 5-level color contract
│   │   └── confidence_scorer.py        ← Ensemble + quality + registration
│   ├── connectivity/                  ← Phase 2: structural + functional
│   ├── fusion/                        ← Phase 2: multimodal fusion
│   └── longitudinal/                  ← Phase 2: temporal comparison
├── reconstruction/
│   ├── mesh_builder.py                ← VTK marching cubes + decimation
│   ├── region_labeler.py              ← Atlas intersection → anatomical names
│   ├── damage_overlay.py              ← Per-vertex severity coloring
│   ├── gif_exporter.py                ← 360-degree rotational animation
│   └── mesh_exporter.py               ← GLB (Draco) / OBJ / STL export
├── llm/
│   ├── rag_engine.py                  ← Weaviate/Pinecone + BioBERT retrieval
│   ├── qa_engine.py                   ← Scan-aware conversational Q&A
│   ├── report_generator.py            ← Two-pass LLM chain → PDF
│   └── prompt_templates.py            ← Versioned, centralized prompts
├── compliance/
│   ├── phi_scrubber.py                ← Presidio singleton wrapper
│   ├── encryption.py                  ← AES-256 (Fernet) at rest
│   ├── audit_logger.py                ← Append-only JSONL / Postgres
│   ├── rbac.py                        ← JWT + role permission matrix
│   └── consent_manager.py             ← Opt-in / opt-out patient consent
├── mlops/
│   ├── pipeline.py                    ← Prefect 7-task orchestration flow
│   ├── tracking.py                    ← MLflow experiment logging
│   ├── registry.py                    ← Model promotion gates (Dice ≥ 0.82)
│   ├── serve/
│   │   ├── api.py                     ← FastAPI REST endpoints
│   │   ├── task_queue.py              ← Celery + Redis async jobs
│   │   └── Dockerfile                 ← Python 3.11 + FSL + ANTs
│   └── monitoring/
│       ├── prometheus.yml             ← Scrape configs
│       └── grafana_dashboard.json      ← 7 clinical ops panels
├── frontend/
│   ├── index.html                     ← Dark-themed 3D viewer layout
│   ├── viewer/
│   │   ├── brain_viewer.js            ← Three.js + GLTFLoader + Draco
│   │   └── damage_overlay.js          ← Severity toggles + opacity
│   └── report/
│       └── clinician_report.html      ← Print-optimized CSS report
├── tests/
│   ├── test_ingestion.py
│   ├── test_preprocessing.py
│   ├── test_analysis.py
│   ├── test_llm.py
│   ├── test_compliance.py
│   └── test_api.py
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_preprocessing.ipynb
│   ├── 03_reconstruction.ipynb
│   ├── 04_analysis.ipynb
│   └── 05_llm_pipeline.ipynb
├── scripts/
│   ├── ingest.py                      ← CLI ingestion script
│   ├── run_pipeline.sh                ← One-command full pipeline
│   ├── download_atlases.sh            ← MNI152, AAL3, Brodmann, DK
│   └── seed_openneuro.py              ← Sample dataset downloader
└── migrations/
    ├── alembic.ini
    ├── env.py
    ├── script.py.mako
    └── versions/
        └── 001_initial_schema.py       ← users, scans, jobs, annotations, audit_logs, consent_records
```

---

## Quick Start

```bash
# 1. Setup
make setup

# 2. Download atlases and sample data
make download-atlases
make seed-data

# 3. Run the full pipeline on a scan
bash scripts/run_pipeline.sh /path/to/scan.nii.gz

# 4. Or use the API
docker-compose up
# POST /ingest → get job_id → poll GET /status/{job_id} → fetch results
```

---

## API Endpoints

| Method | Endpoint | Auth | Phase | Description |
|--------|----------|------|-------|-------------|
| `GET`  | `/health` | — | 1 | Service health check |
| `POST` | `/ingest` | JWT | 1 | Upload scan, get job_id (< 500ms) |
| `GET`  | `/status/{job_id}` | JWT | 1 | Poll pipeline status |
| `GET`  | `/mesh/{scan_id}` | JWT | 1 | Signed S3 URL for .glb + gif |
| `GET`  | `/report/{scan_id}?mode=clinician\|patient` | JWT | 1 | Signed S3 URL for PDF |
| `POST` | `/query` | JWT | 1 | Scan-aware LLM Q&A |
| `GET`  | `/export/{scan_id}?format=glb\|obj\|stl\|gif` | JWT | 1 | 302 redirect to signed URL |
| `GET`  | `/prognosis/{scan_id}` | JWT | 2 | Probabilistic recovery timeline |
| `GET`  | `/longitudinal?patient_id=X&scan_ids=A,B` | JWT | 2 | Multi-scan delta comparison |
| `POST` | `/diagnosis/{scan_id}` | JWT | 2 | Ranked differential diagnosis |
| `POST` | `/connectivity/{scan_id}` | JWT | 2 | Structural + functional connectivity |
| `POST` | `/treatment-planning/{scan_id}` | JWT | 3 | Eloquent cortex mapping, no-go zones |
| `POST` | `/annotate` | JWT | 3 | Save mesh annotation |
| `WS`   | `/ws/annotations/{scan_id}` | JWT | 3 | Real-time annotation collaboration |
| `GET`  | `/dashboard/{institution_id}` | JWT | 3 | Institutional stats dashboard |

---

## Severity Color Contract

Defined once in `configs/models.yaml`, referenced everywhere:

| Level | Label | Color | Hex | Meaning |
|-------|-------|-------|-----|---------|
| 0 | BLUE | `#4A90D9` | Not implicated |
| 1 | GREEN | `#27AE60` | No damage detected |
| 2 | YELLOW | `#F1C40F` | Mild abnormality |
| 3 | ORANGE | `#E67E22` | Moderate-to-severe |
| 4 | RED | `#E74C3C` | Severe damage |

---

## Preprocessing Pipeline Order

Must be executed in this order (defined in `configs/preprocessing.yaml`):

1. **Skull Stripping** — FSL BET (threshold 0.5) / Otsu fallback
2. **Motion Correction** — FSL MCFLIRT (fMRI only)
3. **Slice Timing** — Interleaved correction (fMRI only)
4. **Denoising** — Gaussian smoothing (FWHM 6mm)
5. **Intensity Normalization** — Z-score with percentile clipping
6. **Atlas Registration** — ANTs SyN (primary) / FSL FNIRT (fallback) — **MUST be last**

---

## Configuration

All configs are in `configs/`:

- `pipeline.yaml` — Stage toggles, timeouts, checkpoint/resume
- `preprocessing.yaml` — FSL BET threshold, MCFLIRT params, ANTs iterations
- `models.yaml` — nnU-Net config, severity thresholds, confidence weights, promotion gates
- `llm.yaml` — Provider, model, RAG top-k, embedding dimension, report generation params
- `serve.yaml` — API port/workers, Celery config, S3 storage, mesh decimation
- `compliance.yaml` — PHI entities, DICOM/EXIF tags, RBAC permission matrix, data residency

---

## Testing

```bash
# Run all tests
make test
# or
pytest tests/ -v

# Run specific test modules
pytest tests/test_compliance.py -v    # RBAC, encryption, audit, consent
pytest tests/test_analysis.py -v      # Segmentation, classification, confidence
pytest tests/test_api.py -v           # FastAPI endpoints, JWT auth
```

---

## Docker

```bash
# Start all services
make up

# Stop all services
make down

# View logs
docker-compose logs -f brainscape-api
```

9 containers: `brainscape-api` (2 replicas), `brainscape-worker-cpu`, `brainscape-worker-gpu`, `brainscape-redis`, `brainscape-postgres`, `brainscape-minio`, `brainscape-mlflow`, `brainscape-prometheus`, `brainscape-grafana`

---

## Key Engineering Decisions

1. **nnU-Net over custom model** — self-configuring, state-of-the-art on neuroimaging benchmarks
2. **ANTs SyN primary, FSL FNIRT fallback** — most accurate registration, configurable in YAML
3. **Async pipeline with job IDs** — not latency-sensitive; enables checkpoint-and-resume
4. **RAG over fine-tuning** — forces citations, clinically verifiable claims
5. **Two-pass LLM chain** — decouples clinician and patient report formats
6. **Compliance as synchronous gate** — PHI never enters any queue unmasked
7. **Every fallback works standalone** — all neuroimaging tools (FSL, ANTs, nnU-Net) have Python fallbacks for development without GPU/tools

---

## License

Proprietary — see LICENSE file for details.