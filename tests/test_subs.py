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
        self.assertEqual(core.check_structure(bad)['substitutions'][0]['absent'], [])  # άγνωστος (διαγραμμένος) → αφαιρείται
        bad['substitutions'] = [dict(date='2026-11-10', absent=[dict(teacher=self.t0, periods=[99])], covers=[])]
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


    def test_deleted_teacher_keeps_history(self):
        p = self.p; t = p['teachers'][-1]['id']
        ev = next(e for e in p['events'] if e['place'])
        p['substitutions'] = [dict(date='2026-11-09', absent=[dict(teacher=t, periods=None, reason='')],
                                   covers=[dict(event=ev['id'], period=ev['place'][1], teacher=t, kind='teacher', note='')])]
        q = copy.deepcopy(p); q['teachers'] = [x for x in q['teachers'] if x['id'] != t]
        q = core.check_structure(q)
        r = q['substitutions'][0]
        self.assertEqual(r['absent'], []); self.assertEqual(r['covers'][0]['kind'], 'other'); self.assertEqual(r['covers'][0]['teacher'], '')

    def test_history_survives_deleted_lesson_only(self):
        p = self.p
        rec = subs.auto(p, dict(date='2026-11-10', absent=[dict(teacher=self.t0, periods=None, reason='')], covers=[]))
        p['substitutions'] = [rec]; p = core.check_structure(p)
        covs = [x for x in p['substitutions'][0]['covers'] if x['teacher']]; c = covs[0]
        before = subs.counts(p)
        lid = next(e['lesson'] for e in p['events'] if e['id'] == c['event'])
        q = copy.deepcopy(p); q['lessons'] = [l for l in q['lessons'] if l['id'] != lid]; q['events'] = [e for e in q['events'] if e['lesson'] != lid]
        q = core.check_structure(q); q = core.check_structure(copy.deepcopy(q))   # και μετά από επόμενες αποθηκεύσεις
        r2 = q['substitutions'][0]
        self.assertEqual(len([x for x in r2['covers'] if x['teacher']]), len(covs))
        self.assertEqual(subs.counts(q), before)
        h = subs.day(q, r2)['history']; self.assertTrue(any(x['event'] == c['event'] and x['subject'] for x in h))
        rows = subs.day_pages(q, '2026-11-10')[0]['rows']
        self.assertTrue(any('από παλαιότερο πρόγραμμα' in r[5] for r in rows))

    def test_history_survives_deleted_lesson_and_teacher(self):
        p = self.p
        rec = subs.auto(p, dict(date='2026-11-09', absent=[dict(teacher=self.t0, periods=None, reason='')], covers=[]))
        p['substitutions'] = [rec]; p = core.check_structure(p)
        r = p['substitutions'][0]; c = next(x for x in r['covers'] if x['teacher'])
        self.assertEqual(set(c['snap']), set(subs.SNAP_KEYS)); self.assertTrue(c['snap']['teacher'])
        before = subs.counts(p)[c['teacher']]
        # διαγράφεται η ανάθεση της ώρας που καλύφθηκε και ο εκπαιδευτικός που απουσίαζε
        lid = next(e['lesson'] for e in p['events'] if e['id'] == c['event'])
        q = copy.deepcopy(p); q['lessons'] = [l for l in q['lessons'] if l['id'] != lid]; q['events'] = [e for e in q['events'] if e['lesson'] != lid]
        q['teachers'] = [t for t in q['teachers'] if t['id'] != self.t0]
        for l in q['lessons']: l['teachers'] = [t for t in l['teachers'] if t != self.t0]
        for c_ in q['classes']:
            if c_.get('teacher') == self.t0: c_['teacher'] = ''
        q['teacher_rules'].pop(self.t0, None)
        dead = {l['id'] for l in q['lessons'] if not l['teachers']}
        q['lessons'] = [l for l in q['lessons'] if l['id'] not in dead]; q['events'] = [e for e in q['events'] if e['lesson'] not in dead]
        q = core.check_structure(q)
        r2 = q['substitutions'][0]
        self.assertIn(c['event'], [x['event'] for x in r2['covers']])          # δεν χάθηκε
        self.assertEqual(subs.counts(q)[c['teacher']], before)                  # μετρά ακόμη
        self.assertTrue(r2.get('gone'))                                          # το όνομα του απόντα μένει
        d = subs.day(q, r2); self.assertTrue(any(h['event'] == c['event'] for h in d['history']))
        html = outputs.report(q, dict(kind='teachers', mode='subs_day', date='2026-11-09'))
        self.assertIn('παλαιότερο πρόγραμμα', html); self.assertIn(r2['gone'][0], html)


if __name__ == '__main__':
    unittest.main()


