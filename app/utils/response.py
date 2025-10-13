from flask import jsonify


def api_response(success: bool, message: str, data: dict | None = None):
    # Always return status 200 with unified envelope
    return jsonify({
        "success": success,
        "message": message,
        "data": data
    }), 200


