"""Local web app: load an .als, see where it deviates from the template, restyle selected categories.

Usage: python3 -m bbb.app [port]     then open http://localhost:8765

Two views: one project at a time, or all projects in a folder (batch scan and batch restyle).
Only listens on localhost, only answers requests that come from its own page, and only
reads/writes .als files inside the Bovenburen folder (BBB_ROOT overrides where that is).
"""
import glob
import json
import os
import sys
import threading
import time
import webbrowser
from concurrent.futures import ProcessPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import als, restyle

HERE = os.path.dirname(os.path.abspath(__file__))
BOVENBUREN = os.path.realpath(os.environ.get('BBB_ROOT') or os.path.join(HERE, '..', '..', '..'))
PROJECT_DIRS = ['c_opzetjes', 'b_tracks', 'b1_tracks met Anna']
WORKERS = 4   # each worker holds a whole parsed set in memory (up to ~1-2 GB for the biggest)

_cache = {}   # (path, mtime) -> analysis json
_lock = threading.Lock()
_pool = None
_job = None   # the one batch job (scan or write) that may run at a time


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
    p = os.path.realpath(os.path.expanduser(path))   # realpath: a link may not lead outside the folder
    if not p.startswith(BOVENBUREN + os.sep) or not p.endswith('.als') or not os.path.isfile(p):
        raise ValueError(f'not an .als inside {BOVENBUREN}: {path}')
    return p


# --- work done in worker processes (must be top-level functions) ----------------------------

def analyze_path(path):
    root = als.load(path)
    plan = restyle.analyze(root)
    return dict(
        path=path, file=os.path.basename(path), live=root.get('Creator'), mtime=os.path.getmtime(path),
        categories=[dict(key=k, title=t, default=on, description=d,
                         sound=restyle.SOUND[k][0], sound_text=restyle.SOUND[k][1],
                         items=[dict(track=c.track, id=c.track_id, detail=c.detail, effect=c.effect)
                                for c in plan.changes if c.category == k])
                    for k, (t, on, d) in restyle.CATEGORIES.items()],
        notes=plan.notes, tracks=plan.tracks, warnings=plan.warnings,
        next=os.path.basename(restyle.next_version_path(path)))


def write_path(path, categories):
    out, done = restyle.restyle_file(path, categories)
    return dict(out=out, file=os.path.basename(out), changes=len(done), sound_check=True)


# --- in the server process --------------------------------------------------------------------

def pool():
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=WORKERS)
    return _pool


def remember(data):
    with _lock:
        for key in [k for k in _cache if k[0] == data['path']]:   # drop analyses of older saves
            del _cache[key]
        _cache[(data['path'], data['mtime'])] = data


def analysis(path):
    key = (path, os.path.getmtime(path))
    with _lock:
        if key in _cache:
            return _cache[key]
    data = analyze_path(path)
    remember(data)
    return data


def start_job(kind, tasks):
    """tasks: list of (key, fn, args). Runs them in the pool; results arrive in _job['results']."""
    global _job
    with _lock:
        if _job and _job['running']:
            raise ValueError('another batch job is still running')
        job = dict(id=str(time.time()), kind=kind, total=len(tasks), done=0, results={}, running=True)
        _job = job

    def run():
        futures = {}
        for key, fn, args in tasks:
            if kind == 'scan':  # served from cache when the file did not change
                path = args[0]
                k = (path, os.path.getmtime(path))
                with _lock:
                    cached = _cache.get(k)
                if cached:
                    job['results'][key] = dict(ok=True, data=cached)
                    job['done'] += 1
                    continue
            futures[pool().submit(fn, *args)] = key
        for f in as_completed(futures):
            key = futures[f]
            try:
                res = f.result()
                if kind == 'scan':
                    remember(res)
                job['results'][key] = dict(ok=True, data=res)
            except Exception as e:
                job['results'][key] = dict(ok=False, error=str(e))
            job['done'] += 1
        job['running'] = False

    threading.Thread(target=run, daemon=True).start()
    return job


def job_status(full):
    """Progress, plus the results; scan results are trimmed to what the overview table needs."""
    if not _job:
        return dict(job=None)
    res = {}
    for key, r in _job['results'].items():
        if r['ok'] and _job['kind'] == 'scan' and not full:
            d = r['data']
            r = dict(ok=True, data=dict(path=d['path'], file=d['file'], live=d['live'], next=d['next'],
                                        notes=len(d['notes']), warnings=d['warnings'],
                                        counts={c['key']: len(c['items']) for c in d['categories']}))
        res[key] = r
    return dict(job=dict(id=_job['id'], kind=_job['kind'], total=_job['total'], done=_job['done'],
                         running=_job['running'], results=res))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _own_page(self):
        """True when the request comes from this app's own page.

        Any website can make the browser send requests to localhost. The Host check stops a
        foreign domain that resolves to 127.0.0.1; for POST the Origin and the JSON content
        type (which a foreign page cannot send without a preflight we never grant) stop the rest.
        """
        hosts = {f'{h}:{self.server.server_port}' for h in ('localhost', '127.0.0.1')}
        if self.headers.get('Host') not in hosts:
            return False
        if self.command == 'POST':
            origin = self.headers.get('Origin')
            if origin is not None and origin not in {'http://' + h for h in hosts}:
                return False
            return self.headers.get('Content-Type', '').split(';')[0].strip() == 'application/json'
        return True

    def do_GET(self):
        if not self._own_page():
            return self._send(403, {'error': 'forbidden'})
        if self.path in ('/', '/index.html'):
            with open(os.path.join(HERE, 'app.html'), 'rb') as f:
                return self._send(200, f.read(), 'text/html; charset=utf-8')
        if self.path == '/api/projects':
            return self._send(200, list_projects())
        if self.path == '/api/job':
            return self._send(200, job_status(full=False))
        if self.path == '/api/categories':
            return self._send(200, [dict(key=k, title=t, default=on, description=d,
                                         sound=restyle.SOUND[k][0], sound_text=restyle.SOUND[k][1])
                                    for k, (t, on, d) in restyle.CATEGORIES.items()])
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if not self._own_page():
            return self._send(403, {'error': 'forbidden'})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            if self.path == '/api/batch/scan':
                paths = [check_path(p) for p in req['paths']]
                start_job('scan', [(p, analyze_path, (p,)) for p in paths])
                return self._send(200, job_status(full=False))
            if self.path == '/api/batch/write':
                cats = [c for c in req['categories'] if c in restyle.CATEGORIES]
                paths = [check_path(p) for p in req['paths']]
                start_job('write', [(p, write_path, (p, cats)) for p in paths])
                return self._send(200, job_status(full=False))
            path = check_path(req['path'])
            if self.path == '/api/analyze':
                return self._send(200, analysis(path))
            if self.path == '/api/write':
                cats = [c for c in req['categories'] if c in restyle.CATEGORIES]
                return self._send(200, write_path(path, cats))
            self._send(404, {'error': 'not found'})
        except Exception as e:  # report to the page instead of dropping the connection
            self._send(400, {'error': str(e)})

    def log_message(self, fmt, *args):
        if '/api/job' not in (args[0] if args else ''):  # polling would flood the log
            sys.stderr.write('%s\n' % (fmt % args))


def main():
    port = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8765)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://localhost:{port}'
    print(f'BBB Restyle running at {url}  (Ctrl+C to stop)')
    if '--no-browser' not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == '__main__':
    main()
