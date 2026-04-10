# Brain_Scape — Run Guide

How to run Brain_Scape in various environments: local development, Docker, GPU-enabled, cloud, and production.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start (Local, No Docker)](#2-quick-start-local-no-docker)
3. [Docker Compose (Full Stack)](#3-docker-compose-full-stack)
4. [GPU Setup (nnU-Net, ANTs)](#4-gpu-setup-nnunet-ants)
5. [Cloud Deployment (AWS)](#5-cloud-deployment-aws)
6. [Kubernetes (Production)](#6-kubernetes-production)
7. [Jupyter Notebooks](#7-jupyter-notebooks)
8. [CLI Pipeline (One Command)](#8-cli-pipeline-one-command)
9. [API-Only Mode](#9-api-only-mode)
10. [Environment Variables Reference](#10-environment-variables-reference)
11. [Service Ports Reference](#11-service-ports-reference)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

### Minimum (for development with fallbacks)
- Python 3.10+
- pip
- 8 GB RAM
- 5 GB disk space

### Recommended (for full pipeline)
- Python 3.10+
- NVIDIA GPU with CUDA 11.8+ (for nnU-Net segmentation)
- 16 GB RAM (32 GB recommended for large scans)
- 50 GB disk space (atlases + sample data + outputs)
- Docker & Docker Compose (for full stack)

### External Tools (optional but recommended)
- **FSL** — Skull stripping (BET), motion correction (MCFLIRT), registration (FNIRT)
- **ANTs** — Non-linear atlas registration (SyN)
- **Tesseract OCR** — Metadata extraction from scan printouts

> All modules have pure-Python fallbacks. The system runs without these tools, but outputs will be lower quality.

---

## 2. Quick Start (Local, No Docker)

The fastest way to get Brain_Scape running locally. Uses in-memory and file-based fallbacks for Redis, Postgres, and S3.

### Step 1: Clone and enter the project

```bash
cd BrainScape
```

### Step 2: Create a virtual environment

```bash
# Linux / macOS
python -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Windows (Git Bash)
python -m venv venv
source venv/Scripts/activate
```

### Step 3: Install dependencies

```bash
# Install the brainscape package in development mode
pip install -e ".[dev]"

# Install all pinned dependencies
pip install -r requirements.txt
```

> If some neuroimaging packages (vtk, antspy, nnunetv2) fail to install, that is OK. Fallbacks will be used.

### Step 4: Create data directories

```bash
mkdir -p data/raw data/processed data/registered data/atlases data/samples data/outputs
```

### Step 5: Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` — for local-only mode, the defaults work as-is. The only thing you may want to set:

```bash
# Only needed if you want real LLM responses (otherwise template-based fallback is used)
OPENAI_API_KEY=sk-your-key-here
```

### Step 6: Download atlas files

```bash
bash scripts/download_atlases.sh
```

This downloads:
- MNI152_T1_1mm template (~30 MB)
- AAL3 atlas labels (~5 MB)
- Brodmann area map (~5 MB)
- Desikan-Killiany parcellation (~5 MB)

### Step 7: (Optional) Download sample data

```bash
python scripts/seed_openneuro.py
```

Downloads ~500 MB of sample OpenNeuro MRI/fMRI/EEG datasets.

### Step 8: Run the API server

```bash
uvicorn mlops.serve.api:app --host 0.0.0.0 --port 8000 --reload
```

Visit http://localhost:8000/health to verify it's running.

### Step 9: Process a scan

```bash
# Option A: Via API
curl -X POST http://localhost:8000/ingest \
  -F "file=@data/samples/sample_t1.nii.gz" \
  -H "Authorization: Bearer <your-jwt-token>"

# Option B: Via CLI script
python scripts/ingest.py data/samples/sample_t1.nii.gz

# Option C: Full pipeline in one command
bash scripts/run_pipeline.sh data/samples/sample_t1.nii.gz
```

### Step 10: Run tests

```bash
pytest tests/ -v
```

---

## 3. Docker Compose (Full Stack)

Runs all 9 containers: API, CPU worker, GPU worker, Postgres, Redis, MinIO, MLflow, Prometheus, Grafana.

### Step 1: Install Docker

- [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
- [Docker Engine for Linux](https://docs.docker.com/engine/install/)

Ensure Docker Compose v2+ is installed:

```bash
docker compose version
```

### Step 2: Set up environment

```bash
cp .env.example .env
# Edit .env with your settings if needed
```

### Step 3: Start all services

```bash
# Build and start all containers
docker compose up -d

# Or use the Makefile shortcut
make up
```

### Step 4: Verify all containers are running

```bash
docker compose ps
```

You should see 9 containers:

| Container | Port | Purpose |
|-----------|------|---------|
| `brainscape-api` | 8000 | FastAPI REST API |
| `brainscape-worker-cpu` | — | Celery CPU tasks (ingestion, LLM) |
| `brainscape-worker-gpu` | — | Celery GPU tasks (nnU-Net, classification) |
| `postgres` | 5432 | PostgreSQL database |
| `redis` | 6379 | Celery broker + result backend |
| `minio` | 9000/9001 | S3-compatible object storage |
| `mlflow` | 5000 | Experiment tracking UI |
| `prometheus` | 9090 | Metrics collection |
| `grafana` | 3000 | Monitoring dashboards |

### Step 5: Initialize the database

```bash
docker compose exec brainscape-api alembic upgrade head
```

### Step 6: Create the S3 bucket

```bash
# Access MinIO console at http://localhost:9001
# Login: minioadmin / minioadmin
# Create bucket: brainscape-scans
```

Or via CLI:

```bash
docker compose exec brainscape-api python -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://minio:9000',
                   aws_access_key_id='minioadmin',
                   aws_secret_access_key='minioadmin')
s3.create_bucket(Bucket='brainscape-scans')
print('Bucket created')
"
```

### Step 7: Download atlases inside the API container

```bash
docker compose exec brainscape-api bash scripts/download_atlases.sh
```

### Step 8: Upload and process a scan

```bash
# Get a JWT token first (create a test clinician)
docker compose exec brainscape-api python -c "
from compliance.rbac import RBACManager
rbac = RBACManager(secret_key='change-this-in-production')
token = rbac.create_access_token(user_id='clinician-1', role='clinician', institution='hospital-1')
print(token)
"

# Upload via API
curl -X POST http://localhost:8000/ingest \
  -F "file=@data/samples/sample_t1.nii.gz" \
  -H "Authorization: Bearer <token-from-above>"
```

### Step 9: Monitor the pipeline

```bash
# Check job status
curl http://localhost:8000/status/<job_id> \
  -H "Authorization: Bearer <token>"

# View Grafana dashboards
open http://localhost:3000  # admin / admin

# View MLflow experiments
open http://localhost:5000
```

### Step 10: Stop all services

```bash
docker compose down

# Stop and remove volumes (deletes all data)
docker compose down -v

# Makefile shortcut
make down
```

### Useful Docker Commands

```bash
# View logs
docker compose logs -f brainscape-api
docker compose logs -f brainscape-worker-gpu

# Restart a single service
docker compose restart brainscape-api

# Rebuild after code changes
docker compose build brainscape-api
docker compose up -d brainscape-api

# Shell into a container
docker compose exec brainscape-api bash

# Resource usage
docker compose top
```

---

## 4. GPU Setup (nnU-Net, ANTs)

GPU acceleration is needed for nnU-Net segmentation (5-15 min on GPU vs 1-2 hours on CPU).

### NVIDIA Driver + CUDA

```bash
# Verify NVIDIA driver
nvidia-smi

# Verify CUDA
nvcc --version
```

Required: NVIDIA driver 525+, CUDA 11.8+ or 12.1+.

### PyTorch with CUDA

```bash
# Install PyTorch with CUDA 11.8
pip install torch==2.3.1 --index-url https://download.pytorch.org/whl/cu118

# Install PyTorch with CUDA 12.1
pip install torch==2.3.1 --index-url https://download.pytorch.org/whl/cu121

# Verify GPU is accessible
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

### Docker with GPU

Docker Compose already configures GPU for the `brainscape-worker-gpu` container:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

You need the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html):

```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Verify
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### nnU-Net Configuration

```bash
# Set environment variables for nnU-Net
export nnUNet_raw="data/nnunet/raw"
export nnUNet_preprocessed="data/nnunet/preprocessed"
export nnUNet_results="data/nnunet/results"

# Or add to .env:
echo 'nnUNet_raw=data/nnunet/raw' >> .env
echo 'nnUNet_preprocessed=data/nnunet/preprocessed' >> .env
echo 'nnUNet_results=data/nnunet/results' >> .env
```

### Running on CPU Only (Slower)

If no GPU is available, nnU-Net falls back to CPU inference. Set:

```bash
export CUDA_VISIBLE_DEVICES=""
```

This triggers the intensity-threshold fallback in `segmentor.py`, which is fast but less accurate.

---

## 5. Cloud Deployment (AWS)

### Architecture on AWS

```
Internet → ALB → ECS Fargate (API + workers)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   RDS Postgres  ElastiCache   S3 Bucket
   (multi-AZ)    (Redis)      (scan artifacts)
                    │
                    ▼
              SageMaker (GPU inference)
                    │
                    ▼
              MLflow on ECS
```

### Step 1: Create ECR repositories

```bash
aws ecr create-repository --repository-name brainscape-api
aws ecr create-repository --repository-name brainscape-worker-cpu
aws ecr create-repository --repository-name brainscape-worker-gpu
```

### Step 2: Build and push images

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -f mlops/serve/Dockerfile -t brainscape-api .
docker tag brainscape-api:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/brainscape-api:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/brainscape-api:latest
```

### Step 3: Provision infrastructure

```bash
# Using Terraform (recommended) or CloudFormation
# Key resources:
# - VPC with public + private subnets (multi-AZ)
# - RDS Postgres 16 (multi-AZ, encrypted)
# - ElastiCache Redis 7
# - S3 bucket with versioning + encryption
# - ECS cluster with Fargate tasks
# - ALB with HTTPS (ACM certificate)
# - CloudWatch for logging
# - SageMaker endpoint for GPU inference (optional)
```

### Step 4: Configure environment

```bash
# Update .env or ECS task definitions with production values:
DATABASE_URL=postgresql://brainscape:<strong-password>@<rds-endpoint>:5432/brainscape
REDIS_URL=redis://<elasticache-endpoint>:6379/0
S3_ENDPOINT=https://s3.us-east-1.amazonaws.com
S3_BUCKET=brainscape-scans-prod
MLFLOW_TRACKING_URI=http://<mlflow-endpoint>:5000
JWT_SECRET_KEY=<64-char-random-string>
ENCRYPTION_KEY=<32-byte-key>
```

### Step 5: Database migration

```bash
# Run inside an ECS task or from a bastion host
alembic upgrade head
```

### Step 6: Health check

```bash
curl https://<alb-dns>/health
# Expected: {"api": "ok", "database": "ok", "redis": "ok"}
```

---

## 6. Kubernetes (Production)

For large-scale or regulated deployments.

### Step 1: Create namespace and secrets

```bash
kubectl create namespace brainscape

kubectl create secret generic brainscape-secrets \
  --from-literal=DATABASE_URL='postgresql://brainscape:password@postgres:5432/brainscape' \
  --from-literal=REDIS_URL='redis://redis:6379/0' \
  --from-literal=JWT_SECRET_KEY='your-secret-key' \
  --from-literal=ENCRYPTION_KEY='your-encryption-key' \
  --from-literal=OPENAI_API_KEY='sk-...' \
  -n brainscape
```

### Step 2: Apply manifests

```bash
# Postgres (StatefulSet)
kubectl apply -f k8s/postgres.yaml -n brainscape

# Redis (StatefulSet)
kubectl apply -f k8s/redis.yaml -n brainscape

# MinIO (StatefulSet)
kubectl apply -f k8s/minio.yaml -n brainscape

# API (Deployment + Service)
kubectl apply -f k8s/api.yaml -n brainscape

# CPU Worker (Deployment)
kubectl apply -f k8s/worker-cpu.yaml -n brainscape

# GPU Worker (Deployment with nvidia.com/gpu resource)
kubectl apply -f k8s/worker-gpu.yaml -n brainscape

# Ingress (with TLS)
kubectl apply -f k8s/ingress.yaml -n brainscape
```

### Step 3: GPU node pool

For the GPU worker, your cluster needs GPU nodes:

```bash
# GKE
gcloud container node-pools create gpu-pool \
  --cluster=brainscape \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=1

# EKS
# Use a GPU-optimized AMI and launch template with g4dn.xlarge instances

# AKS
az aks nodepool add --name gpupool --resource-group rg \
  --cluster-name brainscape --node-vm-size Standard_NC6s_v3
```

### Step 4: Run migration job

```bash
kubectl apply -f k8s/migration-job.yaml -n brainscape
kubectl wait --for=condition=complete job/brainscape-migration -n brainscape
```

### Step 5: Verify

```bash
kubectl get pods -n brainscape
kubectl port-forward svc/brainscape-api 8000:8000 -n brainscape
curl http://localhost:8000/health
```

---

## 7. Jupyter Notebooks

Interactive exploration of each pipeline stage.

### Step 1: Install Jupyter

```bash
pip install jupyter jupyterlab
```

### Step 2: Start Jupyter

```bash
cd notebooks
jupyter lab
```

### Step 3: Run notebooks in order

| Notebook | Purpose |
|----------|---------|
| `01_data_exploration.ipynb` | Load scans, visualize slices, SNR, format detection |
| `02_preprocessing.ipynb` | Run all 6 preprocessing stages, before/after comparison |
| `03_reconstruction.ipynb` | Build 3D mesh, label regions, export GLB/OBJ/STL/GIF |
| `04_analysis.ipynb` | Segment, score, classify damage, compute confidence |
| `05_llm_pipeline.ipynb` | RAG retrieval, Q&A, report generation, PDF export |

### Running with Docker

```bash
docker compose exec brainscape-api jupyter lab --port 8888 --no-browser --ip=0.0.0.0
# Then open http://localhost:8888 in your browser
```

---

## 8. CLI Pipeline (One Command)

Process a scan from ingestion to export in a single command.

### Full pipeline

```bash
bash scripts/run_pipeline.sh /path/to/scan.nii.gz
```

Optional: specify modalities

```bash
bash scripts/run_pipeline.sh /path/to/scan.nii.gz --modalities MRI_T1 fMRI
```

### What it does

1. **Ingest**: Detect format → validate → anonymize PHI → convert to NIfTI
2. **Preprocess**: Skull strip → normalize → denoise → atlas register
3. **Analyze + Reconstruct + Report**: Via Prefect pipeline (`python -m mlops.pipeline`)

### Output

Results are saved to `outputs/{job_id}/`:

```
outputs/<job-id>/
├── analysis.json          ← Damage summary, confidence, regions
├── lesion_mask.nii.gz     ← Binary segmentation mask
├── brain_mesh.obj         ← Full-resolution 3D mesh
├── brain.glb              ← Draco-compressed for web viewer
├── brain_view.obj         ← OBJ for surgical tools
├── brain_print.stl        ← STL for 3D printing
├── brain_rotation.gif     ← 360-degree animation
├── damage_map.json        ← Per-vertex severity colors
└── clinician_report.pdf   ← Structured clinical report
```

### Ingestion only (no processing)

```bash
python scripts/ingest.py /path/to/scan --job-id my-test-scan --modalities MRI_T1
```

---

## 9. API-Only Mode

Run just the FastAPI server without Docker Compose infrastructure. Uses file-based fallbacks.

### Start the API

```bash
# Development (with auto-reload)
uvicorn mlops.serve.api:app --host 0.0.0.0 --port 8000 --reload

# Production (multiple workers)
uvicorn mlops.serve.api:app --host 0.0.0.0 --port 8000 --workers 4
```

### Without Redis/Postgres/MinIO

The system degrades gracefully:

| Service | Without It | Fallback |
|---------|-----------|----------|
| PostgreSQL | Job states not persisted | In-memory dict (lost on restart) |
| Redis | No Celery task queue | Synchronous processing (blocks API) |
| MinIO/S3 | No object storage | Local filesystem (`data/` directory) |
| MLflow | No experiment tracking | File-based CSV logging |
| Weaviate/Pinecone | No RAG retrieval | Template-based Q&A answers |

### Quick API test

```bash
# Health check
curl http://localhost:8000/health

# Get a test token
python -c "
from compliance.rbac import RBACManager
rbac = RBACManager(secret_key='change-this-in-production')
print(rbac.create_access_token(user_id='test-clinician', role='clinician'))
"

# Upload a scan
export TOKEN="<token-from-above>"
curl -X POST http://localhost:8000/ingest \
  -F "file=@data/samples/sample_t1.nii.gz" \
  -H "Authorization: Bearer $TOKEN"

# Check job status
curl http://localhost:8000/status/<job_id> \
  -H "Authorization: Bearer $TOKEN"

# Query the scan
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scan_id": "<scan_id>", "question": "What regions are damaged?"}'

# Get the 3D mesh
curl http://localhost:8000/mesh/<scan_id> \
  -H "Authorization: Bearer $TOKEN"

# Get the report
curl "http://localhost:8000/report/<scan_id>?mode=clinician" \
  -H "Authorization: Bearer $TOKEN"

# Export in a specific format
curl "http://localhost:8000/export/<scan_id>?format=glb"
```

---

## 10. Environment Variables Reference

All variables can be set in `.env`, in the shell environment, or in Docker Compose environment blocks.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | `postgresql://brainscape:brainscape@localhost:5432/brainscape` | No* | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | No* | Redis connection string |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | No* | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | No* | Celery result backend |
| `S3_ENDPOINT` | `http://localhost:9000` | No* | MinIO/S3 endpoint |
| `S3_ACCESS_KEY` | `minioadmin` | No* | S3 access key |
| `S3_SECRET_KEY` | `minioadmin` | No* | S3 secret key |
| `S3_BUCKET` | `brainscape-scans` | No* | S3 bucket name |
| `OPENAI_API_KEY` | — | No | OpenAI API key (for LLM responses) |
| `LLM_MODEL` | `gpt-4` | No | LLM model name |
| `LLM_TEMPERATURE` | `0.2` | No | LLM temperature |
| `LLM_MAX_TOKENS` | `4096` | No | Max LLM output tokens |
| `VECTOR_STORE` | `weaviate` | No | `weaviate` or `pinecone` |
| `WEAVIATE_URL` | `http://localhost:8080` | No | Weaviate endpoint |
| `PINECONE_API_KEY` | — | No | Pinecone API key |
| `EMBEDDING_MODEL` | `pubmedbert` | No | Embedding model name |
| `EMBEDDING_DIMENSION` | `768` | No | Embedding vector dimension |
| `JWT_SECRET_KEY` | `change-this-in-production` | **Yes** | Secret for JWT signing |
| `JWT_ALGORITHM` | `RS256` | No | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | No | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | No | Refresh token lifetime |
| `ENCRYPTION_KEY` | — | **Yes** | AES-256 encryption key |
| `DATA_RESIDENCY_REGION` | `US` | No | Data residency for GDPR |
| `PHI_SCRUBBING_ENABLED` | `true` | No | Enable/disable PHI scrubbing |
| `MLFLOW_TRACKING_URI` | `http://localhost:5000` | No* | MLflow endpoint |
| `MLFLOW_EXPERIMENT_NAME` | `brainscape` | No | MLflow experiment name |
| `CUDA_VISIBLE_DEVICES` | `0` | No | GPU device index |
| `GPU_WORKER_COUNT` | `2` | No | GPU worker concurrency |
| `CPU_WORKER_COUNT` | `4` | No | CPU worker concurrency |

\* Required for Docker Compose / production. Optional for local dev (fallbacks available).

---

## 11. Service Ports Reference

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| API | 8000 | http://localhost:8000 | FastAPI REST endpoints |
| API Docs | 8000 | http://localhost:8000/docs | Swagger UI |
| MinIO API | 9000 | http://localhost:9000 | S3-compatible storage |
| MinIO Console | 9001 | http://localhost:9001 | MinIO web UI (minioadmin/minioadmin) |
| MLflow | 5000 | http://localhost:5000 | Experiment tracking UI |
| Grafana | 3000 | http://localhost:3000 | Monitoring dashboards (admin/admin) |
| Prometheus | 9090 | http://localhost:9090 | Metrics UI |
| PostgreSQL | 5432 | localhost:5432 | Database (brainscape/brainscape) |
| Redis | 6379 | localhost:6379 | Cache + job queue |
| Jupyter | 8888 | http://localhost:8888 | Notebooks (when running) |

---

## 12. Troubleshooting

### `nibabel` / `vtk` / `antspy` install fails

These packages require C extensions. Solutions:

```bash
# macOS: install Xcode command line tools
xcode-select --install

# Ubuntu/Debian: install build dependencies
sudo apt-get install build-essential python3-dev libgl1-mesa-glx

# Windows: use pre-built wheels
pip install vtk --find-links https://vtk.org/download/

# Or skip them — fallbacks are used automatically
pip install nibabel nilearn  # minimal neuroimaging deps
```

### `nnunetv2` install fails

nnU-Net requires PyTorch first:

```bash
pip install torch==2.3.1  # CPU-only version
pip install nnunetv2
```

### Docker GPU worker fails to start

```bash
# Check NVIDIA runtime
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# If error: install NVIDIA Container Toolkit
# See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

# If no GPU available, remove the GPU worker from docker-compose.yml
# and use CPU-only inference (set CUDA_VISIBLE_DEVICES="")
```

### PostgreSQL connection refused

```bash
# Check if Postgres is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# If running locally (not Docker):
# Ensure Postgres is installed and running
pg_isready -h localhost -p 5432

# Create the database
createdb -U postgres brainscape
```

### Redis connection refused

```bash
# Check if Redis is running
docker compose ps redis

# If running locally:
redis-cli ping  # Should return PONG

# Start Redis locally (if not using Docker)
redis-server
```

### MinIO bucket not found

```bash
# Access MinIO console at http://localhost:9001
# Login: minioadmin / minioadmin
# Create the bucket manually, or:

# Via AWS CLI
aws --endpoint-url http://localhost:9000 s3 mb s3://brainscape-scans

# Via Python boto3
python -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
                   aws_access_key_id='minioadmin',
                   aws_secret_access_key='minioadmin')
s3.create_bucket(Bucket='brainscape-scans')
"
```

### Alembic migration fails

```bash
# Check database connectivity
docker compose exec brainscape-api python -c "
import psycopg2
conn = psycopg2.connect('postgresql://brainscape:brainscape@postgres:5432/brainscape')
print('Database connected')
conn.close()
"

# Run migration manually
docker compose exec brainscape-api alembic upgrade head

# If migration is already applied
docker compose exec brainscape-api alembic current

# Reset and re-run
docker compose exec brainscape-api alembic downgrade base
docker compose exec brainscape-api alembic upgrade head
```

### Tests fail due to missing scan data

```bash
# Download sample data first
python scripts/seed_openneuro.py

# Or run tests with mocks only (no file I/O)
pytest tests/ -v -k "not requires_data"
```

### API returns 401 Unauthorized

```bash
# Generate a valid JWT token
python -c "
from compliance.rbac import RBACManager
rbac = RBACManager(secret_key='change-this-in-production')
token = rbac.create_access_token(user_id='test-user', role='clinician')
print(f'Bearer {token}')
"

# Use the token in requests
curl -H "Authorization: Bearer <token>" http://localhost:8000/health
```

### OOM during nnU-Net segmentation

```bash
# Reduce batch size in configs/models.yaml
nnunet:
  trainer: nnUNetTrainerV2
  plans: nnUNetPlans
  fold: 0
  batch_size: 1          # Reduce from default
  input_patch_size: [128, 128, 128]  # Reduce from default

# Or use CPU fallback (no GPU memory needed)
export CUDA_VISIBLE_DEVICES=""
```

### Port already in use

```bash
# Find what's using the port
lsof -i :8000    # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Change the port
uvicorn mlops.serve.api:app --port 8001

# Or update configs/serve.yaml and docker-compose.yml
```

### Frontend can't connect to API

The frontend (`frontend/index.html`) connects to the API at `http://localhost:8000` by default. To change:

1. Edit `frontend/viewer/brain_viewer.js` — find the `API_URL` constant
2. Or serve the frontend through the API (add static file mounting)

For CORS issues, update `configs/serve.yaml`:

```yaml
api:
  cors_origins:
    - "http://localhost:3000"
    - "http://localhost:8000"
    - "http://127.0.0.1:5500"  # VS Code Live Server
```

---

## Summary: Which Mode To Use

| Scenario | Recommended Setup | Command |
|----------|-------------------|---------|
| Just exploring the code | Local, no Docker | `pip install -e . && uvicorn mlops.serve.api:app` |
| Running notebooks | Local + Jupyter | `jupyter lab` in notebooks/ |
| Processing one scan | CLI pipeline | `bash scripts/run_pipeline.sh <scan>` |
| Full development environment | Docker Compose | `docker compose up -d` |
| GPU inference testing | Docker Compose + NVIDIA | `docker compose up -d` (with nvidia toolkit) |
| Production (small scale) | Docker Compose on VM | `docker compose up -d` with production .env |
| Production (large scale) | Kubernetes on cloud | `kubectl apply -f k8s/` |
| HIPAA-compliant deployment | AWS ECS + RDS + CloudHSM | Terraform + production .env |