"""A single local callback for provider consent, with no request logging."""
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from .account_providers import REDIRECT


def listener(expected):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(0.6)
            super().setup()

        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            params = parse_qs(url.query, max_num_fields=12)
            state = params.get("state", [])
            valid = (self.headers.get("Host") == "127.0.0.1:54381" and url.path == "/callback"
                     and len(state) == 1 and state[0].isascii() and compare_digest(state[0], expected))
            codes = params.get("code", [])
            if valid and len(codes) == 1 and 0 < len(codes[0]) < 4096:
                self.server.code = codes[0]
            elif valid and params.get("error"):
                self.server.denied = True
            self.send_response(200 if valid else 400)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Return to Nexus Exchange to see your connection status.")
    class Callback(HTTPServer):
        allow_reuse_address = False
        def handle_error(self, request, client_address):
            pass
    uri = urlsplit(REDIRECT)
    server = Callback((uri.hostname, uri.port), Handler)
    server.timeout = 0.25
    server.code, server.denied = None, False
    return server


def receive(server, stopped):
    until = monotonic() + 180
    while not stopped() and monotonic() < until and not server.denied:
        server.handle_request()
        if server.code and not stopped():
            return server.code
    raise ValueError("Consent was cancelled or timed out.")
