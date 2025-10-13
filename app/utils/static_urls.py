import os
from flask import current_app, url_for


def build_static_url(path: str | None) -> str | None:
    if not path:
        return None

    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")

    # Normalize separators
    normalized = path.replace("\\", "/")

    # If path already under static/, strip prefix to get relative filename
    if normalized.startswith("static/"):
        normalized = normalized[len("static/"):]

    # If it's an absolute filesystem path, relativize to static folder
    try:
        if os.path.isabs(path) and current_app.static_folder:
            normalized = os.path.relpath(path, start=current_app.static_folder).replace("\\", "/")
    except Exception:
        pass

    return f"{base_url}{url_for('static', filename=normalized)}"


