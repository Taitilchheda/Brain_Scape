# Graph Report - .  (2026-04-12)

## Corpus Check
- 84 files · ~86,014 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1609 nodes · 4332 edges · 102 communities detected
- Extraction: 51% EXTRACTED · 49% INFERRED · 0% AMBIGUOUS · INFERRED: 2127 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `RAGEngine` - 124 edges
2. `PrognosisGenerator` - 122 edges
3. `InstitutionalDashboard` - 122 edges
4. `PlanningOverlay` - 121 edges
5. `DifferentialDiagnoser` - 119 edges
6. `TemporalComparator` - 119 edges
7. `FunctionalConnectivity` - 118 edges
8. `StructuralConnectivity` - 118 edges
9. `AuditLogger` - 102 edges
10. `RBACManager` - 91 edges

## Surprising Connections (you probably didn't know these)
- `Brain_Scape — Consent Manager  Tracks patient consent decisions. Certain feature` --uses--> `AuditLogger`  [INFERRED]
  compliance\consent_manager.py → compliance\audit_logger.py
- `Manages patient consent for data processing features.      Enforces that certain` --uses--> `AuditLogger`  [INFERRED]
  compliance\consent_manager.py → compliance\audit_logger.py
- `Grant consent for a feature.          Args:             patient_id: UUID of the` --uses--> `AuditLogger`  [INFERRED]
  compliance\consent_manager.py → compliance\audit_logger.py
- `Revoke consent for a feature.` --uses--> `AuditLogger`  [INFERRED]
  compliance\consent_manager.py → compliance\audit_logger.py
