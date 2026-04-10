.PHONY: setup up down test pipeline lint clean

# ── Setup ──
setup:
	python -m venv venv
	. venv/bin/activate && pip install -e ".[dev]"
	pip install -r requirements.txt
	mkdir -p data/raw data/processed data/registered data/samples
	@echo "Downloading atlas files..."
	bash scripts/download_atlases.sh

# ── Docker ──
up:
	docker compose up -d
	@echo "Brain_Scape is running. API at http://localhost:8000"

down:
	docker compose down

# ── Pipeline ──
pipeline:
	. venv/bin/activate && python -m mlops.pipeline

# ── Ingest ──
ingest:
	. venv/bin/activate && python scripts/ingest.py

# ── Tests ──
test:
	. venv/bin/activate && pytest tests/ -v --cov=ingestion --cov=preprocessing --cov=analysis --cov=llm --cov=compliance --cov=mlops

test-ingestion:
	. venv/bin/activate && pytest tests/test_ingestion.py -v

test-preprocessing:
	. venv/bin/activate && pytest tests/test_preprocessing.py -v

test-analysis:
	. venv/bin/activate && pytest tests/test_analysis.py -v

test-llm:
	. venv/bin/activate && pytest tests/test_llm.py -v

test-compliance:
	. venv/bin/activate && pytest tests/test_compliance.py -v

test-api:
	. venv/bin/activate && pytest tests/test_api.py -v

# ── Lint ──
lint:
	. venv/bin/activate && ruff check . && mypy .

# ── Clean ──
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache

# ── Database ──
db-init:
	. venv/bin/activate && alembic upgrade head

db-migrate:
	. venv/bin/activate && alembic revision --autogenerate -m "$(msg)"

# ── Atlases ──
download-atlases:
	bash scripts/download_atlases.sh

seed-data:
	. venv/bin/activate && python scripts/seed_openneuro.py