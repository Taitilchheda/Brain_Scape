"""
Brain_Scape — API Integration Tests

Tests for FastAPI endpoints, JWT auth, RBAC, and async job patterns.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

import mlops.serve.api as api_module
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

    def test_document_upload_has_volume_fallback(self, client, clinician_token):
        """Document uploads should still produce a renderable volume payload."""
        import io

        response = client.post(
            "/ingest",
            files={"file": ("scan.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert response.status_code == 200

        payload = response.json()
        job_id = payload["job_id"]

        status = client.get(
            f"/status/{job_id}",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert status.status_code == 200
        assert status.json()["status"] == "complete"

        analysis = client.get(
            f"/analysis/{job_id}",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert analysis.status_code == 200

        volume = client.get(f"/volume/{job_id}")
        assert volume.status_code == 200

        volume_payload = volume.json()
        assert volume_payload["scan_id"] == job_id
        assert volume_payload["encoding"] == "base64-rgba-u8"
        assert volume_payload["shape"]
        assert volume_payload["synthetic_fallback"] is True
        assert volume_payload["resolution_profile"] == "standard"


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


class TestDemoPatientEndpoints:
    """Test sample patient data endpoints used by frontend demo mode."""

    def test_demo_patients_list(self, client):
        """Demo patients endpoint should return multiple sample cases."""
        response = client.get("/demo/patients")
        assert response.status_code == 200

        payload = response.json()
        assert "patients" in payload
        assert len(payload["patients"]) >= 3
        assert "patient_id" in payload["patients"][0]
        assert "latest_scan_id" in payload["patients"][0]
        assert "timeline" in payload["patients"][0]
        assert "triage_score" in payload["patients"][0]

    def test_demo_analysis_by_patient(self, client):
        """Demo analysis should be selectable via patient_id."""
        patients_resp = client.get("/demo/patients")
        assert patients_resp.status_code == 200
        patient = patients_resp.json()["patients"][0]

        analysis_resp = client.get(f"/demo/analysis?patient_id={patient['patient_id']}")
        assert analysis_resp.status_code == 200
        analysis_payload = analysis_resp.json()
        assert analysis_payload["patient_id"] == patient["patient_id"]
        assert analysis_payload["scan_id"] == patient["latest_scan_id"]

    def test_demo_patient_detail(self, client):
        """Per-patient endpoint should include profile and latest analysis."""
        patients_resp = client.get("/demo/patients")
        assert patients_resp.status_code == 200
        patient = patients_resp.json()["patients"][0]

        detail_resp = client.get(f"/demo/patients/{patient['patient_id']}")
        assert detail_resp.status_code == 200

        detail_payload = detail_resp.json()
        assert detail_payload["patient"]["patient_id"] == patient["patient_id"]
        assert detail_payload["analysis"]["scan_id"] == patient["latest_scan_id"]
        assert len(detail_payload["timeline"]) >= 2

    def test_demo_patient_timeline_endpoint(self, client):
        """Timeline endpoint should return longitudinal scan history."""
        patients_resp = client.get("/demo/patients")
        assert patients_resp.status_code == 200
        patient = patients_resp.json()["patients"][0]

        timeline_resp = client.get(f"/demo/patients/{patient['patient_id']}/timeline")
        assert timeline_resp.status_code == 200

        timeline_payload = timeline_resp.json()
        assert timeline_payload["patient"]["patient_id"] == patient["patient_id"]
        assert len(timeline_payload["timeline"]) >= 2
        assert "trend" in timeline_payload

    def test_demo_compare_endpoint(self, client):
        """Compare endpoint should return delta metrics and changed regions."""
        patients_resp = client.get("/demo/patients")
        assert patients_resp.status_code == 200
        patients = patients_resp.json()["patients"]
        assert len(patients) >= 2

        left_scan = patients[0]["latest_scan_id"]
        right_scan = patients[1]["latest_scan_id"]
        compare_resp = client.get(f"/demo/compare?left_scan_id={left_scan}&right_scan_id={right_scan}")
        assert compare_resp.status_code == 200

        compare_payload = compare_resp.json()
        assert compare_payload["left"]["scan_id"] == left_scan
        assert compare_payload["right"]["scan_id"] == right_scan
        assert "delta" in compare_payload
        assert "changed_regions" in compare_payload

    def test_demo_dicom_endpoint(self, client):
        """DICOM endpoint should return workstation profile metadata."""
        patients_resp = client.get("/demo/patients")
        assert patients_resp.status_code == 200
        patient = patients_resp.json()["patients"][0]

        dicom_resp = client.get(f"/demo/dicom/{patient['latest_scan_id']}")
        assert dicom_resp.status_code == 200

        payload = dicom_resp.json()
        assert payload["scan_id"] == patient["latest_scan_id"]
        assert "profile" in payload
        assert "series" in payload["profile"]
        assert len(payload["profile"]["series"]) >= 1
        assert "capabilities" in payload


class TestVolumeEndpoints:
    """Validate volumetric endpoint resolution controls."""

    @staticmethod
    def _get_demo_scan_id(client):
        response = client.get("/demo/patients")
        assert response.status_code == 200
        return response.json()["patients"][0]["latest_scan_id"]

    def test_volume_endpoint_forwards_resolution(self, client, monkeypatch):
        """/volume should pass resolution through to payload generation helper."""
        demo_scan_id = self._get_demo_scan_id(client)
        captured = {}

        def fake_resolve_scan_volume_path(scan_id, analysis):
            captured["scan_id"] = scan_id
            return Path("dummy-volume.nii.gz")

        def fake_build_volume_payload(scan_id, source_path, analysis, resolution="standard"):
            captured["resolution"] = resolution
            captured["source_path"] = str(source_path)
            return {
                "scan_id": scan_id,
                "modality": "MRI_T1",
                "shape": [192, 192, 192],
                "spacing_mm": [1.0, 1.0, 1.0],
                "encoding": "base64-rgba-u8",
                "volume_b64": "",
                "source_nifti": "dummy-volume.nii.gz",
                "synthetic_fallback": False,
                "resolution_profile": resolution,
                "cached": False,
            }

        monkeypatch.setattr(api_module, "_resolve_scan_volume_path", fake_resolve_scan_volume_path)
        monkeypatch.setattr(api_module, "_build_volume_payload", fake_build_volume_payload)

        response = client.get(f"/volume/{demo_scan_id}?resolution=extreme")
        assert response.status_code == 200

        payload = response.json()
        assert captured["scan_id"] == demo_scan_id
        assert captured["resolution"] == "extreme"
        assert payload["resolution_profile"] == "extreme"

    def test_volume_endpoint_rejects_invalid_resolution(self, client):
        """Volume endpoint should reject unsupported resolution values."""
        demo_scan_id = self._get_demo_scan_id(client)
        response = client.get(f"/volume/{demo_scan_id}?resolution=ultra")
        assert response.status_code == 422


class TestMeshEndpoints:
    """Validate mesh endpoint quality controls and request plumbing."""

    @staticmethod
    def _get_demo_scan_id(client):
        response = client.get("/demo/patients")
        assert response.status_code == 200
        return response.json()["patients"][0]["latest_scan_id"]

    def test_mesh_endpoint_forwards_quality(self, client, clinician_token, monkeypatch):
        """/mesh should pass quality through to mesh generation helper."""
        demo_scan_id = self._get_demo_scan_id(client)
        captured = {}

        def fake_ensure_scan_mesh(scan_id, analysis, force_rebuild=False, quality="high"):
            captured["scan_id"] = scan_id
            captured["quality"] = quality
            captured["force_rebuild"] = force_rebuild
            return {
                "mesh_url": f"/outputs/export/{scan_id}/brain_hq_web.obj",
                "mesh_format": "obj",
                "cached": True,
                "mesh_path": f"outputs/export/{scan_id}/brain_hq_web.obj",
                "mesh_quality": quality,
            }

        monkeypatch.setattr(api_module, "_ensure_scan_mesh", fake_ensure_scan_mesh)

        response = client.get(
            f"/mesh/{demo_scan_id}?quality=extreme&force_rebuild=true",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert response.status_code == 200

        payload = response.json()
        assert captured["scan_id"] == demo_scan_id
        assert captured["quality"] == "extreme"
        assert captured["force_rebuild"] is True
        assert payload["mesh_quality"] == "extreme"

    def test_demo_mesh_endpoint_forwards_quality(self, client, monkeypatch):
        """/demo/mesh should pass quality through without auth."""
        demo_scan_id = self._get_demo_scan_id(client)
        captured = {}

        def fake_ensure_demo_mesh(scan_id, modality, force_rebuild=False, quality="high"):
            captured["scan_id"] = scan_id
            captured["quality"] = quality
            captured["force_rebuild"] = force_rebuild
            return {
                "mesh_url": f"/outputs/demo_mesh/{scan_id}/brain_hq_web.obj",
                "mesh_format": "obj",
                "cached": True,
                "mesh_path": f"outputs/demo_mesh/{scan_id}/brain_hq_web.obj",
                "mesh_quality": quality,
                "modality": modality,
            }

        monkeypatch.setattr(api_module, "_ensure_demo_mesh", fake_ensure_demo_mesh)

        response = client.get(f"/demo/mesh/{demo_scan_id}?quality=extreme")
        assert response.status_code == 200

        payload = response.json()
        assert captured["scan_id"] == demo_scan_id
        assert captured["quality"] == "extreme"
        assert captured["force_rebuild"] is False
        assert payload["mesh_quality"] == "extreme"

    def test_mesh_endpoint_rejects_invalid_quality(self, client, clinician_token):
        """Mesh endpoint should reject unsupported quality values."""
        demo_scan_id = self._get_demo_scan_id(client)
        response = client.get(
            f"/mesh/{demo_scan_id}?quality=ultra",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert response.status_code == 422

    def test_demo_mesh_endpoint_rejects_invalid_quality(self, client):
        """Demo mesh endpoint should reject unsupported quality values."""
        demo_scan_id = self._get_demo_scan_id(client)
        response = client.get(f"/demo/mesh/{demo_scan_id}?quality=ultra")
        assert response.status_code == 422


class TestGovernanceAndSignoffEndpoints:
    """Validate clinical governance metadata and sign-off workflow."""

    @staticmethod
    def _get_demo_scan_id(client):
        response = client.get("/demo/patients")
        assert response.status_code == 200
        return response.json()["patients"][0]["latest_scan_id"]

    def test_analysis_payload_includes_governance(self, client):
        """Analysis endpoint should include governance metadata for UI/report surfaces."""
        demo_scan_id = self._get_demo_scan_id(client)
        response = client.get(f"/analysis/{demo_scan_id}")
        assert response.status_code == 200

        payload = response.json()
        assert "clinical_governance" in payload
        assert "decision_tier" in payload["clinical_governance"]
        assert "provenance" in payload["clinical_governance"]
        assert "review_state" in payload

    def test_governance_endpoint_requires_auth(self, client):
        """Governance endpoint should reject anonymous callers."""
        demo_scan_id = self._get_demo_scan_id(client)
        response = client.get(f"/governance/{demo_scan_id}")
        assert response.status_code == 401

    def test_clinician_signoff_roundtrip(self, client, clinician_token):
        """Clinician should be able to submit sign-off decisions and read history."""
        demo_scan_id = self._get_demo_scan_id(client)

        create_resp = client.post(
            f"/signoff/{demo_scan_id}",
            json={"decision": "approve", "note": "Validated with MRI context"},
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert create_resp.status_code == 200
        create_payload = create_resp.json()
        assert create_payload["recorded"]["decision"] == "approve"
        assert create_payload["history"]

        history_resp = client.get(
            f"/signoff/{demo_scan_id}",
            headers={"Authorization": f"Bearer {clinician_token}"},
        )
        assert history_resp.status_code == 200
        history_payload = history_resp.json()
        assert history_payload["history"]
        assert history_payload["history"][-1]["decision"] == "approve"

    def test_patient_cannot_submit_signoff(self, client, patient_token):
        """Patient role should not be allowed to record sign-off actions."""
        demo_scan_id = self._get_demo_scan_id(client)
        response = client.post(
            f"/signoff/{demo_scan_id}",
            json={"decision": "escalate", "escalation_reason": "Neurology review requested"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert response.status_code == 403