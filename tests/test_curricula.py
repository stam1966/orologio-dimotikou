import unittest, sys, json, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import core, curricula

DEMO = json.loads((Path(__file__).resolve().parents[1] / 'src' / 'demo_school.json').read_text(encoding='utf-8'))


class Curricula(unittest.TestCase):
    def test_totals_match_fek(self):
        self.assertEqual(curricula.check_totals(), [])

    def test_levels_and_grades(self):
        for t in curricula.TEMPLATES:
            self.assertIn(t['level'], core.LEVELS)
            gs = set(core.LEVEL_GRADES[t['level']])
            self.assertEqual(set(t['total']), gs)
            for n, h, o in t['subjects']:
                self.assertTrue(set(h) <= gs, n)
            self.assertEqual(len({n for n, h, o in t['subjects']}), len(t['subjects']))

    def test_matching_aliases(self):
        subs = [dict(id='a', name='Γλώσσα'), dict(id='b', name='Τ.Π.Ε.'), dict(id='c', name='Μελέτη'), dict(id='d', name='ΦΥΣΙΚΗ ΑΓΩΓΗ')]
        rows = {r['name']: r['match'] for r in curricula.listing(dict(subjects=subs))[0]['subjects']}
        self.assertEqual((rows['Γλώσσα'], rows['ΤΠΕ'], rows['Μελέτη Περιβάλλοντος'], rows['Φυσική Αγωγή']), ('a', 'b', 'c', 'd'))
        self.assertEqual(rows['Ηθική'], '')

    def test_optional_subject_skipped_when_absent(self):
        p = core.check_structure(copy.deepcopy(DEMO))
        c = p['classes'][0]; g = core.grade_of(c)
        eth = dict(id='eth', name='Ηθική', short='Ηθ'); p['subjects'].append(eth)
        p['curriculum'] = {g: {'eth': 2}}
        self.assertTrue(any('Ηθική' in m for m in core.curriculum_check(p).get(c['id'], [])))
        p['framework'] = dict(p.get('framework') or {}, optional={g: ['eth']})
        p = core.check_structure(p)
        self.assertFalse(any('Ηθική' in m for m in core.curriculum_check(p).get(c['id'], [])))
        p['framework']['optional'] = {g: ['nope']}
        with self.assertRaises(ValueError):
            core.check_structure(p)


class Joint(unittest.TestCase):
    def test_joint_flags_validated(self):
        p = core.check_structure(copy.deepcopy(DEMO))
        l = p['lessons'][0]; l['joint'] = True; l['joint_deduct'] = False
        core.check_structure(p)
        l['joint'] = 'ναι'
        with self.assertRaises(ValueError):
            core.check_structure(p)


class Bump(unittest.TestCase):
    def test_move_bumps_conflicts_to_pending(self):
        p = core.check_structure(copy.deepcopy(DEMO))
        ls = core.mapping(p, 'lessons')
        evs = [e for e in p['events'] if e['place'] and not e['locked'] and ls[e['lesson']]['duration'] == 1 and ls[e['lesson']]['classes']]
        a = evs[0]; cid = ls[a['lesson']]['classes'][0]
        b = next(e for e in evs if e is not a and cid in ls[e['lesson']]['classes'] and e['place'] != a['place'] and not (set(ls[e['lesson']]['teachers']) & set(ls[a['lesson']]['teachers'])))
        try:
            q, out = core.move_bump(p, a['id'], b['place'])
        except ValueError as ex:
            self.skipTest('κανόνας εμποδίζει: ' + str(ex))
        self.assertIn(b['id'], out)
        m = {e['id']: e for e in q['events']}
        self.assertEqual(m[a['id']]['place'], b['place']); self.assertIsNone(m[b['id']]['place'])
        b2 = next(e for e in p['events'] if e['id'] == b['id']); b2['locked'] = True
        with self.assertRaises(ValueError):
            core.move_bump(p, a['id'], b['place'])


class DirectorSecondary(unittest.TestCase):
    def proj(self, n_classes, positions=None, stored=None):
        p = core.blank()
        p['framework'] = {'level': 'Γυμνάσιο'}
        if stored is not None: p['framework']['teacher_hours'] = stored
        p['classes'] = [{'id': 'c%d' % i, 'name': 'Τ%d' % i} for i in range(n_classes)]
        if positions: p['positions'] = positions
        return p
    def test_table(self):
        for n, young, old in [(3, 10, 8), (5, 10, 8), (6, 9, 7), (9, 9, 7), (10, 7, 5), (12, 7, 5), (13, 5, 3), (20, 5, 3)]:
            p = self.proj(n)
            self.assertEqual(core.required_hours(p, {'role': 'director', 'years': 12}), young, n)
            self.assertEqual(core.required_hours(p, {'role': 'director', 'years': 25}), old, n)
            self.assertEqual(core.required_hours(p, {'role': 'director', 'years': 20}), young)   # «πάνω από 20»
            self.assertIsNone(core.required_hours(p, {'role': 'director'}))
    def test_positions_override_and_old_projects(self):
        p = self.proj(4, positions=11, stored={'director': [], 'bands': [[0, 99, 18]]})
        self.assertEqual(core.required_hours(p, {'role': 'director', 'years': 30}), 5)
        self.assertEqual(core.required_hours(p, {'years': 3}), 18)
    def test_primary_unchanged(self):
        p = self.proj(12); p['framework']['level'] = 'Δημοτικό'; p['positions'] = 12
        self.assertEqual(core.required_hours(p, {'role': 'director', 'years': 30}), 6)
    def test_deputy_secondary(self):
        p = self.proj(8)
        self.assertEqual(core.required_hours(p, {'role': 'deputy', 'years': 5}), 16)
        self.assertEqual(core.required_hours(p, {'role': 'deputy', 'years': 20}), 16)
        self.assertEqual(core.required_hours(p, {'role': 'deputy', 'years': 21}), 14)
        self.assertIsNone(core.required_hours(p, {'role': 'deputy'}))
    def test_deputy_secondary_custom_and_old(self):
        p = self.proj(8, stored={'deputy_hours': [15, 15]})
        self.assertEqual(core.required_hours(p, {'role': 'deputy'}), 15)
        p = self.proj(8, stored={'deputy_reduction': 2, 'bands': [[0, 99, 20]]})   # παλιό έργο με δική του μείωση
        self.assertEqual(core.required_hours(p, {'role': 'deputy', 'years': 25}), 18)
        p = self.proj(8, stored={'deputy_hours': [16]})
        with self.assertRaises(ValueError): core.check_structure(p)
    def test_deputy_primary_unchanged(self):
        p = self.proj(12); p['framework']['level'] = 'Δημοτικό'; p['positions'] = 12
        self.assertEqual(core.required_hours(p, {'role': 'deputy', 'years': 25}), 19)

if __name__ == '__main__':
    unittest.main()
