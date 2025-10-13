from typing import Optional
from ..models.user import User


def get_user_by_email(email: str) -> Optional[User]:
    return User.query.filter_by(email=email).first()


def get_user_by_client_id(client_id: str) -> Optional[User]:
    return User.query.filter_by(client_id=client_id).first()


