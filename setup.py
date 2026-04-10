"""
Brain_Scape — Brain Reconstruction and Analysis Intelligence Network
for Scan-based Clinical Assessment and Prognosis Engine
"""

from setuptools import setup, find_packages

setup(
    name="brainscape",
    version="1.0.0",
    description="Neuro-imaging intelligence platform combining 3D brain reconstruction, "
                "AI-powered damage analysis, multimodal RAG, and clinical-grade MLOps.",
    author="Brain_Scape Team",
    python_requires=">=3.10",
    packages=find_packages(include=[
        "ingestion",
        "preprocessing",
        "reconstruction",
        "analysis",
        "analysis.segmentation",
        "analysis.classification",
        "analysis.connectivity",
        "analysis.fusion",
        "analysis.longitudinal",
        "analysis.treatment",
        "llm",
        "compliance",
        "mlops",
        "mlops.serve",
        "mlops.dashboard",
    ]),
    install_requires=[
        "nibabel>=5.2",
        "nilearn>=0.10",
        "vtk>=9.3",
        # antspy>=0.3  # No Windows wheels — fallback used
        "torch>=2.3",
        "monai>=1.3",
        "nnunetv2>=2.5",
        "fastapi>=0.111",
        "uvicorn[standard]>=0.30",
        "celery[redis]>=5.4",
        "redis>=5.0",
        "prefect>=2.19",
        "mlflow>=2.14",
        "presidio-analyzer>=2.2",
        "presidio-anonymizer>=2.2",
        "cryptography>=42.0",
        "PyJWT>=2.8",
        "langchain>=0.2",
        "langchain-openai>=0.1",
        "openai>=1.35",
        "reportlab>=4.2",
        "jinja2>=3.1",
        "sqlalchemy>=2.0",
        "psycopg2-binary>=2.9",
        "alembic>=1.13",
        "boto3>=1.34",
        "pydicom>=2.4",
        "pytesseract>=0.3",
        "Pillow>=10.3",
        "pyyaml>=6.0",
        "python-dotenv>=1.0",
        "click>=8.1",
        "numpy>=1.26",
        "scipy>=1.14",
    ],
    extras_require={
        "dev": [
            "pytest>=8.2",
            "pytest-asyncio>=0.23",
            "httpx>=0.27",
            "pytest-cov>=5.0",
        ],
        "gpu": [
            "torch>=2.3",
        ],
    },
    entry_points={
        "console_scripts": [
            "brainscape-ingest=scripts.ingest:main",
            "brainscape-pipeline=mlops.pipeline:run_pipeline",
            "brainscape-api=mlops.serve.api:main",
        ],
    },
)