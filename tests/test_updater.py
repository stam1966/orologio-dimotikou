"""Έλεγχοι ενημέρωσης εφαρμογής από αρχείο."""
import unittest, sys, io, json, zipfile, tempfile, shutil
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
import updater, core

def make_zip(version='9.9.9', extra=None, drop=(), manifest=True, app='orologio-dimotikou'):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        if manifest: z.writestr(updater.MANIFEST, json.dumps({'app': app, 'version': version, 'notes': 'δοκιμή'}))
        for p in SRC.iterdir():
            if p.is_file() and 'src/' + p.name not in drop and p.suffix in ('.py', '.html', '.ico'):
                z.writestr('src/' + p.name, p.read_bytes())
        z.writestr('UPDATE_TEST.txt', 'σημειώσεις')
        for n, data in (extra or {}).items(): z.writestr(n, data)
    return b.getvalue()

class Updater(unittest.TestCase):
    def test_accepts_valid(self):
        man, files = updater.read(make_zip())
        self.assertEqual(man['version'], '9.9.9'); self.assertIn('src/core.py', files)
        self.assertEqual(updater.verify(files), core.VERSION)  # ο νέος κώδικας φορτώνεται

    def test_rejects_unsafe_and_foreign(self):
        for extra in ({'../evil.py': 'x'}, {'data/project.json': '{}'}, {'runtime/python.exe': 'x'}, {'evil.exe': 'x'}, {'C:/x.txt': 'x'}):
            with self.assertRaises(ValueError): updater.read(make_zip(extra=extra))
        with self.assertRaises(ValueError): updater.read(make_zip(manifest=False))
        with self.assertRaises(ValueError): updater.read(make_zip(app='other'))
        with self.assertRaises(ValueError): updater.read(make_zip(drop=('src/server.py',)))
        with self.assertRaises(ValueError): updater.read(b'not a zip')

    def test_full_package_hint(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z: z.writestr('Orologio/runtime/python.exe', 'x')
        with self.assertRaisesRegex(ValueError, 'ΕΓΚΑΤΑΣΤΑΣΗ'): updater.read(b.getvalue())

    def test_broken_code_is_rejected_before_install(self):
        man, files = updater.read(make_zip(extra={'src/rules.py': 'def broken(:\n'}))
        with self.assertRaises(ValueError): updater.verify(files)

    def test_install_backup_rollback_keeps_data(self):
        root = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(SRC, root / 'src', ignore=shutil.ignore_patterns('__pycache__'))
            (root / 'tests').mkdir(); (root / 'tests' / 'old.py').write_text('# old')
            (root / 'data').mkdir(); (root / 'data' / 'project.json').write_text('ΔΕΔΟΜΕΝΑ')
            (root / 'START.cmd').write_text('old')
            saved = updater.backup(root, '1.0.0')
            man, files = updater.read(make_zip(extra={'START.cmd': 'new', 'src/extra.txt': 'νέο'}))
            updater.install(root, files)
            self.assertEqual((root / 'START.cmd').read_text(), 'new')
            self.assertTrue((root / 'src' / 'extra.txt').exists())
            self.assertTrue((root / 'tests' / 'old.py').exists())  # το zip δεν είχε tests: μένουν τα παλιά
            self.assertEqual((root / 'data' / 'project.json').read_text(), 'ΔΕΔΟΜΕΝΑ')
            self.assertEqual([b['version'] for b in updater.list_backups(root)], ['1.0.0'])
            man, files = updater.read(saved.read_bytes()); updater.install(root, files)  # επαναφορά
            self.assertEqual((root / 'START.cmd').read_text(), 'old')
            self.assertFalse((root / 'src' / 'extra.txt').exists())
            self.assertEqual((root / 'data' / 'project.json').read_text(), 'ΔΕΔΟΜΕΝΑ')
            self.assertFalse((root / 'data' / 'update_stage').exists()); self.assertFalse((root / 'data' / 'update_old').exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_versions(self):
        self.assertGreater(updater.vtuple('0.10.0-beta'), updater.vtuple('0.9.3'))
        self.assertEqual(updater.vtuple('0.4.0-beta'), (0, 4, 0))

class Online(unittest.TestCase):
    """Έλεγχος/λήψη από το Internet με ψεύτικο δίκτυο: εφεδρική πηγή όταν το GitHub δεν απαντά."""
    def setUp(self):
        import urllib.error, hashlib
        self.err = lambda code: urllib.error.HTTPError('u', code, 'x', {}, None)
        self.zipdata = b'ZIPDATA'; self.sha = hashlib.sha256(self.zipdata).hexdigest()
        self.orig = updater._get; self.calls = []
    def tearDown(self):
        updater._get = self.orig
    def net(self, table):
        def fake(url, limit, accept='', tries=3, timeout=30):
            self.calls.append(url)
            for key, val in table.items():
                if key in url:
                    if isinstance(val, Exception): raise val
                    return val
            raise AssertionError(url)
        updater._get = fake
    def mirror_json(self, version='9.9.9', sha=None):
        return json.dumps({'app': 'orologio-dimotikou', 'version': version, 'file': 'Orologio_Enimerosi.zip', 'sha256': sha or self.sha, 'notes': 'n'}).encode()
    def test_api_ok(self):
        api = json.dumps({'tag_name': 'v9.9.9', 'body': 'b', 'assets': [{'name': 'Orologio_Enimerosi_9.9.9.zip', 'browser_download_url': 'https://github.com/a.zip'}]}).encode()
        self.net({'api.github.com': api})
        i = updater.check_online(); self.assertEqual((i['version'], i['source']), ('9.9.9', 'github'))
    def test_api_down_uses_mirror(self):
        self.net({'api.github.com': self.err(504), 'latest.json': self.mirror_json(), 'updates/Orologio_Enimerosi.zip': self.zipdata})
        i = updater.check_online()
        self.assertEqual((i['version'], i['source']), ('9.9.9', 'mirror')); self.assertIn('raw.githubusercontent.com', i['url'])
        self.assertEqual(updater.download_info(i), self.zipdata)
    def test_both_down_clear_message(self):
        self.net({'api.github.com': self.err(503), 'latest.json': self.err(503)})
        with self.assertRaisesRegex(ValueError, 'δεν απαντά.*503.*releases/latest'): updater.check_online()
    def test_download_falls_back_and_checks_sha(self):
        info = {'version': '9.9.9', 'url': 'https://github.com/x.zip', 'source': 'github'}
        self.net({'github.com/x.zip': self.err(503), 'latest.json': self.mirror_json(), 'updates/Orologio_Enimerosi.zip': self.zipdata})
        self.assertEqual(updater.download_info(info), self.zipdata)
        self.net({'github.com/x.zip': self.err(503), 'latest.json': self.mirror_json(sha='0' * 64), 'updates/Orologio_Enimerosi.zip': self.zipdata})
        with self.assertRaises(ValueError): updater.download_info(info)
        self.net({'github.com/x.zip': self.err(503), 'latest.json': self.mirror_json(version='8.0.0')})   # άλλη έκδοση: δεν χρησιμοποιείται
        with self.assertRaises(ValueError): updater.download_info(info)
    def test_mirror_rejects_bad_file(self):
        self.net({'api.github.com': self.err(504), 'latest.json': json.dumps({'app': 'orologio-dimotikou', 'version': '1', 'file': '../x.zip'}).encode()})
        with self.assertRaises(ValueError): updater.check_online()
    def test_retry_on_5xx(self):
        import urllib.request
        n = [0]; orig = urllib.request.urlopen; sl = updater.time.sleep
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def geturl(s): return 'https://api.github.com/x'
            def read(s, n): return b'ok'
        def fake(req, timeout=0):
            n[0] += 1
            if n[0] < 3: raise self.err(503)
            return R()
        urllib.request.urlopen = fake; updater.time.sleep = lambda s: None
        try:
            self.assertEqual(self.orig('https://api.github.com/x', 10), b'ok'); self.assertEqual(n[0], 3)
            n[0] = -10
            with self.assertRaises(Exception): self.orig('https://api.github.com/x', 10)
        finally:
            urllib.request.urlopen = orig; updater.time.sleep = sl

if __name__ == '__main__': unittest.main(verbosity=2)
