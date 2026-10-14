import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from control_plane.models.access_control import AuthSession, DemoUser
from control_plane.models.task import utc_now
from control_plane.services.security_audit_service import SecurityAuditService


class AuthenticationError(RuntimeError):
    pass


class InactiveUserError(AuthenticationError):
    pass


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
    ).hex()
    return salt, digest


def verify_password(password: str, salt: str, expected: str) -> bool:
    _, actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, session: Session, session_ttl_seconds: int = 28_800):
        self.session = session
        self.session_ttl_seconds = session_ttl_seconds
        self.audit = SecurityAuditService(session)

    def login(self, username: str, password: str) -> tuple[DemoUser, str]:
        user = self.session.scalar(select(DemoUser).where(DemoUser.username == username.strip()))
        if user is None or not verify_password(password, user.password_salt, user.password_hash):
            self.audit.record(
                "LOGIN_FAILED",
                user,
                decision="DENIED",
                reason="invalid username or password",
            )
            raise AuthenticationError("用户名或密码错误")
        if not user.is_active:
            self.audit.record(
                "LOGIN_FAILED", user, decision="DENIED", reason="user is inactive"
            )
            raise InactiveUserError("账号已停用")

        token = secrets.token_urlsafe(48)
        now = utc_now()
        user.last_login_at = now
        auth_session = AuthSession(
            session_id=str(uuid.uuid4()),
            token_hash=token_digest(token),
            user_id=user.user_id,
            expires_at=now + timedelta(seconds=self.session_ttl_seconds),
        )
        self.session.add(auth_session)
        self.session.commit()
        self.audit.record("LOGIN_SUCCESS", user, decision="ALLOWED")
        return user, token

    def revoke_user_sessions(self, user_id: str) -> int:
        result = self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        self.session.commit()
        return int(result.rowcount or 0)

    def current_user(self, token: str | None) -> DemoUser | None:
        if not token:
            return None
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(token))
        )
        now = utc_now()
        if (
            auth_session is None
            or auth_session.revoked_at is not None
            or auth_session.expires_at <= now
        ):
            return None
        user = self.session.get(DemoUser, auth_session.user_id)
        if user is None or not user.is_active:
            return None
        auth_session.last_seen_at = now
        self.session.commit()
        return user

    def logout(self, token: str | None) -> DemoUser | None:
        if not token:
            return None
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(token))
        )
        if auth_session is None:
            return None
        user = self.session.get(DemoUser, auth_session.user_id)
        if auth_session.revoked_at is None:
            auth_session.revoked_at = utc_now()
            self.session.commit()
        self.audit.record("LOGOUT", user, decision="ALLOWED")
        return user
