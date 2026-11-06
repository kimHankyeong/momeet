import hashlib
import hmac
import secrets
from datetime import datetime, timezone

import bcrypt

from app.config import get_settings


def utcnow() -> datetime:
    """DB에는 timezone 없는 UTC로 저장한다 (SQLite/MySQL 동일 동작)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def isoformat(dt: datetime | None) -> str | None:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


def hash_secret(plain: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds)).decode("ascii")


def verify_secret(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


# 존재하지 않는 약속방/대상에도 같은 비용을 쓰기 위한 더미 해시 (타이밍 차이 최소화)
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(4)).decode("ascii")


def burn_verify(plain: str) -> None:
    verify_secret(plain, _DUMMY_HASH)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    # 토큰은 엔트로피가 충분하므로 빠른 해시로 충분하다
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def digests_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def new_meeting_id() -> str:
    return secrets.token_urlsafe(6)


# 입장 코드: 소문자+숫자, 헷갈리는 문자(i, l, o, 0, 1) 제외 -> 31자, 8자리 = 약 8.5e11 가지
JOIN_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
JOIN_CODE_LENGTH = 8


def new_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def normalize_join_code(raw: str) -> str:
    """사용자가 입력한 코드를 정리한다: 공백/하이픈 제거, 소문자화, 'MOMEET-' 표시 접두사 허용."""
    code = raw.strip().lower().replace("-", "").replace(" ", "")
    # 'o'는 코드 문자에 없으므로 정상 코드가 'momeet'로 시작할 수 없다 -> 접두사로 안전하게 제거
    if code.startswith("momeet"):
        code = code[len("momeet"):]
    return code


def is_valid_join_code(code: str) -> bool:
    return len(code) == JOIN_CODE_LENGTH and all(c in JOIN_CODE_ALPHABET for c in code)
