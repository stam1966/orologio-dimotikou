"""Έλεγχοι τρόπων παραγωγής και ιστορικού αναίρεσης της τοπικής υπηρεσίας."""
import unittest, sys, copy, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server, core
from test_rules import base, add_lesson

def placed_fixture():
    p = base(3, 3)
    for k, e in enumerate(p['events']): e['place'] = [k % 5, 1 + k // 5]
    p['events'][0]['place'] = None
    return p

class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); server.DATA = Path(self.tmp.name) / 'project.json'
        server.UNDO.clear(); server.REDO.clear(); server.STATE.update(project=None, revision=0)
    def tearDown(self): self.tmp.cleanup()

    def test_prepare_modes(self):
        p = placed_fixture()
        q = server.prepare(p, 'fill', None)
        self.assertTrue(all(e.get('stay') for e in q['events'] if e['place']))
        self.assertFalse(any(e['locked'] for e in p['events']))  # το πρωτότυπο δεν αλλάζει
        q = server.prepare(p, 'scratch', None)
        self.assertTrue(all(e['place'] is None for e in q['events']))
        q = server.prepare(p, 'entity', ('teachers', 'ta'))
        ls = core.mapping(q, 'lessons')
        for e in q['events']:
            if e['place']: self.assertEqual(e['locked'], 'ta' not in ls[e['lesson']]['teachers'])

    def test_fill_keeps_placed(self):
        p = placed_fixture(); before = {e['id']: e['place'] for e in p['events'] if e['place']}
        r = core.solve(server.prepare(p, 'fill', None), 10)
        self.assertIn(r['status'], ['optimal', 'feasible'])
        for e in r['project']['events']:
            if e['id'] in before: self.assertEqual(e['place'], before[e['id']])
            self.assertIsNotNone(e['place'])

    def test_fill_moves_minimum_when_needed(self):
        # Υπάρχουσα παραβίαση: 2 φορές Γλώσσα την ίδια ημέρα με όριο 1. Η συμπλήρωση τη διορθώνει μετακινώντας μόνο μία.
        p = base(3, 2); place = {'la0': [0, 1], 'la1': [0, 2], 'la2': None, 'lb0': [1, 1], 'lb1': [2, 1]}
        for e in p['events']: e['place'] = place[e['id']]
        p['subject_rules']['s1'] = {'max_per_day': {'v': 1, 'w': 0}}
        r = core.solve(server.prepare(p, 'fill', None), 10)
        self.assertIn(r['status'], ['optimal', 'feasible'])
        q = r['project']; moved = [e['id'] for e in q['events'] if place[e['id']] and e['place'] != place[e['id']]]
        self.assertEqual(len(moved), 1); self.assertEqual(core.validation(q, True), [])

    def test_undo_redo(self):
        p = placed_fixture(); server.commit(p, 'Αρχή', history=False)
        q = copy.deepcopy(p); q['title'] = 'Β'; server.commit(q, 'Τίτλος')
        self.assertEqual(server.UNDO[-1][0], 'Τίτλος')
        label, old = server.UNDO.pop(); server.REDO.append((label, server.STATE['project'])); server.commit(old, history=False)
        self.assertNotEqual(server.STATE['project']['title'], 'Β')
        s = server.summary(server.STATE['project']); self.assertEqual(s['unplaced'], 1)

if __name__ == '__main__': unittest.main(verbosity=2)

class Versions(unittest.TestCase):
    def test_save_list_diff_report(self):
        import versions
        with tempfile.TemporaryDirectory() as d:
            p = placed_fixture(); vid = versions.save(d, p, 'Σεπτέμβριος')
            self.assertEqual([v['name'] for v in versions.listing(d)], ['Σεπτέμβριος'])
            q = copy.deepcopy(p); e = next(x for x in q['events'] if x['place'] and x['lesson'] == 'la'); e['place'] = [4, 6]
            diff = versions.diff(versions.load(d, vid)['project'], q)
            self.assertEqual([r['id'] for r in diff], ['ta']); self.assertIn('→ Παρασκευή', diff[0]['changes'][0])
            self.assertIn('Σεπτέμβριος', versions.changes_report(p, q, 'Σεπτέμβριος'))
            self.assertEqual(versions.diff(p, p), [])
            versions.delete(d, vid); self.assertEqual(versions.listing(d), [])
            with self.assertRaises(ValueError): versions.load(d, '../../etc')

class Backups(unittest.TestCase):
    def test_settings_daily_prune_points(self):
        import backup, os, time
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'data' / 'backups').mkdir(parents=True)
            proj = root / 'data' / 'project.json'; proj.write_text('{"x":1}', encoding='utf-8')
            self.assertIsNone(backup.daily(root, proj))                   # χωρίς φάκελο: τίποτα
            dest = root / 'usb'; dest.mkdir()
            s = backup.load_settings(root); s['backup_dir'] = backup.ensure_folder(str(dest / 'Ωρολόγιο - αντίγραφα')); backup.save_settings(root, s)
            path = backup.daily(root, proj); self.assertTrue(Path(path).exists())
            self.assertIsNone(backup.daily(root, proj))                   # ήδη σήμερα
            self.assertTrue(backup.daily(root, proj, force=True))
            with self.assertRaises(ValueError): backup.check_folder(str(root / 'δεν-υπάρχει'))
            for k in range(200):                                          # 200 αντίγραφα, 2 ανά ημέρα
                day = 20260101 + k // 2 if k // 2 < 28 else 20260201 + (k // 2 - 28) % 28
                (root / 'data' / 'backups' / ('project_%d_%02d%02d00_000000.json' % (day, 8 + k % 10, k % 60))).write_text('{}')
            (root / 'data' / 'backups' / 'project_20261399_999999_0.json').write_text('{}')  # μη έγκυρο όνομα: αγνοείται
            backup.prune(root, keep_recent=50, days_daily=100000)
            pts = backup.points(root)
            self.assertLess(len(pts), 200); self.assertGreaterEqual(len(pts), 50)
            self.assertEqual(len({p['day'] for p in pts}), len({p['day'] for p in pts}))
            self.assertRegex(pts[0]['when'], r'\d\d/\d\d/\d{4} \d\d:\d\d:\d\d')
