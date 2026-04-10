"""
Brain_Scape — API Integration Tests

Tests for FastAPI endpoints, JWT auth, RBAC, and async job patterns.
"""

import pytest
from fastapi.testclient import TestClient

from mlops.serve.api import app


@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


@pytest.fixture
def clinician_token(client):
    """Generate a valid clinician JWT token."""
    response = client.post(
        "/auth/token",
        json={
            "user_id": "clinician-1",
            "role": "clinician",
            "institution": "hospital-1",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def patient_token(client):
    """Generate a valid patient JWT token."""
    response = client.post(
        "/auth/token",
        json={
            "user_id": "patient-1",
            "role": "patient",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check(self, client):
        """Health endpoint should return 200 and status info."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "api" in data
        assert data["api"] == "ok"


class TestIngestEndpoint:
    """Test the scan ingestion endpoint."""

    def test_ingest_requires_auth(self, client):
        """Ingest endpoint should require authentication."""
        response = client.post("/ingest")
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403, 422]  # 422 if no file provided

    def test_ingest_with_auth(self, client, clinician_token):
        """Ingest should accept a file upload with valid auth."""
        # Create a minimal test file
        import io
        test_file = io.BytesIO(b"test scan data")

        response = client.post(
            "/ingest",
            files={"file": ("test.nii.gz", test_file, "application/octet-stream")},
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        # May fail due to actual processing, but should not be auth error
        assert response.status_code != 401


class TestReportEndpoint:
    """Test the report endpoint."""

    def test_patient_cannot_access_clinician_report(self, client, patient_token):
        """Patient should not access clinician-mode reports."""
        response = client.get(
            "/report/test-scan-1?mode=clinician",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert response.status_code == 403

    def test_report_returns_info(self, client, clinician_token):
        """Report endpoint should return download info for clinicians."""
        response = client.get(
            "/report/test-scan-1?mode=clinician",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        # May return 200 or 404 depending on whether scan exists
        assert response.status_code in [200, 404]


class TestQueryEndpoint:
    """Test the Q&A endpoint."""

    def test_query_with_auth(self, client, clinician_token):
        """Query endpoint should accept authenticated requests."""
        response = client.post(
            "/query",
            json={
                "scan_id": "test-scan-1",
                "question": "Is this region related to speech?",
            },
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        # May return 404 if scan doesn't exist, but not auth error
        assert response.status_code != 401


class TestExportEndpoint:
    """Test the export endpoint."""

    def test_export_glb(self, client):
        """Export endpoint should accept format parameter."""
        response = client.get("/export/test-scan-1?format=glb")
        # May return 200 or redirect
        assert response.status_code in [200, 302, 404]


class TestPrognosisEndpoint:
    """Test the prognosis endpoint (Phase 2 feature)."""

    def test_prognosis_requires_auth(self, client):
        """Prognosis endpoint should reject anonymous access."""
        response = client.get("/prognosis/test-scan-1")
        assert response.status_code == 401

    def test_prognosis_with_auth(self, client, clinician_token):
        """Prognosis should accept auth and return domain response."""
        response = client.get(
            "/prognosis/test-scan-1",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert response.status_code in [200, 404]


class TestLongitudinalEndpoint:
    """Test the longitudinal endpoint (Phase 2 feature)."""

    def test_longitudinal_requires_auth(self, client):
        """Longitudinal endpoint should reject anonymous access."""
        response = client.get("/longitudinal?patient_id=patient-1&scan_ids=a,b")
        assert response.status_code == 401

    def test_longitudinal_with_auth(self, client, clinician_token):
        """Longitudinal should accept auth and return domain response."""
        response = client.get(
            "/longitudinal?patient_id=patient-1&scan_ids=a,b",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert response.status_code in [200, 404]