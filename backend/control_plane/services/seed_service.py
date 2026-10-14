import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from common.enums import GroupBy, OrganizationId, QueryType, UserRole
from control_plane.models.access_control import DatasetAsset, DemoUser
from control_plane.services.auth_service import hash_password


DEMO_USERS = {
    "analyst_demo": (UserRole.ANALYST, None),
    "owner_a": (UserRole.DATA_OWNER, OrganizationId.ORG_A),
    "owner_b": (UserRole.DATA_OWNER, OrganizationId.ORG_B),
    "owner_c": (UserRole.DATA_OWNER, OrganizationId.ORG_C),
    "auditor_demo": (UserRole.AUDITOR, None),
    "admin_demo": (UserRole.ADMIN, None),
}


def seed_catalog(session: Session) -> None:
    for party in OrganizationId:
        asset_id = f"ENERGY_{party.value}"
        if session.get(DatasetAsset, asset_id) is not None:
            continue
        session.add(
            DatasetAsset(
                asset_id=asset_id,
                name=f"{party.value} 园区智能电表聚合数据",
                description="园区家庭用电半小时粒度数据，仅支持受控隐私统计查询。",
                owner_party=party.value,
                time_start=datetime(2012, 11, 11),
                time_end=datetime(2012, 12, 11),
                source_granularity="30m",
                supported_query_types_json=json.dumps([item.value for item in QueryType]),
                supported_group_by_json=json.dumps([item.value for item in GroupBy]),
                privacy_protection="家庭级贡献裁剪、秘密共享与分布式差分隐私；不提供原始数据下载。",
                raw_download_allowed=False,
                status="ACTIVE",
            )
        )
    session.commit()


def seed_demo_users(session: Session, passwords: dict[str, str]) -> None:
    for username, (role, party) in DEMO_USERS.items():
        password = passwords.get(username, "")
        if not password:
            continue
        user = session.scalar(select(DemoUser).where(DemoUser.username == username))
        salt, password_hash = hash_password(password)
        if user is None:
            user = DemoUser(
                user_id=username,
                username=username,
                password_salt=salt,
                password_hash=password_hash,
                role=role.value,
                party_id=party.value if party else None,
                is_active=True,
            )
            session.add(user)
        else:
            user.role = role.value
            user.party_id = party.value if party else None
            user.password_salt = salt
            user.password_hash = password_hash
    session.commit()


def seed_access_control(
    factory: sessionmaker[Session], *, demo_seed_enabled: bool, passwords: dict[str, str]
) -> None:
    with factory() as session:
        seed_catalog(session)
        if demo_seed_enabled:
            seed_demo_users(session, passwords)
