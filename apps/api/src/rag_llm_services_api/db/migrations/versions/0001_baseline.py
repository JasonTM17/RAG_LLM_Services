"""empty baseline: establishes the migration head; owner-scoped tables arrive in Phase 03

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-06

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Intentionally empty: the baseline only anchors the migration history.


def downgrade() -> None:
    """Downgrade schema."""
    # Intentionally empty: the baseline creates no schema to remove.
