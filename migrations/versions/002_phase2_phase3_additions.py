"""Phase 2/3 schema additions — prognosis, longitudinal, connectivity, annotations versions

Revision: 002
Revises: 001
Create Date: 2025-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Prognosis results table ---
    op.create_table(
        'prognosis_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('etiology', sa.Text(), nullable=True),
        sa.Column('overall_prognosis', sa.Text(), nullable=True,
                   comment='favorable, guarded, or poor'),
        sa.Column('recovery_trajectory', sa.Text(), nullable=True),
        sa.Column('milestones', sa.JSON(), nullable=True,
                   comment='List of milestone dicts with timeframe, description, probability range'),
        sa.Column('functional_outcomes', sa.JSON(), nullable=True,
                   comment='mRS estimates at discharge, 3mo, 6mo, 12mo'),
        sa.Column('risk_factors', sa.JSON(), nullable=True),
        sa.Column('protective_factors', sa.JSON(), nullable=True),
        sa.Column('disclaimer', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_prognosis_scan_id', 'prognosis_results', ['scan_id'])

    # --- Longitudinal comparisons table ---
    op.create_table(
        'longitudinal_comparisons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scan_id_before', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scan_id_after', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('overall_trend', sa.Text(), nullable=True,
                   comment='worsening, improving, stable, mixed'),
        sa.Column('region_deltas', sa.JSON(), nullable=True),
        sa.Column('atrophy_rate_global', sa.Float(), nullable=True),
        sa.Column('new_regions_affected', sa.JSON(), nullable=True),
        sa.Column('resolved_regions', sa.JSON(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('months_between', sa.Float(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_longitudinal_patient_id', 'longitudinal_comparisons', ['patient_id'])
    op.create_index('ix_longitudinal_before', 'longitudinal_comparisons', ['scan_id_before'])
    op.create_index('ix_longitudinal_after', 'longitudinal_comparisons', ['scan_id_after'])

    # --- Connectivity results table ---
    op.create_table(
        'connectivity_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('connectivity_type', sa.Text(), nullable=False,
                   comment='structural or functional'),
        sa.Column('method', sa.Text(), nullable=True,
                   comment='mrtrix3, nilearn, or atlas_estimation'),
        sa.Column('results', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_connectivity_scan_id', 'connectivity_results', ['scan_id'])
    op.create_index('ix_connectivity_type', 'connectivity_results', ['connectivity_type'])

    # --- Differential diagnosis table ---
    op.create_table(
        'differential_diagnoses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('etiology', sa.Text(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('probability', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('matching_regions', sa.JSON(), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_diff_diag_scan_id', 'differential_diagnoses', ['scan_id'])
    op.create_index('ix_diff_diag_rank', 'differential_diagnoses', ['rank'])

    # --- Treatment planning table ---
    op.create_table(
        'treatment_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('overall_viability', sa.Text(), nullable=True,
                   comment='contraindicated, high_risk, caution, feasible, no_damage'),
        sa.Column('no_go_zones', sa.JSON(), nullable=True),
        sa.Column('surgical_corridors', sa.JSON(), nullable=True),
        sa.Column('eloquent_assessments', sa.JSON(), nullable=True),
        sa.Column('warnings', sa.JSON(), nullable=True),
        sa.Column('recommendations', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_treatment_plan_scan_id', 'treatment_plans', ['scan_id'])

    # --- Annotation versions (optimistic locking) ---
    op.add_column('annotations', sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('annotations', sa.Column('is_latest', sa.Boolean(), nullable=True, server_default='true'))
    op.create_index('ix_annotations_parent_id', 'annotations', ['parent_id'])
    op.create_index('ix_annotations_is_latest', 'annotations', ['is_latest'])

    # --- Institution configurations ---
    op.create_table(
        'institutions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('data_residency_region', sa.Text(), nullable=False, server_default='us-east-1'),
        sa.Column('gdpr_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('retention_days', sa.Integer(), nullable=False, server_default='365'),
        sa.Column('allowed_modalities', sa.JSON(), nullable=True),
        sa.Column('max_concurrent_jobs', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('s3_bucket', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                   server_default=sa.text('now()'), nullable=False),
    )

    # Add institution FK to users
    op.add_column('users', sa.Column('institution_id', postgresql.UUID(as_uuid=True),
                                      sa.ForeignKey('institutions.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'institution_id')
    op.drop_table('institutions')
    op.drop_index('ix_annotations_is_latest')
    op.drop_index('ix_annotations_parent_id')
    op.drop_column('annotations', 'is_latest')
    op.drop_column('annotations', 'parent_id')
    op.drop_table('treatment_plans')
    op.drop_table('differential_diagnoses')
    op.drop_table('connectivity_results')
    op.drop_table('longitudinal_comparisons')
    op.drop_table('prognosis_results')