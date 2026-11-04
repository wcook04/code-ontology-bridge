"""WSGI adapter; requests never read files, run SQL or invoke a model."""
from __future__ import annotations

import hashlib
import re
from http import HTTPStatus
from urllib.parse import parse_qsl
from wsgiref.simple_server import WSGIServer, make_server

from .api import APIError, API_SCHEMA, PREFIX, Inspector, allowed
from .bundle import encode
from .contract import openapi_document


class Application:
    def __init__(self, bundle):
        self.inspector = Inspector(bundle)

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        headers = [("Content-Type", "application/json; charset=utf-8"),
                   ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "no-cache")]
        status = 200
        try:
            if method not in ("GET", "HEAD"):
                headers.append(("Allow", "GET, HEAD"))
                raise APIError(405, "only GET and HEAD are supported")
            query = environ.get("QUERY_STRING", "")
            if len(query) > 4096:
                raise APIError(400, "query string too long")
            if re.search(r"%(?![0-9a-fA-F]{2})", query):
                raise APIError(400, "malformed percent escape")
            pairs = parse_qsl(query, keep_blank_values=True, max_num_fields=30, errors="strict")
            params = dict(pairs)
            if len(params) != len(pairs):
                raise APIError(400, "duplicate query parameter")
            path = environ.get("PATH_INFO", "")
            if path == PREFIX + "/openapi.json":
                allowed(params, [])
                payload = openapi_document()
            else:
                payload = self.inspector.response(path, params)
        except (ValueError, UnicodeError):
            status, payload = 400, {"schema_version": API_SCHEMA, "error": {"message": "malformed query"}}
        except APIError as error:
            status, payload = error.status, {"schema_version": API_SCHEMA, "error": {"message": error.message}}
        body = encode(payload)
        if status == 200:
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            headers.append(("ETag", etag))
            if etag in [v.strip().removeprefix("W/") for v in environ.get("HTTP_IF_NONE_MATCH", "").split(",")] or environ.get("HTTP_IF_NONE_MATCH") == "*":
                start_response("304 Not Modified", headers)
                return []
        headers.append(("Content-Length", str(len(body))))
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [] if method == "HEAD" else [body]


class LocalServer(WSGIServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address


def serve(bundle, port):
    with make_server("127.0.0.1", port, Application(bundle), server_class=LocalServer) as server:
        print(f"Inspection API: http://127.0.0.1:{server.server_port}/api/v1", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
