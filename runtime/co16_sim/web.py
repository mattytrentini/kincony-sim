# SPDX-License-Identifier: MIT
"""Simulation environment routes; device controls remain in the original UI."""

import json

from microdot import Response, redirect


def _json(body, status=200):
    return Response(body, status, {"Cache-Control": "no-store"})


def _error(code, message, status):
    return _json({"error": {"code": code, "message": message}}, status)


def _payload(request):
    media = (request.content_type or "").split(";", 1)[0].strip().lower()
    if media != "application/json":
        return None, _error(
            "unsupported_media_type", "Content-Type must be application/json.", 415
        )
    try:
        payload = json.loads(request.body.decode())
    except (ValueError, UnicodeError):
        return None, _error("invalid_request", "Malformed JSON body.", 400)
    if not isinstance(payload, dict):
        return None, _error("invalid_request", "JSON body must be an object.", 400)
    return payload, None


def install(app, state):
    """Attach local routes without changing application-wide error handlers."""
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
        return _json(state.snapshot())

    async def update(request, operation, device=None):
        payload, error = _payload(request)
        if error is not None:
            return error
        try:
            if device is None:
                operation(payload)
            else:
                operation(device, payload)
        except KeyError:
            return _error("not_found", "Simulation device not found.", 404)
        except ValueError as error:
            return _error("invalid_request", str(error), 400)
        return _json(state.snapshot())

    @app.post("/sim/api/inputs")
    async def inputs(request):
        return await update(request, state.update_inputs)

    @app.post("/sim/api/rtc")
    async def rtc(request):
        return await update(request, state.update_rtc)

    @app.post("/sim/api/devices/<device>")
    async def device(request, device):
        return await update(request, state.update_device, device)

    @app.after_error_request
    async def simulation_errors(request, response):
        if request is not None and (
            request.path == "/sim/api" or request.path.startswith("/sim/api/")
        ):
            if response.status_code == 404:
                response = _error("not_found", "Simulation API route not found.", 404)
            elif response.status_code == 405:
                allow = response.headers.get("Allow", "")
                response = _error("method_not_allowed", "Allowed methods: " + allow + ".", 405)
                response.headers["Allow"] = allow
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
