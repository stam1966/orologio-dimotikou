"""Σουίτα: φάκελος δεδομένων, ρόλος/PIN, κλείδωμα, αναπληρώσεις σε κοινό αρχείο, αρχεία για τις Εφημερίες."""
import unittest, sys, os, json, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import core, suite, exchange

FIX = Path(__file__).parent / 'gymnasio_fixture.json'


class SuiteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.old = os.environ.get('SCHOOLAPPS_CONFIG')
        os.environ['SCHOOLAPPS_CONFIG'] = str(self.tmp / 'cfg' / 'suite.json')

    def tearDown(self):
        if self.old is None:
            os.environ.pop('SCHOOLAPPS_CONFIG', None)
        else:
            os.environ['SCHOOLAPPS_CONFIG'] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)


class Machine(SuiteBase):
    def test_local_default(self):
        self.assertFalse(suite.shared()); self.assertEqual(suite.data_dir('/app'), Path('/app') / 'data')
        self.assertEqual(suite.effective_role(), 'director')
        self.assertEqual(suite.common_dir(), self.tmp / 'cfg' / 'Κοινά')

    def test_roles_and_pin(self):
        root = self.tmp / 'share'; root.mkdir()
        suite.save_machine({'root': str(root), 'role': 'director', 'confirmed': False})
        self.assertEqual(suite.effective_role(), 'deputy')          # χωρίς PIN δεν γίνεται Διεύθυνση
        with self.assertRaises(ValueError):
            suite.set_pin('12')                                      # πολύ μικρό
        suite.set_role('director', '2468'); self.assertTrue(suite.has_pin()); self.assertEqual(suite.effective_role(), 'director')
        with self.assertRaises(ValueError):
            suite.set_role('deputy', '0000')                         # αλλαγή ρόλου θέλει το PIN
        suite.set_role('deputy', '2468'); self.assertEqual(suite.effective_role(), 'deputy')
        with self.assertRaises(ValueError):
            suite.set_role('director', '1111')
        with self.assertRaises(ValueError):
            suite.set_pin('5555', '1111')
        suite.set_pin('5555', '2468'); self.assertTrue(suite.check_pin('5555')); self.assertFalse(suite.check_pin('2468'))
        self.assertNotIn('5555', (root / 'Κοινά' / 'suite.json').read_text(encoding='utf-8'))

    def test_lock(self):
        d = self.tmp / 'o'; d.mkdir()
        self.assertEqual(suite.acquire(d), (True, None))
        info = json.loads((d / 'editor.lock').read_text(encoding='utf-8')); info['pid'] = -1; info['pc'] = 'ΑΛΛΟΣ'
        (d / 'editor.lock').write_text(json.dumps(info), encoding='utf-8')
        ok, holder = suite.acquire(d); self.assertFalse(ok); self.assertEqual(holder['pc'], 'ΑΛΛΟΣ')
        info['beat'] = 0; (d / 'editor.lock').write_text(json.dumps(info), encoding='utf-8')
        self.assertTrue(suite.acquire(d)[0])                         # εγκαταλελειμμένο κλείδωμα
        suite.release(d); self.assertFalse((d / 'editor.lock').exists())

    def test_merge_subs(self):
        d = self.tmp / 'o'; d.mkdir()
        a = [{'date': '2026-11-16', 'absent': [{'teacher': 'T1'}], 'covers': []}]
        self.assertEqual(suite.merge_subs(d, [], a), a)
        b = [{'date': '2026-11-17', 'absent': [{'teacher': 'T2'}], 'covers': []}]
        out = suite.merge_subs(d, [], b)                              # άλλος υπολογιστής πρόσθεσε άλλη ημέρα
        self.assertEqual([r['date'] for r in out], ['2026-11-16', '2026-11-17'])
        out = suite.merge_subs(d, a, [])                              # διαγραφή μόνο της δικής μας ημέρας
        self.assertEqual([r['date'] for r in out], ['2026-11-17']); self.assertEqual(suite.load_subs(d), out)

    def test_cloud(self):
        self.assertTrue(suite.cloud_folder(r'C:\Users\x\OneDrive\Σχολείο')); self.assertFalse(suite.cloud_folder(r'\\server\koina'))


class Exchange(SuiteBase):
    def test_files(self):
        p = core.check_structure(json.loads(FIX.read_text(encoding='utf-8')))
        t = p['teachers'][0]['id']
        p['substitutions'] = [{'date': '2026-11-16', 'absent': [{'teacher': t, 'periods': None, 'reason': 'άδεια'}], 'covers': []}]
        self.assertIsNone(exchange.write(p))
        snap = json.loads((suite.common_dir() / 'orologio.json').read_text(encoding='utf-8'))
        self.assertEqual(snap['format'], 'orologio-snapshot'); self.assertEqual(len(snap['periods']), len(p['periods']))
        T = {x['id']: x for x in snap['teachers']}
        L = core.mapping(p, 'lessons'); n = sum(l['duration'] for e in p['events'] if e['place'] for l in [L[e['lesson']]] if t in l['teachers'])
        self.assertEqual(sum(len(x) for x in T[t]['periods']), n)
        ab = json.loads((suite.common_dir() / 'apousies.json').read_text(encoding='utf-8'))['absences']
        self.assertEqual((ab[0]['date'], ab[0]['name'], ab[0]['periods']), ('2026-11-16', p['teachers'][0]['name'], None))


