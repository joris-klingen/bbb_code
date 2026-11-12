import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from bbb import als, app
from tests.fixture import messy_set


class App(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = os.path.realpath(d.name)
        self.addCleanup(setattr, app, 'BOVENBUREN', app.BOVENBUREN)
        app.BOVENBUREN = self.root
        app._cache.clear()
        self.project = os.path.join(self.root, 'c_opzetjes', 'song Project')
        os.makedirs(self.project)
        self.set = os.path.join(self.project, 'song 1.0.als')
        als.save(messy_set().root, self.set)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def call(self, path, body=None, headers=None):
        h = {'Content-Type': 'application/json'} if body is not None else {}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None, h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_projects_analyze_write(self):
        code, projects = self.call('/api/projects')
        self.assertEqual((code, [p['project'] for p in projects]), (200, ['song Project']))
        code, data = self.call('/api/analyze', {'path': self.set})
        self.assertEqual(code, 200)
        self.assertEqual(data['next'], 'song 1.1 (restyle).als')
        code, res = self.call('/api/write', {'path': self.set, 'categories': ['group_names', 'bogus']})
        self.assertEqual((code, res['file'], res['sound_check']), (200, 'song 1.1 (restyle).als', True))

    def test_only_sets_inside_the_folder(self):
        with tempfile.TemporaryDirectory() as other:
            outside = os.path.join(other, 'x.als')
            als.save(messy_set().root, outside)
            self.assertEqual(self.call('/api/analyze', {'path': outside})[0], 400)
            link = os.path.join(self.project, 'link.als')
            os.symlink(outside, link)
            self.assertEqual(self.call('/api/analyze', {'path': link})[0], 400)

    def test_other_websites_are_refused(self):
        body = {'path': self.set, 'categories': ['group_names']}
        self.assertEqual(self.call('/api/write', body, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.call('/api/write', body, {'Content-Type': 'text/plain'})[0], 403)
        self.assertEqual(self.call('/api/projects', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(os.listdir(self.project), ['song 1.0.als'])


if __name__ == '__main__':
    unittest.main()
