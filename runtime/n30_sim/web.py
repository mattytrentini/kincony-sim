# SPDX-License-Identifier: MIT
"""Simulation-only controls attached to the real N30 application's HTTP server.

The supplied state owns validation and shared controllers. Reads never poll a
meter or apply an input; writes are explicit, atomic state operations.
"""

import json

from microdot import Response, redirect


def _json_response(body, status=200):
    return Response(body, status, {"Cache-Control": "no-store"})


def _error(code, message, status):
    return _json_response({"error": {"code": code, "message": message}}, status)


def _payload(request):
    content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return None, _error(
            "unsupported_media_type", "Content-Type must be application/json.", 415
        )
    try:
        value = json.loads(request.body.decode())
    except (ValueError, UnicodeError):
        return None, _error("invalid_request", "Malformed JSON body.", 400)
    if not isinstance(value, dict):
        return None, _error("invalid_request", "JSON body must be an object.", 400)
    return value, None


def install(app, state):
    """Add /sim/ routes without replacing the application's error handlers."""
    separator = __file__.rfind("/")
    static_dir = __file__[:separator + 1] + "static/" if separator >= 0 else "static/"

    @app.get("/sim")
    async def index_redirect(request):
        return redirect("/sim/")

    @app.get("/sim/")
    async def index(request):
        return Response.send_file(
            static_dir + "index.html", content_type="text/html; charset=UTF-8"
        )

    @app.get("/sim/static/app.css")
    async def stylesheet(request):
        return Response.send_file(
            static_dir + "app.css", content_type="text/css; charset=UTF-8"
        )

    @app.get("/sim/static/app.js")
    async def script(request):
        return Response.send_file(
            static_dir + "app.js", content_type="application/javascript; charset=UTF-8"
        )

    @app.get("/sim/api/state")
    async def snapshot(request):
        return _json_response(state.snapshot())

    @app.post("/sim/api/inputs/<int:pin>")
    async def inject_input(request, pin):
        payload, error = _payload(request)
        if error is not None:
            return error
        if len(payload) != 1 or "level" not in payload:
            return _error("invalid_request", "Use exactly {level: null, 0 or 1}.", 400)
        level = payload["level"]
        if level is not None and (type(level) is not int or level not in (0, 1)):
            return _error("invalid_request", "Level must be null, 0 or 1 (not boolean).", 400)
        try:
            state.inject_pin(pin, level)
        except KeyError:
            return _error("not_found", "GPIO pin not found.", 404)
        except ValueError as error:
            return _error("invalid_request", str(error), 400)
        except RuntimeError as error:
            return _error("output_conflict", str(error), 409)
        return _json_response(state.snapshot())

    @app.post("/sim/api/banks/<int:bank>")
    async def update_bank(request, bank):
        payload, error = _payload(request)
        if error is not None:
            return error
        try:
            state.update_bank(bank, payload)
        except KeyError:
            return _error("not_found", "Meter bank not found.", 404)
        except ValueError as error:
            return _error("invalid_request", str(error), 400)
        return _json_response(state.snapshot())

    return app
