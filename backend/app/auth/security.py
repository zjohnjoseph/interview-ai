import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings


def _to_bcrypt_input(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes of input; SHA-256 digest is always
    # 32 bytes, so any password length is handled without truncation.
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_to_bcrypt_input(plain), hashed.encode("utf-8"))


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload: dict[str, str | datetime] = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
