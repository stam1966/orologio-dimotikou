import unittest, sys, json, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import core, subs, outputs

DEMO = json.loads((Path(__file__).resolve().parents[1] / 'src' / 'demo_school.json').read_text(encoding='utf-8'))


class Substitutions(unittest.TestCase):
    def setUp(self):
        self.p = core.check_structure(copy.deepcopy(DEMO))
        self.t0, self.t1 = self.p['teachers'][0]['id'], self.p['teachers'][1]['id']

    def test_needs_candidates_auto(self):
        p = self.p
        rec = dict(date='2026-11-09', absent=[dict(teacher=self.t0, periods=None, reason='άδεια')], covers=[])
        d = subs.day(p, rec)
        self.assertEqual(d['day'], p['days'][0])
        mine = [e for e in p['events'] if e['place'] and e['place'][0] == 0 and self.t0 in core.mapping(p, 'lessons')[e['lesson']]['teachers']]
        self.assertTrue(d['needs']); self.assertLessEqual(len(d['needs']), sum(core.mapping(p, 'lessons')[e['lesson']]['duration'] for e in mine))
        for n in d['needs']:
            self.assertNotIn(self.t0, [c['teacher'] for c in n['candidates']])
            kinds = [c['kind'] for c in n['candidates']]; self.assertEqual(kinds, sorted(kinds))
        r = subs.auto(p, rec)
        per = {}
        for c in r['covers']:
            self.assertNotEqual(c['teacher'], self.t0)
            if c['teacher']:
                self.assertNotIn((c['teacher'], c['period']), per); per[c['teacher'], c['period']] = 1
        self.assertLessEqual(max(sum(1 for c in r['covers'] if c['teacher'] == t) for t in {c['teacher'] for c in r['covers']}), 2)
        p['substitutions'] = [r]; core.check_structure(p)
        self.assertEqual(sum(subs.counts(p).values()), sum(1 for c in r['covers'] if c['teacher']))
        for mode in ('subs_day', 'subs_stats'):
            self.assertIn('Αναπληρώσεις', outputs.report(p, dict(kind='teachers', mode=mode, date='2026-11-09')))
            outputs.export_xlsx(p, dict(kind='teachers', mode=mode, date='2026-11-09'))

    def test_partial_absence_and_validation(self):
        p = self.p
        rec = dict(date='2026-11-10', absent=[dict(teacher=self.t1, periods=[1], reason='')], covers=[])
        ns, _ = subs.needs(p, rec)
        self.assertTrue(all(n['period'] == 1 for n in ns))
        with self.assertRaises(ValueError): subs.weekday('2026-11-08')            # Κυριακή
        bad = copy.deepcopy(p); bad['substitutions'] = [dict(date='2026-11-10', absent=[dict(teacher='χ', periods=None)], covers=[])]
        with self.assertRaises(ValueError): core.check_structure(bad)
        bad['substitutions'] = [dict(date='x', absent=[], covers=[])]
        with self.assertRaises(ValueError): core.check_structure(bad)

    def test_disposal_hour_preferred(self):
        p = self.p
        rec = dict(date='2026-11-09', absent=[dict(teacher=self.t0, periods=None)], covers=[])
        n = subs.needs(p, rec)[0][0]
        # ο t1 αποκτά «ώρα διάθεσης» (ανάθεση χωρίς τμήμα) ακριβώς εκείνη την ώρα
        other = next(t['id'] for t in p['teachers'] if t['id'] != self.t0 and not subs.day_map(p, 0).get((t['id'], n['period'])))
        p['lessons'].append(dict(id='disp', subject=p['subjects'][0]['id'], teachers=[other], classes=[], groups=[], room='', hours=1, duration=1, days=[0, 1, 2, 3, 4], max_daily=0))
        p['events'].append(dict(id='dispe', lesson='disp', place=[0, n['period']], locked=False))
        c = subs.candidates(p, rec, n)
        self.assertEqual((c[0]['teacher'], c[0]['kind']), (other, 0))


if __name__ == '__main__':
    unittest.main()