- `Check if consent has been granted for a feature.          Args:             pati` --uses--> `AuditLogger`  [INFERRED]
  compliance\consent_manager.py → compliance\audit_logger.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (151): AtlasRegistrar, Brain_Scape — Atlas Registrar  The most critical and most expensive preprocessin, Run ANTs SyN non-linear registration.          ANTs SyN produces the most accura, Run ANTs via command line (fallback if ANTsPy not installed)., Run FSL FNIRT for affine + non-linear registration.          Faster than ANTs Sy, Try the fallback registration method., Registers brain scans to MNI152 standard space.      Uses ANTs SyN as the primar, Args:             method: "ants_syn" or "fsl_fnirt".             template_path: (+143 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (150): AnnotateRequest, ConnectivityRequest, DifferentialDiagnosisRequest, get_job_status(), JobStatus, LongitudinalRequest, PrognosisRequest, QueryRequest (+142 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (170): animate(), applyClipDepthFromSlider(), applyDamageColors(), applyDicomContextPreset(), applyDicomPreset(), applyPanelMode(), askQuestion(), authHeaders() (+162 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (76): PHIScrubber, Brain_Scape — PHI Anonymizer  CRITICAL: This module performs synchronous, blocki, Scrub PHI from DICOM metadata tags.          Args:             file_path: Path t, Scrub PHI from an entire DICOM series directory.          Args:             inpu, Remove EXIF metadata (including GPS) from image files.          Args:, Generate a deterministic hash-based replacement token., Generate an age range bucket (e.g., '55-60 years')., Synchronous PHI scrubber using Microsoft Presidio.      PHI stripping is the fir (+68 more)

### Community 4 - "Community 4"
Cohesion: 0.03
Nodes (73): PromptTemplates, Backward-compatible class wrapper around module-level templates., _compute_answer_confidence(), _extract_citations(), Brain_Scape — Q&A Engine  Scan-aware conversational query system. The user can a, Build the full context string for the LLM prompt., Call the LLM API with the prompt., Generate a basic answer without LLM (template-based). (+65 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (58): client(), clinician_token(), _get_demo_scan_id(), patient_token(), Brain_Scape — API Integration Tests  Tests for FastAPI endpoints, JWT auth, RBAC, Test the report endpoint., Patient should not access clinician-mode reports., Report endpoint should return download info for clinicians. (+50 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (48): ConsentManager, Brain_Scape — Consent Manager  Tracks patient consent decisions. Certain feature, Revoke consent for a feature., Check if consent has been granted for a feature.          Args:             pati, Raise an error if consent has not been granted.          Call this at the start, Save a consent record., Manages patient consent for data processing features.      Enforces that certain, Get the most recent consent record for a patient/feature. (+40 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (66): _analysis_json_path(), annotation_websocket(), _build_damage_volume(), _build_demo_damage(), _build_demo_dicom_profile(), _build_synthetic_volume_channels(), _build_trend_overrides(), _build_uploaded_analysis_payload() (+58 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (1): AnnotationLayer

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (15): _default_profile(), Milestone, PrognosisResult, Brain_Scape — Prognosis Timeline Generator  Probabilistic recovery trajectory ba, A recovery milestone with probability range., Generate a prognosis timeline.          Args:             analysis: Analysis JSO, Infer most likely etiology from damage pattern., Complete prognosis timeline result. (+7 more)

### Community 10 - "Community 10"
Cohesion: 0.1
Nodes (14): annotation_websocket_endpoint(), AnnotationSession, Brain_Scape — WebSocket Annotation Server  Real-time collaborative annotation sy, Process an incoming WebSocket message., Handle annotation creation., Handle annotation update with optimistic locking., Handle annotation deletion., Broadcast a message to all connected users in a session. (+6 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (15): FHIRDiagnosticReport, FHIRPatient, _get_dicom_tag(), PACSConnector, Brain_Scape — PACS / HL7 FHIR Integration  DICOM WADO-RS for PACS connectivity a, Retrieve DICOM series from PACS.          Args:             study_instance_uid:, Send Brain_Scape analysis as DICOM Structured Report to PACS.          Args:, Create a DICOM Structured Report from analysis data. (+7 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (21): clinician_report_prompt(), connectivity_prompt(), differential_diagnosis_prompt(), get_template(), patient_report_prompt(), prognosis_prompt(), qa_prompt(), rag_retrieval_prompt() (+13 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (12): _compute_face_colors(), Brain_Scape — Damage Overlay  Projects the analysis engine's damage severity map, Map each vertex to a severity level and color., Load vertices and faces from OBJ file., Write OBJ file with vertex colors (extension: vertex color as comment)., Build the damage map JSON for the frontend., Apply damage color overlay to the mesh.          Args:             mesh_path: Pa, setOverlayOpacity() (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.11
Nodes (13): EloquentRegionAssessment, _partial_match(), Brain_Scape — Treatment Planning Overlay  Maps damage regions against eloquent c, Assessment of damage proximity to an eloquent region., Complete treatment planning overlay result., Analyze damage proximity to eloquent cortex and generate treatment planning over, Assess how close damage is to an eloquent area., Check if any damaged region is adjacent to an eloquent area. (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (7): _deep_merge(), _derive_metrics(), _derive_review_state(), _infer_source_kind(), Brain_Scape - Clinical Governance Engine  Computes configurable clinical gover, _safe_float(), _status_from_score()

### Community 16 - "Community 16"
Cohesion: 0.15
Nodes (12): _check_bilaterality(), _check_edema_pattern(), _check_mass_effect(), DiagnosisCandidate, _partial_match(), Brain_Scape — Differential Diagnosis Engine  CNN encoder (ResNet-50 backbone) +, A single etiology candidate with evidence., Generate a ranked differential diagnosis.          Args:             damage_summ (+4 more)

### Community 17 - "Community 17"
Cohesion: 0.12
Nodes (9): ModelRegistry, Brain_Scape — Model Registry  Manages model version promotion with automated qua, Promote a model to staging (automated gate check).          Returns:, Promote a model to production (requires human sign-off + ml_admin JWT)., Model version registry with promotion gates.      Promotion policy:         Dice, List all registered models, optionally filtered by name., Get the current production model for a given name., Register a new model version.          Args:             model_name: Name of the (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.17
Nodes (11): _common_shape(), FusionResult, Brain_Scape — Multimodal Fusion Engine  Weighted late fusion of EEG + fMRI + DTI, Weighted average fusion of voxel-level damage maps., Maximum fusion: take maximum severity at each voxel., Bayesian fusion: combine probabilities using Bayesian updating., Fuse per-region scores from multiple modalities., Combined multimodal damage assessment. (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.15
Nodes (10): _largest_component(), _normalize_vertices(), Brain_Scape — Mesh Builder  Converts 3D voxel volumes into surface meshes using, Apply quadric decimation to reduce polygon count., Fallback mesh building using scikit-image., Prepare a stable brain surface scalar field from MRI or fMRI NIfTI inputs., Build 3D meshes from a brain volume.          Args:             input_path: Path, Build mesh using VTK (preferred — higher quality). (+2 more)

### Community 20 - "Community 20"
Cohesion: 0.17
Nodes (9): _estimate_shift(), MotionCorrector, Brain_Scape — Motion Corrector  Corrects for patient head movement during fMRI a, Simple motion correction fallback using rigid registration.          Uses nibabe, Get the reference volume index., Corrects head motion in fMRI time-series data.      Uses FSL MCFLIRT to align al, Args:             reference_volume: Which volume to align to.                 "m, Apply motion correction to an fMRI scan.          Args:             input_path: (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (9): LongitudinalResult, Brain_Scape — Longitudinal Temporal Comparator  Compare multiple scans of the sa, Change in a single atlas region between two timepoints., Compare multiple timepoints sequentially.          Produces pairwise comparisons, Index damage summary by anatomical name., Generate a plain-text summary of the longitudinal comparison., Complete longitudinal comparison result., Compare two analysis results from different timepoints.          Args: (+1 more)

### Community 22 - "Community 22"
Cohesion: 0.15
Nodes (9): _count_by_field(), DashboardStats, _generate_compliance_recommendations(), Brain_Scape — Institutional Dashboard Configuration  Aggregate stats, audit tool, Generate aggregate statistics for an institution.          Args:             ins, Populate statistics from audit log., Populate statistics from job store., Generate a compliance audit report for an institution.          Args: (+1 more)

### Community 23 - "Community 23"
Cohesion: 0.19
Nodes (9): FunctionalConnectivityResult, NetworkResult, _partial_match(), Brain_Scape — Functional Connectivity Analysis  nilearn-based resting-state fMRI, Complete functional connectivity analysis., Analyze functional connectivity and network disruption.          Args:, Atlas-based estimation of network disruption.          Maps damaged atlas region, nilearn-based functional connectivity analysis.          Steps:         1. Load (+1 more)

### Community 24 - "Community 24"
Cohesion: 0.19
Nodes (8): _interpolate_timeseries(), Brain_Scape — Slice Timer  Corrects for the temporal offset between slice acquis, Compute acquisition time for each slice., Get the reference time point to align all slices to., Corrects slice timing in fMRI data.      fMRI volumes are acquired slice by slic, Args:             repetition_time: TR in seconds.             slice_order: "sequ, Apply slice timing correction to fMRI data.          Args:             input_pat, SliceTimer

### Community 25 - "Community 25"
Cohesion: 0.2
Nodes (8): Brain_Scape — Structural Connectivity Analysis  MRtrix3-based white matter fiber, Complete structural connectivity analysis., Analyze which white matter tracts are affected by damage.          Args:, Atlas-based estimation of tract involvement.          Maps damaged atlas regions, MRtrix3-based tractography analysis.          Steps:         1. Generate tractog, Result for a single white matter tract., StructuralConnectivityResult, TractResult

### Community 26 - "Community 26"
Cohesion: 0.26
Nodes (9): animate(), findRegionForFace(), init(), loadBrainMesh(), onCanvasClick(), pollJobStatus(), showRegionInfo(), updateStatus() (+1 more)

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (6): PHIScrubber, Brain_Scape — PHI Scrubber (Compliance Layer)  Re-usable PHI scrubbing using Mic, Re-usable PHI scrubber for compliance at any pipeline stage., Singleton pattern — one analyzer engine shared across the pipeline., Scrub PHI from any text string., Check if text contains PHI without scrubbing it.

### Community 28 - "Community 28"
Cohesion: 0.22
Nodes (5): Log PHI access (always both allowed and denied)., Write audit event to a daily log file (development mode)., Write audit event to Postgres (production mode)., Log an audit event.          Args:             user_id: UUID of the user perform, Convenience method for access events.

### Community 29 - "Community 29"
Cohesion: 0.2
Nodes (5): Transcribe audio from raw bytes.          Args:             audio_bytes: Raw aud, Full voice query pipeline: audio -> text -> Q&A -> response.          Args:, Voice query from raw audio bytes.          Same as voice_query but accepts bytes, Lazy-load Whisper model on first use., Transcribe an audio file to text.          Args:             audio_path: Path to

### Community 30 - "Community 30"
Cohesion: 0.38
Nodes (5): _histogram_matching(), _minmax_normalize(), Brain_Scape — Intensity Normalizer  Standardizes voxel intensity ranges across d, Normalize voxel intensities in a brain scan.          Args:             input_pa, _zscore_normalize()

### Community 31 - "Community 31"
Cohesion: 0.33
Nodes (5): Brain_Scape — Alembic Migration Environment  Configuration for running database, Run migrations in 'offline' mode.      Configures the context with just a URL an, Run migrations in 'online' mode.      Creates an Engine and associates a connect, run_migrations_offline(), run_migrations_online()

### Community 32 - "Community 32"
Cohesion: 0.4
Nodes (3): _endpoint_matches(), Brain_Scape — RBAC (Role-Based Access Control)  JWT-based authentication with ro, Check if a role has permission to access an endpoint.          Args:

### Community 33 - "Community 33"
Cohesion: 0.5
Nodes (4): download_openneuro_dataset(), main(), Brain_Scape — Seed OpenNeuro Sample Datasets  Downloads sample neuroimaging data, Download a single OpenNeuro dataset using openneuro-py.

### Community 34 - "Community 34"
Cohesion: 0.5
Nodes (1): Initial schema — users, scans, jobs, annotations  Revision: 001 Revises: None Cr

### Community 35 - "Community 35"
Cohesion: 0.5
Nodes (1): Phase 2/3 schema additions — prognosis, longitudinal, connectivity, annotations

### Community 36 - "Community 36"
Cohesion: 0.5
Nodes (2): Register a new institutional tenant., Save institutional config to disk.

### Community 37 - "Community 37"
Cohesion: 0.67
Nodes (1): Load the CNN+Transformer model if available.

### Community 38 - "Community 38"
Cohesion: 0.67
Nodes (1): Find MRtrix3 installation.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (2): HomePage(), loadLegacyFile()

### Community 40 - "Community 40"
Cohesion: 0.67
Nodes (1): Brain_Scape — Voice Query Interface  Whisper ASR for audio transcription -> QA e

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Brain_Scape — Brain Reconstruction and Analysis Intelligence Network for Scan-ba

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Convert diagnosis candidates to serializable dicts.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Convert result to serializable dict.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Convert result to serializable dict.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Convert fusion result to serializable dict.

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Generate a delta map for visualization.          Returns per-region color-coded

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Convert result to serializable dict.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Convert result to serializable dict.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Brain_Scape — Audit Logger  Append-only audit log for every API call, role check

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Args:             storage: "postgres" (production) or "file" (development).

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Query audit logs (read-only — no modification).          Args:             user_

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Create a JWT access token with role claims.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Create a JWT refresh token.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Validate a JWT token and return the decoded payload.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Convert result to serializable dict.

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Check if data can be stored in the target region per GDPR rules.          Args:

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Generate Grafana dashboard configuration for an institution.          Returns a

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Convert FHIRDiagnosticReport to FHIR R4 JSON.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Submit a FHIR resource to a FHIR server.

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Convert FHIRPatient to FHIR R4 JSON.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Get information about an annotation session.

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Args:             decimation_target: Target polygon count for web mesh.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Compute a scan quality score from SNR and registration accuracy.          Args:

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Get the hex color for a severity level.

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Get the label for a severity level.

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Get the semantic description for a severity level.

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Check if key words from b appear in a.

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Check if damage is bilateral (affects both left and right hemispheres).

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Heuristic: mass effect if one region has very high volume_pct and midline struct

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Heuristic: edema pattern if there's a RED core surrounded by ORANGE/YELLOW.

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Check if key words from b appear in a.

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Convert numeric severity level to label.

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Find the smallest common shape for alignment.

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Crop or pad array to target shape.

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Generate a new encryption key (store securely).

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Check if an actual endpoint matches a permission pattern.

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (0): 

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (0): 

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Default recovery profile for unknown etiologies.

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Split text into overlapping chunks for embedding.

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Return instructions for client-side TTS using browser speechSynthesis.

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Fallback: log to local file.

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Count events grouped by a field.

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Generate compliance recommendations based on audit data.

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): Extract a value from DICOM JSON by tag.

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): Estimate percentage of noise removed.

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (1): Z-score normalization: (x - mean) / std for brain voxels only.

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): Min-max normalization: scale to [0, 1] for brain voxels only.

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): Match intensity distribution to a reference scan.          Uses histogram specif

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): Estimate translational shift between two volumes using         phase correlation

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (1): Compute Otsu's threshold for brain/non-brain separation.

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (1): Apply morphological operations to clean up the brain mask.

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (1): Compute skull stripping statistics from the output image.

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (1): Compute statistics from data and mask.

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (1): Interpolate a voxel time series to correct for slice timing offset.          Use

### Community 98 - "Community 98"
Cohesion: 1.0
Nodes (1): Compute face color from its vertices (majority vote).

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (1): Map continuous severity score to 5-level scale.

### Community 100 - "Community 100"
Cohesion: 1.0
Nodes (1): Load vertices and faces from OBJ file.

### Community 101 - "Community 101"
Cohesion: 1.0
Nodes (1): Write a VTK mesh to file (auto-detect format from extension).

## Knowledge Gaps
- **394 isolated node(s):** `Brain_Scape — Brain Reconstruction and Analysis Intelligence Network for Scan-ba`, `Brain_Scape — Confidence Scorer  Every prediction in the system carries a confid`, `Computes confidence scores for damage classifications.      Three components fee`, `Args:             ensemble_size: Number of model variants in the ensemble.`, `Compute confidence scores for all classified regions.          Args:` (+389 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 41`** (2 nodes): `setup.py`, `Brain_Scape — Brain Reconstruction and Analysis Intelligence Network for Scan-ba`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (2 nodes): `.to_dict()`, `Convert diagnosis candidates to serializable dicts.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (2 nodes): `.to_dict()`, `Convert result to serializable dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (2 nodes): `Convert result to serializable dict.`, `.to_dict()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (2 nodes): `.to_dict()`, `Convert fusion result to serializable dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (2 nodes): `Generate a delta map for visualization.          Returns per-region color-coded`, `.generate_delta_map()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (2 nodes): `Convert result to serializable dict.`, `.to_dict()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (2 nodes): `.to_dict()`, `Convert result to serializable dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (2 nodes): `audit_logger.py`, `Brain_Scape — Audit Logger  Append-only audit log for every API call, role check`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (2 nodes): `.__init__()`, `Args:             storage: "postgres" (production) or "file" (development).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (2 nodes): `.query()`, `Query audit logs (read-only — no modification).          Args:             user_`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (2 nodes): `Create a JWT access token with role claims.`, `.create_access_token()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (2 nodes): `Create a JWT refresh token.`, `.create_refresh_token()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (2 nodes): `Validate a JWT token and return the decoded payload.`, `.validate_token()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (2 nodes): `layout.tsx`, `RootLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (2 nodes): `.to_dict()`, `Convert result to serializable dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (2 nodes): `.check_data_residency()`, `Check if data can be stored in the target region per GDPR rules.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (2 nodes): `.get_grafana_dashboard_config()`, `Generate Grafana dashboard configuration for an institution.          Returns a`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (2 nodes): `.fhir_report_to_dict()`, `Convert FHIRDiagnosticReport to FHIR R4 JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (2 nodes): `.submit_to_fhir_server()`, `Submit a FHIR resource to a FHIR server.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (2 nodes): `.fhir_patient_to_dict()`, `Convert FHIRPatient to FHIR R4 JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (2 nodes): `.get_session_info()`, `Get information about an annotation session.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `.__init__()`, `Args:             decimation_target: Target polygon count for web mesh.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (2 nodes): `record_dom_demo.js`, `run()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Compute a scan quality score from SNR and registration accuracy.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Get the hex color for a severity level.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `Get the label for a severity level.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Get the semantic description for a severity level.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Check if key words from b appear in a.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `Check if damage is bilateral (affects both left and right hemispheres).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Heuristic: mass effect if one region has very high volume_pct and midline struct`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Heuristic: edema pattern if there's a RED core surrounded by ORANGE/YELLOW.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Check if key words from b appear in a.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Convert numeric severity level to label.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Find the smallest common shape for alignment.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Crop or pad array to target shape.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `Generate a new encryption key (store securely).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Check if an actual endpoint matches a permission pattern.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `next-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `next.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `Default recovery profile for unknown etiologies.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Split text into overlapping chunks for embedding.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `Return instructions for client-side TTS using browser speechSynthesis.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `Fallback: log to local file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `Count events grouped by a field.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `Generate compliance recommendations based on audit data.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `Extract a value from DICOM JSON by tag.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `Estimate percentage of noise removed.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `Z-score normalization: (x - mean) / std for brain voxels only.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `Min-max normalization: scale to [0, 1] for brain voxels only.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `Match intensity distribution to a reference scan.          Uses histogram specif`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `Estimate translational shift between two volumes using         phase correlation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `Compute Otsu's threshold for brain/non-brain separation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `Apply morphological operations to clean up the brain mask.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `Compute skull stripping statistics from the output image.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (1 nodes): `Compute statistics from data and mask.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `Interpolate a voxel time series to correct for slice timing offset.          Use`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 98`** (1 nodes): `Compute face color from its vertices (majority vote).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `Map continuous severity score to 5-level scale.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 100`** (1 nodes): `Load vertices and faces from OBJ file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 101`** (1 nodes): `Write a VTK mesh to file (auto-detect format from extension).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RAGEngine` connect `Community 4` to `Community 0`, `Community 1`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Why does `MeshBuilder` connect `Community 1` to `Community 0`, `Community 19`, `Community 63`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Why does `AuditLogger` connect `Community 1` to `Community 6`, `Community 49`, `Community 50`, `Community 51`, `Community 28`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 116 inferred relationships involving `RAGEngine` (e.g. with `QAEngine` and `Brain_Scape — Q&A Engine  Scan-aware conversational query system. The user can a`) actually correct?**
  _`RAGEngine` has 116 INFERRED edges - model-reasoned connections that need verification._
- **Are the 109 inferred relationships involving `PrognosisGenerator` (e.g. with `JobStatus` and `QueryRequest`) actually correct?**
  _`PrognosisGenerator` has 109 INFERRED edges - model-reasoned connections that need verification._
- **Are the 110 inferred relationships involving `InstitutionalDashboard` (e.g. with `Brain_Scape — MLOps Dashboard Module` and `JobStatus`) actually correct?**
  _`InstitutionalDashboard` has 110 INFERRED edges - model-reasoned connections that need verification._
- **Are the 110 inferred relationships involving `PlanningOverlay` (e.g. with `Brain_Scape — MLOps Dashboard Module` and `JobStatus`) actually correct?**
  _`PlanningOverlay` has 110 INFERRED edges - model-reasoned connections that need verification._