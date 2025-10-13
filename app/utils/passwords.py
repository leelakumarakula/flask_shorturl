from typing import Tuple
from werkzeug.security import check_password_hash, generate_password_hash


def verify_and_upgrade_password(stored_password: str, provided_password: str) -> Tuple[bool, str | None]:
    """Verify password against possibly legacy plaintext value.

    Returns (is_valid, new_hash_or_None). If the stored password was plaintext and
    the provided one matches, a new hash is returned for upgrade.
    """
    if not stored_password:
        return False, None

    # Try modern werkzeug hash first
    try:
        if check_password_hash(stored_password, provided_password):
            return True, None
    except ValueError:
        # Stored string is not a valid werkzeug hash
        pass

    # Fallback: treat stored as plaintext
    if stored_password == provided_password:
        return True, generate_password_hash(provided_password)

    return False, None


