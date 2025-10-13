def serialize_user(user) -> dict:
    return {
        "id": user.id,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "email": user.email,
        "organization": user.organization,
        "phone": user.phone,
        "client_id": user.client_id,
        "client_secret": user.client_secret,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


