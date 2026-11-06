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


if __name__ == '__main__':
    unittest.main()
