"""Initial schema — users, scans, jobs, annotations

Revision: 001
Revises: None
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Users table ---
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.Text(), unique=True, nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False,
                   server_default='patient',
                   comment='One of: clinician, researcher, patient'),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
    )

    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_role', 'users', ['role'])

    # --- Scans table ---
    op.create_table(
        'scans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('original_filename', sa.Text(), nullable=True),
        sa.Column('original_format', sa.Text(), nullable=True,
                   comment='DICOM, NIFTI, NIFTI_GZ, EDF, BDF, JPEG, PNG, PDF'),
        sa.Column('modality', sa.Text(), nullable=True,
                   comment='MRI_T1, fMRI, EEG, DTI, etc.'),
        sa.Column('status', sa.Text(), nullable=False,
                   server_default='uploaded',
                   comment='uploaded, processing, complete, failed'),
        sa.Column('anonymized_path', sa.Text(), nullable=True,
                   comment='S3 path to anonymized NIfTI after PHI scrubbing'),
        sa.Column('original_path', sa.Text(), nullable=True,
                   comment='S3 path to encrypted original before anonymization'),
        sa.Column('scan_metadata', sa.JSON(), nullable=True,
                   comment='Extracted metadata: voxel size, dimensions, etc.'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
    )

    op.create_index('ix_scans_patient_id', 'scans', ['patient_id'])
    op.create_index('ix_scans_status', 'scans', ['status'])
    op.create_index('ix_scans_modality', 'scans', ['modality'])

    # --- Jobs table ---
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Text(), nullable=False,
                   server_default='queued',
                   comment='queued, preprocessing, reconstructing, analyzing, generating, complete, failed'),
        sa.Column('stage', sa.Text(), nullable=True,
                   comment='Current pipeline stage name'),
        sa.Column('progress_pct', sa.Integer(), nullable=True,
                   comment='0-100 progress percentage'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('pipeline_config', sa.JSON(), nullable=True,
                   comment='Pipeline configuration overrides for this job'),
        sa.Column('result_path', sa.Text(), nullable=True,
                   comment='S3 path to pipeline output artifacts'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
    )

    op.create_index('ix_jobs_scan_id', 'jobs', ['scan_id'])
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])
    op.create_index('ix_jobs_status', 'jobs', ['status'])
    op.create_index('ix_jobs_created_at', 'jobs', ['created_at'])

    # --- Annotations table ---
    op.create_table(
        'annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mesh_face_id', sa.Integer(), nullable=True,
                   comment='Index of the mesh face being annotated'),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('marker_type', sa.Text(), nullable=True,
                   comment='point, region, measurement, etc.'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )

    op.create_index('ix_annotations_scan_id', 'annotations', ['scan_id'])
    op.create_index('ix_annotations_user_id', 'annotations', ['user_id'])

    # --- Audit logs table (append-only) ---
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('action', sa.Text(), nullable=False,
                   comment='e.g., GET /report/scan-123, POST /ingest'),
        sa.Column('resource_id', sa.Text(), nullable=True),
        sa.Column('outcome', sa.Text(), nullable=False,
                   comment='ALLOWED or DENIED'),
        sa.Column('ip_address', sa.Text(), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
    )

    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])

    # --- Consent records table ---
    op.create_table(
        'consent_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('feature', sa.Text(), nullable=False,
                   comment='longitudinal_analysis, research_contribution, data_sharing'),
        sa.Column('status', sa.Text(), nullable=False,
                   comment='granted or revoked'),
        sa.Column('granted_by', sa.Text(), nullable=True),
        sa.Column('revoked_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
    )

    op.create_index('ix_consent_patient_feature', 'consent_records',
                     ['patient_id', 'feature'], unique=True)


def downgrade() -> None:
    op.drop_table('consent_records')
    op.drop_table('audit_logs')
    op.drop_table('annotations')
    op.drop_table('jobs')
    op.drop_table('scans')
    op.drop_table('users')