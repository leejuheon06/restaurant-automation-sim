"""Tiny JSON-over-HTTP helper (standard library only) shared by the web service and the guest simulator UI."""
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def serve(port, static_dir, get_routes, post_routes, pages=None):
    """get_routes/post_routes: {path: fn(query|body) -> dict}. pages: {'/': 'index.html'}."""
    pages = pages or {}

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()

        def do_GET(self):
            u = urlparse(self.path)
            try:
                if u.path in get_routes:
                    return self._send(200, get_routes[u.path]({k: v[0] for k, v in parse_qs(u.query).items()}))
                name = pages.get(u.path) or (u.path[len('/static/'):] if u.path.startswith('/static/') else None)
                if name and '/' not in name and '..' not in name:
                    path = os.path.join(static_dir, name)
                    if os.path.isfile(path):
                        ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                        if ctype.startswith('text/') or ctype.endswith('javascript'):
                            ctype += '; charset=utf-8'
                        return self._send(200, open(path, 'rb').read(), ctype)
                self._send(404, {'ok': False, 'message': 'not found'})
            except Exception as e:  # noqa
                self._send(500, {'ok': False, 'message': str(e)})

        def do_POST(self):
            u = urlparse(self.path)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                if u.path in post_routes:
                    return self._send(200, post_routes[u.path](body))
                self._send(404, {'ok': False, 'message': 'not found'})
            except Exception as e:  # noqa
                self._send(500, {'ok': False, 'message': str(e)})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(('0.0.0.0', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
