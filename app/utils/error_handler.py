from .response import api_response


def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(e):
        return api_response(False, "Bad Request", None)

    @app.errorhandler(401)
    def unauthorized(e):
        return api_response(False, "Unauthorized", None)

    @app.errorhandler(404)
    def not_found(e):
        return api_response(False, "Not Found", None)

    @app.errorhandler(500)
    def server_error(e):
        return api_response(False, "Server Error", None)


