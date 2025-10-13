from werkzeug.security import generate_password_hash
from ..extensions import db
from ..models.user import User


def create_user(**kwargs) -> User:
    user = User(**kwargs)
    db.session.add(user)
    db.session.commit()
    return user


