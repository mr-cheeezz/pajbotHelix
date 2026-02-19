import pajbot.web.routes.api.banphrases
import pajbot.web.routes.api.commands
import pajbot.web.routes.api.common
import pajbot.web.routes.api.modules
import pajbot.web.routes.api.playsound
import pajbot.web.routes.api.social
import pajbot.web.routes.api.timers
import pajbot.web.routes.api.users

from flask import Blueprint, Response, current_app, jsonify


def _rule_to_openapi_path(rule: str) -> str:
    # Flask: /commands/<int:command_id> -> OpenAPI: /commands/{command_id}
    converted = rule.replace("<", "{").replace(">", "}")
    for converter in ("int:", "float:", "string:", "path:", "uuid:"):
        converted = converted.replace("{" + converter, "{")
    return converted


def _build_openapi_spec() -> dict:
    app = current_app

    paths: dict = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1"):
            continue

        # Don't document Flask internals.
        if rule.endpoint == "static":
            continue

        methods = sorted(m for m in rule.methods if m in {"GET", "POST", "PUT", "PATCH", "DELETE"})
        if not methods:
            continue

        openapi_path = _rule_to_openapi_path(rule.rule)
        if openapi_path not in paths:
            paths[openapi_path] = {}

        for method in methods:
            paths[openapi_path][method.lower()] = {
                "summary": f"{method} {openapi_path}",
                "operationId": rule.endpoint.replace(".", "_") + "_" + method.lower(),
                "responses": {
                    "200": {"description": "Success"},
                },
            }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "pajbot API",
            "version": "v1",
            "description": "Auto-generated documentation for pajbot API endpoints.",
        },
        "paths": paths,
    }


def init(app) -> None:
    # Initialize the v1 api
    # /api/v1
    bp = Blueprint("api", __name__, url_prefix="/api/v1")

    # Initialize any common settings and routes
    pajbot.web.routes.api.common.init(bp)

    # /users
    pajbot.web.routes.api.users.init(bp)

    # /commands
    pajbot.web.routes.api.commands.init(bp)

    # /social
    pajbot.web.routes.api.social.init(bp)

    # /timers
    pajbot.web.routes.api.timers.init(bp)

    # /banphrases
    pajbot.web.routes.api.banphrases.init(bp)

    # /modules
    pajbot.web.routes.api.modules.init(bp)

    # /playsound/:name
    # /playsound/:name/play
    pajbot.web.routes.api.playsound.init(bp)

    app.register_blueprint(bp)

    @app.route("/api")
    @app.route("/api/")
    @app.route("/api/swagger")
    def api_swagger() -> Response:
        html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>pajbot API docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    html, body { margin: 0; padding: 0; }
    #swagger-ui { max-width: 1200px; margin: 0 auto; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/api/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      displayRequestDuration: true,
      persistAuthorization: true
    });
  </script>
</body>
</html>"""
        return Response(html, mimetype="text/html")

    @app.route("/api/openapi.json")
    def api_openapi_json():
        return jsonify(_build_openapi_spec())
