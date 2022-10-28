"""Introduce role permissions [5994f9ad0489].

Revision ID: 5994f9ad0489
Revises: c1b18cec3a48
Create Date: 2022-10-25 23:52:25.935344

"""
import datetime
import uuid

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision = "5994f9ad0489"
down_revision = "c1b18cec3a48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    op.create_table('permissionschema',
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
    op.create_table('rolepermissionsschema',
    sa.Column('permission_name', sa.Integer(), nullable=False),
    sa.Column('role_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
    sa.ForeignKeyConstraint(['permission_name'], ['permissionschema.name'], ),
    sa.ForeignKeyConstraint(['role_id'], ['roleschema.id'], ),
    sa.PrimaryKeyConstraint('permission_name', 'role_id')
    )

    # get metadata from current connection
    meta = sa.MetaData(bind=op.get_bind())

    # pass in tuple with tables we want to reflect, otherwise whole database will get reflected
    meta.reflect(
        only=(
            "permissionschema",
            "roleschema",
            "rolepermissionsschema",
            "userroleassignmentschema",
            "userschema",
        )
    )

    read = "READ"
    write = "WRITE"
    me = "ME"

    # Prefill the table with two possible permissions
    op.bulk_insert(
        sa.Table("permissionschema", meta),
        [
            {"name": read},
            {"name": write},
            {"name": me},
        ],
    )

    admin_id = str(uuid.uuid4()).replace("-", "")
    guest_id = str(uuid.uuid4()).replace("-", "")

    # Prefill the roles table with an admin role
    op.bulk_insert(
        sa.Table(
            "roleschema",
            meta,
        ),
        [
            {
                "id": admin_id,
                "name": "admin",
                "created": datetime.datetime.now(),
                "updated": datetime.datetime.now(),
            },
            {
                "id": guest_id,
                "name": "guest",
                "created": datetime.datetime.now(),
                "updated": datetime.datetime.now(),
            },
        ],
    )

    # Give the admin read, write and me permissions,
    # give the guest read and me permissions
    op.bulk_insert(
        sa.Table(
            "rolepermissionsschema",
            meta,
        ),
        [
            {"role_id": admin_id, "permission_name": read},
            {"role_id": admin_id, "permission_name": write},
            {"role_id": admin_id, "permission_name": me},
            {"role_id": guest_id, "permission_name": read},
            {"role_id": guest_id, "permission_name": me},
        ],
    )

    # In order to not break permissions for existing users, all will be assigned
    # admin
    conn = op.get_bind()
    res = conn.execute(sa.text("""SELECT id FROM userschema"""))
    user_ids = res.fetchall()
    # user_table = sa.Table('userschema', meta)
    # user_ids = op.execute(user_table.select('id'))
    for user_id in user_ids:
        op.bulk_insert(
            sa.Table(
                "userroleassignmentschema",
                meta,
            ),
            [
                {
                    "id": str(uuid.uuid4()).replace("-", ""),
                    "role_id": admin_id,
                    "user_id": user_id[0],
                    "created": datetime.datetime.now(),
                    "updated": datetime.datetime.now(),
                }
            ],
        )


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("rolepermissionsschema")
    op.drop_table("permissionschema")
    # ### end Alembic commands ###
