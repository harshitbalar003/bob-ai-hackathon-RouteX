"""add_predictions_table

ML-layer predictions table.  These rows are NEVER read by the deterministic
engines and NEVER influence a Decision, severity, citation, or disposition.

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2025-07-14 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the predictions table."""
    op.create_table(
        'predictions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('model_id', sa.String(), nullable=False),
        sa.Column('model_version', sa.String(), nullable=False),
        sa.Column('subject_type', sa.String(), nullable=False),
        sa.Column('subject_id', sa.String(), nullable=False),
        sa.Column('predicted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('horizon_hours', sa.Float(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('baseline_value', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_predictions_model_id', 'predictions', ['model_id'])
    op.create_index('ix_predictions_subject_type', 'predictions', ['subject_type'])
    op.create_index('ix_predictions_subject_id', 'predictions', ['subject_id'])
    op.create_index('ix_predictions_predicted_at', 'predictions', ['predicted_at'])
    op.create_index(
        'ix_predictions_subject_ts',
        'predictions',
        ['subject_type', 'subject_id', 'predicted_at'],
    )


def downgrade() -> None:
    """Drop the predictions table."""
    op.drop_index('ix_predictions_subject_ts', table_name='predictions')
    op.drop_index('ix_predictions_predicted_at', table_name='predictions')
    op.drop_index('ix_predictions_subject_id', table_name='predictions')
    op.drop_index('ix_predictions_subject_type', table_name='predictions')
    op.drop_index('ix_predictions_model_id', table_name='predictions')
    op.drop_table('predictions')