class Compact(unittest.TestCase):
    """Συμπτύξεις Β/θμιας: ανεβαίνουν μαθήματα των τελευταίων ωρών του τμήματος."""
    def setUp(self):
        import json as _j, core as _c
        from pathlib import Path as _P
        self.p = _c.check_structure(_j.loads((_P(__file__).parent / 'gymnasio_fixture.json').read_text(encoding='utf-8')))
        self.T = {t['name']: t['id'] for t in self.p['teachers']}

    def test_compact_moves_and_needs(self):
        import subs as S
        p = self.p
        rec = {'date': '2026-11-12', 'absent': [{'teacher': self.T['Δημητρίου Παύλος'], 'periods': None, 'reason': ''}], 'covers': []}
        before, _ = S.needs(p, rec)
        r = S.compact(p, rec)
        after, _ = S.needs(p, r)
        done = S.compacted(p, r)
        self.assertEqual(len(before), len(after) + len(done))
        self.assertTrue(r['compact'])
        L = {l['id']: l for l in p['lessons']}; E = {e['id']: e for e in p['events']}
        busy = {}
        for (t, j), (e, l) in S.day_map(p, 3, r).items():
            busy.setdefault(t, set()).add(j)
        for m in r.get('moves', []):
            l = L[E[m['event']]['lesson']]
            self.assertTrue(all(self.T['Δημητρίου Παύλος'] != t for t in l['teachers']))
            self.assertLess(m['to'], m['from'])
        # κανένα τμήμα δεν έχει κενό στη μέση μετά τις συμπτύξεις, εκτός από ώρες που μένουν για αναπλήρωση
        open_ = {(n['class_ids'][0], n['period']) for n in after}
        for c, tl in S.class_day(p, r).items():
            end = S.class_end(r, tl)
            for j in range(min(tl), end + 1):
                live = j in tl and not S._gone_at(r, tl[j][1], tl[j][2])
                self.assertTrue(live or (c, j) in open_, (c, j))
        g = S.grid(p, r)
        self.assertTrue(any(c['kind'] == 'moved' for row in g['rows'] for c in row['cells'].values()) == bool(r.get('moves')))
        # αποθήκευση και εκτύπωση
        q = dict(p); q['substitutions'] = [S.auto(p, r)]
        q = core.check_structure(json.loads(json.dumps(q)))
        self.assertTrue(q['substitutions'][0]['compact'])
        self.assertIn('Πρόγραμμα ημέρας', outputs.report(q, dict(kind='teachers', mode='subs_day', date='2026-11-12')))
        self.assertNotIn('compact', S.uncompact(r))

    def test_last_hour_leaves_early(self):
        import subs as S
        p = self.p; L = {l['id']: l for l in p['lessons']}
        # εκπαιδευτικός με μάθημα την τελευταία ώρα ενός τμήματος την Πέμπτη
        cd = S.class_day(p, {'date': '2026-11-12', 'absent': [], 'covers': []})
        c, tl = next(iter(sorted(cd.items())))
        last = max(tl); e, l, _ = tl[last]
        rec = {'date': '2026-11-12', 'absent': [{'teacher': l['teachers'][0], 'periods': [last], 'reason': ''}], 'covers': []}
        r = S.compact(p, rec)
        done = S.compacted(p, r)
        self.assertTrue(any(n['period'] == last and 'σχολάει' in n['how'] for n in done))


class Replan(unittest.TestCase):
    """Ανασχεδιασμός ημέρας: όλα τα μαθήματα της ημέρας σε νέες ώρες, χωρίς συγκρούσεις."""
    def test_replan(self):
        import json as _j, core as _c, subs as S
        from pathlib import Path as _P
        p = _c.check_structure(_j.loads((_P(__file__).parent / 'gymnasio_fixture.json').read_text(encoding='utf-8')))
        T = {t['name']: t['id'] for t in p['teachers']}
        L = {l['id']: l for l in p['lessons']}
        for who, day in (('Δημητρίου Παύλος', '2026-11-12'), ('Ιωαννίδου Μαρία', '2026-11-13')):
            rec = {'date': day, 'absent': [{'teacher': T[who], 'periods': None, 'reason': ''}], 'covers': []}
            wd = S.weekday(day)
            c, r = S.compact(p, rec), S.replan(p, rec, iterations=20000)
            self.assertTrue(r['compact'] and r['replan'])
            self.assertLessEqual(len(S.needs(p, r)[0]), len(S.needs(p, c)[0]))
            mv = {m['event']: m['to'] for m in r.get('moves', [])}; seen = set()
            for e in p['events']:
                if e['place'] and e['place'][0] == wd and not S._gone_at(r, L[e['lesson']], e['place'][1]):
                    s = mv.get(e['id'], e['place'][1])
                    for k in [('t', t, s) for t in L[e['lesson']]['teachers']] + [('c', x, s) for x in L[e['lesson']]['classes']]:
                        self.assertNotIn(k, seen); seen.add(k)
                    self.assertNotIn(T[who], L[e['lesson']]['teachers'])
            q = dict(p); q['substitutions'] = [S.auto(p, r)]
            q = _c.check_structure(_j.loads(_j.dumps(q)))
            self.assertTrue(q['substitutions'][0]['replan'])
            self.assertNotIn('replan', S.uncompact(r))


class ReplanNoLater(unittest.TestCase):
    def test_no_teacher_leaves_later(self):
        import json as _j, core as _c, subs as S
        from pathlib import Path as _P
        p = _c.check_structure(_j.loads((_P(__file__).parent / 'gymnasio_fixture.json').read_text(encoding='utf-8')))
        for t in p['teachers'][:6]:
            for day in ('2026-11-09', '2026-11-12'):
                rec = {'date': day, 'absent': [{'teacher': t['id'], 'periods': None, 'reason': ''}], 'covers': []}
                wd = S.weekday(day); base = {}; after = {}
                for (x, j), _ in S.day_map(p, wd, rec).items():
                    if x != t['id']: base[x] = max(base.get(x, -1), j)
                r = S.replan(p, rec, iterations=6000)
                for (x, j), _ in S.day_map(p, wd, r).items():
                    if x != t['id']: after[x] = max(after.get(x, -1), j)
                self.assertTrue(all(after[x] <= base[x] for x in after), (t['name'], day))
