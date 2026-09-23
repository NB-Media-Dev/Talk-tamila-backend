"""dedupe and constrain story_mutes / story_reports

Revision ID: 830134bbfc1c
Revises: af44bdacc830
Create Date: 2026-09-23 13:00:00.000000

This closes audit items #5 (StoryMute missing UniqueConstraint) and #14
(duplicate story reports not prevented). Any existing duplicate rows are
removed first (keeping the earliest row of each dup group) so the new
UNIQUE constraints don't fail to apply on data that predates them.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '830134bbfc1c'
down_revision: Union[str, None] = 'af44bdacc830'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the earliest row per (user_id, muted_user_id) / (story_id, user_id)
    # pair; delete the rest. Self-join delete works on MySQL 5.7+ as well as 8,
    # unlike a window-function approach.
    op.execute("""
        DELETE m1 FROM story_mutes m1
        INNER JOIN story_mutes m2
          ON m1.user_id = m2.user_id
         AND m1.muted_user_id = m2.muted_user_id
         AND m1.mute_id > m2.mute_id
    """)
    op.execute("""
        DELETE r1 FROM story_reports r1
        INNER JOIN story_reports r2
          ON r1.story_id = r2.story_id
         AND r1.user_id = r2.user_id
         AND r1.report_id > r2.report_id
    """)

    op.create_unique_constraint(
        "uq_story_mutes_user_muted", "story_mutes", ["user_id", "muted_user_id"]
    )
    op.create_unique_constraint(
        "uq_story_reports_story_user", "story_reports", ["story_id", "user_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_story_reports_story_user", "story_reports", type_="unique")
    op.drop_constraint("uq_story_mutes_user_muted", "story_mutes", type_="unique")