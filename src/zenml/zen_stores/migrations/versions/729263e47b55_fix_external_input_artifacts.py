"""fix external_input_artifacts [729263e47b55].

Revision ID: 729263e47b55
Revises: 0.45.2
Create Date: 2023-10-18 08:07:33.374613

"""
import json

from alembic import op
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = "729263e47b55"
down_revision = "0.45.2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    bind = op.get_bind()
    session = Session(bind=bind)
    rows = session.execute(
        text("SELECT id, step_configurations FROM pipeline_deployment")
    )
    for id_, data in rows:
        data_dict = json.loads(data)
        for k in data_dict:
            for eip_name in data_dict[k]["config"]["external_input_artifacts"]:
                data_dict[k]["config"]["external_input_artifacts"][
                    eip_name
                ] = {
                    "id": data_dict[k]["config"]["external_input_artifacts"][
                        eip_name
                    ]
                }
        data = json.dumps(data_dict)
        session.execute(
            text(
                f"UPDATE pipeline_deployment SET step_configurations='{data}' WHERE id='{id_}'"
            )
        )
    session.commit()
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    bind = op.get_bind()
    session = Session(bind=bind)
    rows = session.execute(
        text("SELECT id,step_configurations FROM pipeline_deployment")
    )
    for id_, data in rows:
        data_dict = json.loads(data)
        for k in data_dict:
            for eip_name in data_dict[k]["config"]["external_input_artifacts"]:
                data_dict[k]["config"]["external_input_artifacts"][
                    eip_name
                ] = data_dict[k]["config"]["external_input_artifacts"][
                    eip_name
                ][
                    "id"
                ]
        data = json.dumps(data_dict)
        session.execute(
            text(
                f"UPDATE pipeline_deployment SET step_configurations='{data}' WHERE id='{id_}'"
            )
        )
    session.commit()
    # ### end Alembic commands ###
