"""Local web app: load an .als, see where it deviates from the template, restyle selected categories.

Usage: python3 -m bbb.app [port]     then open http://localhost:8765

Only listens on localhost, and only reads/writes .als files inside the Bovenburen folder.
"""
import glob
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import als, restyle

HERE = os.path.dirname(os.path.abspath(__file__))
BOVENBUREN = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
PROJECT_DIRS = ['c_opzetjes', 'b_tracks', 'b1_tracks met Anna']

_cache = {}   # (path, mtime) -> analysis json
_lock = threading.Lock()


def list_projects():
    out = []
    for sub in PROJECT_DIRS:
        for d in sorted(glob.glob(os.path.join(BOVENBUREN, sub, '*/')), key=str.lower):
            files = sorted(glob.glob(os.path.join(d, '*.als')), key=os.path.getmtime, reverse=True)
            if files:
                out.append(dict(folder=sub, project=os.path.basename(d.rstrip('/')),
                                versions=[os.path.basename(f) for f in files], dir=d))
    return out


def check_path(path):
    p = os.path.abspath(os.path.expanduser(path))
    if not p.startswith(BOVENBUREN + os.sep) or not p.endswith('.als') or not os.path.isfile(p):
        raise ValueError(f'not an .als inside {BOVENBUREN}: {path}')
    return p


def analysis(path):
    key = (path, os.path.getmtime(path))
    with _lock:
        if key in _cache:
            return _cache[key]
    root = als.load(path)
    plan = restyle.analyze(root)
    data = dict(
        path=path, file=os.path.basename(path), live=root.get('Creator'),
        categories=[dict(key=k, title=t, default=on, description=d,
                         sound=restyle.SOUND[k][0], sound_text=restyle.SOUND[k][1],
                         items=[dict(track=c.track, detail=c.detail) for c in plan.changes if c.category == k])
                    for k, (t, on, d) in restyle.CATEGORIES.items()],
        notes=plan.notes, tracks=plan.tracks, warnings=plan.warnings, next=os.path.basename(restyle.next_version_path(path)))
    with _lock:
        _cache[key] = data
    return data


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            with open(os.path.join(HERE, 'app.html'), 'rb') as f:
                return self._send(200, f.read(), 'text/html; charset=utf-8')
        if self.path == '/api/projects':
            return self._send(200, list_projects())
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            path = check_path(req['path'])
            if self.path == '/api/analyze':
                return self._send(200, analysis(path))
            if self.path == '/api/write':
                cats = [c for c in req['categories'] if c in restyle.CATEGORIES]
                out, done = restyle.restyle_file(path, cats)
                return self._send(200, dict(out=out, file=os.path.basename(out), changes=len(done), sound_check=True))
            self._send(404, {'error': 'not found'})
        except Exception as e:  # report to the page instead of dropping the connection
            self._send(400, {'error': str(e)})

    def log_message(self, fmt, *args):
        sys.stderr.write('%s\n' % (fmt % args))


def main():
    port = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8765)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://localhost:{port}'
    print(f'BBB restyle running at {url}  (Ctrl+C to stop)')
    if '--no-browser' not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == '__main__':
    main()