class ServerShared(SuiteBase):
    """Ροή του server σε κοινό φάκελο: Διεύθυνση, κλειδωμένο από άλλον, Υποδιευθυντής."""
    def setUp(self):
        super().setUp()
        import server
        self.S = server; self.app = self.tmp / 'app'; (self.app / 'data').mkdir(parents=True)
        shutil.copy(FIX, self.app / 'data' / 'project.json')
        self.saved = (server.ROOT, server.DDIR, server.DATA); server.ROOT = self.app
        self.root = self.tmp / 'share'; self.root.mkdir()

    def tearDown(self):
        try:
            self.S.suite.release(self.S.DDIR)
        except Exception:
            pass
        self.S.ROOT, self.S.DDIR, self.S.DATA = self.saved
        self.S.STATE['suite'] = {}
        super().tearDown()

    def test_flow(self):
        S = self.S
        S.boot(); self.assertFalse(S.STATE['suite']['shared'])
        st = json.loads(S.suite_action('connect', {'root': str(self.root), 'create': True, 'role': 'director', 'pin': '1234'}))
        self.assertTrue(st['suite']['shared']); self.assertEqual(st['suite']['role'], 'director'); self.assertEqual(st['suite']['readonly'], '')
        base = self.root / 'Σχολικές Εφαρμογές'
        self.assertTrue((base / 'Ωρολόγιο' / 'project.json').exists()); self.assertTrue((base / 'Κοινά' / 'orologio.json').exists())
        p = S.STATE['project']; t = p['teachers'][0]['id']
        q = json.loads(json.dumps(p)); q['substitutions'] = [{'date': '2026-11-16', 'absent': [{'teacher': t, 'periods': None, 'reason': ''}], 'covers': []}]
        S.commit(q, 'απουσία')
        self.assertEqual(len(json.loads((base / 'Ωρολόγιο' / 'anaplirwseis.json').read_text(encoding='utf-8'))['records']), 1)
        # άλλος υπολογιστής κρατά το κλείδωμα → μόνο προβολή, αλλά αναπληρώσεις επιτρέπονται
        lk = base / 'Ωρολόγιο' / 'editor.lock'; info = json.loads(lk.read_text(encoding='utf-8')); info.update(pc='ΑΛΛΟΣ', pid=-1)
        lk.write_text(json.dumps(info), encoding='utf-8'); S.take_lock()
        self.assertEqual(S.STATE['suite']['readonly'], 'locked')
        q = json.loads(json.dumps(S.STATE['project'])); q['school'] = 'Άλλο'
        with self.assertRaises(ValueError):
            S.commit(q)
        q = json.loads(json.dumps(S.STATE['project'])); q['substitutions'].append({'date': '2026-11-17', 'absent': [{'teacher': t, 'periods': [0, 1], 'reason': ''}], 'covers': []})
        S.commit(q, 'απουσία 2')
        self.assertEqual(len(S.suite.load_subs(base / 'Ωρολόγιο')), 2)
        # ο άλλος υπολογιστής αλλάζει το πρόγραμμα → συγχρονισμός
        other = core.load(base / 'Ωρολόγιο' / 'project.json'); other['school'] = 'Νέο όνομα'; core.save(other, base / 'Ωρολόγιο' / 'project.json')
        os.utime(base / 'Ωρολόγιο' / 'project.json', (1, 1))
        self.assertTrue(S.sync()); self.assertEqual(S.STATE['project']['school'], 'Νέο όνομα'); self.assertEqual(len(S.STATE['project']['substitutions']), 2)
        # ανάληψη ελέγχου, μετά ρόλος Υποδιευθυντή
        S.suite_action('takeover', {}); self.assertEqual(S.STATE['suite']['readonly'], '')
        with self.assertRaises(ValueError):
            S.suite_action('role', {'role': 'deputy', 'pin': '0000'})
        S.suite_action('role', {'role': 'deputy', 'pin': '1234'}); self.assertEqual(S.STATE['suite']['readonly'], 'deputy')
        # σύνδεση 2ου υπολογιστή σε υπάρχουσα σουίτα δείχνοντας τον γονικό φάκελο
        st = json.loads(S.suite_action('connect', {'root': str(self.root), 'role': 'deputy'}))
        self.assertEqual(st['suite']['root'], str(base)); self.assertEqual(st['suite']['role'], 'deputy')
        with self.assertRaises(ValueError):
            S.suite_action('connect', {'root': str(self.root), 'role': 'director', 'pin': '9999'})
        self.assertEqual(S.suite.machine()['role'], 'deputy')                 # η αποτυχία δεν άλλαξε τον ρόλο
        S.suite_action('disconnect', {}); self.assertFalse(S.STATE['suite']['shared'])
        self.assertEqual(core.load(self.app / 'data' / 'project.json')['school'], 'Νέο όνομα')


if __name__ == '__main__':
    unittest.main()
