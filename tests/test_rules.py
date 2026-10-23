"""Έλεγχοι των κανόνων 0.2: τήρηση από τον solver, ίδια μέτρηση με τον ανεξάρτητο έλεγχο, διάγνωση."""
import unittest, sys, copy, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import core, rules as R

P = 7  # περίοδοι 0..6

def base(hours_a=4, hours_b=4):
    p = core.blank()
    p['periods'] = [dict(id=str(i), name=str(i), start=f'{8+i:02}:00', end=f'{8+i:02}:45') for i in range(P)]
    p['teachers'] = [dict(id='ta', name='Άλφα', short='Α'), dict(id='tb', name='Βήτα', short='Β')]
    p['classes'] = [dict(id='c1', name='Τμ1', short='1'), dict(id='c2', name='Τμ2', short='2')]
    p['subjects'] = [dict(id='s1', name='Γλώσσα', short='ΓΛ'), dict(id='s2', name='Φυσική Αγωγή', short='ΦΑ'), dict(id='pz', name='Πρωινή Ζώνη', short='ΠΖ')]
    p['lessons'] = [
        dict(id='la', subject='s1', teachers=['ta'], classes=['c1'], groups=[], room='', hours=hours_a, duration=1, days=[0, 1, 2, 3, 4], max_daily=0),
        dict(id='lb', subject='s2', teachers=['tb'], classes=['c2'], groups=[], room='', hours=hours_b, duration=1, days=[0, 1, 2, 3, 4], max_daily=0)]
    p['events'] = [dict(id=f'{l["id"]}{k}', lesson=l['id'], place=None, locked=False) for l in p['lessons'] for k in range(l['hours'])]
    return p

def add_lesson(p, lid, subject, teachers, classes, hours, duration=1, days=(0, 1, 2, 3, 4)):
    p['lessons'].append(dict(id=lid, subject=subject, teachers=teachers, classes=classes, groups=[], room='', hours=hours, duration=duration, days=list(days), max_daily=0))
    p['events'] += [dict(id=f'{lid}{k}', lesson=lid, place=None, locked=False) for k in range(hours // duration)]

def solved(t, p, seconds=20):
    r = core.solve(p, seconds)
    t.assertIn(r['status'], ['optimal', 'feasible'], r.get('message'))
    q = r['project']
    t.assertEqual(core.validation(q, True), [])
    if r['status'] == 'optimal':
        t.assertEqual(r['objective'], R.score(q), 'Ο solver και ο ανεξάρτητος έλεγχος μετρούν διαφορετικά')
    return q

def days_hours(q, t):
    ls = core.mapping(q, 'lessons'); out = [set() for _ in range(5)]
    for e in q['events']:
        l = ls[e['lesson']]
        if t in l['teachers'] and e['place']:
            for j in range(e['place'][1], e['place'][1] + l['duration']): out[e['place'][0]].add(j)
    return out

class Rules(unittest.TestCase):
    def test_max_consecutive_hard(self):
        p = base(8); p['teacher_rules']['ta'] = {'allowed': [[0, i] for i in range(P)] + [[1, i] for i in range(P)], 'max_consecutive': {'v': 2, 'w': 0}}
        q = solved(self, p)
        for used in days_hours(q, 'ta'):
            for i in used: self.assertFalse({i, i + 1, i + 2} <= used)

    def test_max_consecutive_soft_counts_excess(self):
        p = base(6); p['teacher_rules']['ta'] = {'allowed': [[0, i] for i in range(P)], 'max_consecutive': {'v': 2, 'w': 3}}
        p['global_rules'] = {'min_gaps': {'w': 1, 'on': False}}
        q = solved(self, p)  # 6 ώρες σε 7 περιόδους μίας ημέρας: αναγκαστικά παραβίαση
        self.assertTrue(core.warnings(q))

    def test_presence_target(self):
        p = base(6); p['teacher_rules']['ta'] = {'allowed': [[d, i] for d in (0, 1) for i in range(P)], 'presence': {'v': 8, 'w': 4}}
        q = solved(self, p)
        span = sum(max(u) - min(u) + 1 for u in days_hours(q, 'ta') if u)
        self.assertEqual(span, 8)

    def test_day_pattern_hard(self):
        p = base(13); p['teacher_rules']['ta'] = {'day_pattern': {'v': [[5, 1], [2, 4]], 'w': 0}}
        q = solved(self, p)
        self.assertEqual(sorted(len(u) for u in days_hours(q, 'ta')), [2, 2, 2, 2, 5])

    def test_balance(self):
        p = base(9); p['teacher_rules']['ta'] = {'allowed': [[d, i] for d in (0, 2, 4) for i in range(P)], 'balance': {'v': True, 'w': 5}}
        q = solved(self, p)
        self.assertEqual([len(u) for u in days_hours(q, 'ta')], [3, 0, 3, 0, 3])

    def test_earliest_hard_and_soft(self):
        p = base(5); p['teacher_rules']['ta'] = {'earliest': {'v': 3, 'w': 0}}
        q = solved(self, p)
        self.assertTrue(all(i >= 3 for u in days_hours(q, 'ta') for i in u))
        p['teacher_rules']['ta']['earliest']['w'] = 5
        q = solved(self, p)
        self.assertTrue(all(i >= 3 for u in days_hours(q, 'ta') for i in u))

    def test_subject_max_per_day_and_exemption(self):
        p = base(10, 2); p['subject_rules']['s1'] = {'max_per_day': {'v': 2, 'w': 0}}
        q = solved(self, p)
        ls = core.mapping(q, 'lessons')
        per_day = [sum(1 for e in q['events'] if ls[e['lesson']]['subject'] == 's1' and e['place'][0] == d) for d in range(5)]
        self.assertEqual(per_day, [2, 2, 2, 2, 2])
        p = base(4, 4); p['subject_rules']['s2'] = {'max_per_day': {'v': 1, 'w': 0}}
        p['class_rules']['c2'] = {'allowed': [[0, i] for i in range(P)] + [[1, i] for i in range(P)]}
        self.assertEqual(core.solve(p, 10)['status'], 'infeasible')
        p['lessons'][1]['exempt_subject_limit'] = True
        solved(self, p)

    def test_double_counts_once(self):
        p = base(2, 2); p['lessons'][0]['duration'] = 2; p['events'] = [e for e in p['events'] if e['lesson'] != 'la'][:2] + [dict(id='la0', lesson='la', place=None, locked=False)]
        p['subject_rules']['s1'] = {'max_per_day': {'v': 1, 'w': 0}}
        solved(self, p)

    def test_day_end_after_morning_zone(self):
        p = base(10); add_lesson(p, 'lz', 'pz', ['ta'], [], 1, days=[2])
        p['subject_rules']['pz'] = {'allowed': [[d, 0] for d in range(5)], 'day_end': {'v': 2, 'w': 0}}
        p['subject_rules']['s1'] = {'allowed': [[d, i] for d in range(5) for i in range(1, P)]}
        q = solved(self, p)
        self.assertTrue(all(i <= 2 for i in days_hours(q, 'ta')[2]))

    def test_class_compact(self):
        p = base(4, 4); add_lesson(p, 'lc', 's2', ['tb'], ['c1'], 4)
        p['class_rules']['c1'] = {'allowed': [[d, i] for d in range(5) for i in range(1, 5)], 'compact': {'v': True, 'w': 0}}
        q = solved(self, p)
        ls = core.mapping(q, 'lessons')
        for d in range(5):
            used = sorted(e['place'][1] for e in q['events'] if 'c1' in ls[e['lesson']]['classes'] and e['place'][0] == d)
            self.assertEqual(used, list(range(1, 1 + len(used))))

    def test_avoid_slots_soft(self):
        p = base(2); p['teacher_rules']['ta'] = {'allowed': [[0, 0], [0, 1], [0, 2]], 'avoid': [[0, 0]], 'avoid_w': 5}
        q = solved(self, p)
        self.assertEqual(sorted(days_hours(q, 'ta')[0]), [1, 2])

    def test_swimming_two_classes_one_teacher_fixed_day(self):
        p = base(2, 2); add_lesson(p, 'sw', 's2', ['tb'], ['c1', 'c2'], 2, duration=2, days=[3])
        q = solved(self, p)
        e = next(e for e in q['events'] if e['lesson'] == 'sw')
        self.assertEqual(e['place'][0], 3)

    def test_diagnosis_names_conflicting_rules(self):
        p = base(4); p['teacher_rules']['ta'] = {'max_daily': {'v': 1, 'w': 0}, 'allowed': [[d, i] for d in (0, 1, 2) for i in range(P)]}
        r = core.solve(p, 10)
        self.assertEqual(r['status'], 'infeasible')
        text = ' '.join(r.get('reasons', []))
        self.assertIn('Μέγιστες ώρες ανά ημέρα', text)
        self.assertIn('Διαθεσιμότητα εκπαιδευτικού', text)

    def test_inactive_rule_ignored(self):
        p = base(6); p['teacher_rules']['ta'] = {'max_daily': {'v': 1, 'w': 0, 'on': False}, 'allowed': [[0, i] for i in range(P)]}
        solved(self, p)

    def test_move_not_blocked_by_existing_problem(self):
        p = base(2, 3)
        place = {'la0': [1, 2], 'la1': [2, 3], 'lb0': [0, 1], 'lb1': [0, 2], 'lb2': [3, 1]}
        for e in p['events']: e['place'] = place[e['id']]
        p['subject_rules']['s1'] = {'max_per_day': {'v': 1, 'w': 0}}
        p['subject_rules']['s2'] = {'max_per_day': {'v': 1, 'w': 0}}  # υπάρχουσα παραβίαση: ΦΑ 2 φορές Δευτέρα
        q = core.move_event(p, 'lb2', [4, 4])  # άσχετη μετακίνηση: επιτρέπεται παρά την υπάρχουσα εκκρεμότητα
        self.assertEqual(next(e for e in q['events'] if e['id'] == 'lb2')['place'], [4, 4])
        with self.assertRaises(ValueError): core.move_event(q, 'lb1', [4, 4])  # νέα σύγκρουση εκπαιδευτικού
        with self.assertRaises(ValueError): core.move_event(q, 'la1', [1, 5])  # 2η Γλώσσα την Τρίτη: χειροτερεύει
        q = core.move_event(q, 'lb1', [2, 5])  # διορθώνει την υπάρχουσα παραβίαση
        self.assertEqual(core.validation(q, True), [])

    def test_rule_structure_rejected(self):
        p = base(); p['teacher_rules']['ta'] = {'max_daily': {'v': -1, 'w': 0}}
        with self.assertRaises(ValueError): core.check_structure(p)
        p['teacher_rules']['ta'] = {'unknown': 3}
        with self.assertRaises(ValueError): core.check_structure(p)
        p['teacher_rules']['ta'] = {'day_pattern': {'v': [[5, 4], [4, 4]], 'w': 0}}
        with self.assertRaises(ValueError): core.check_structure(p)

    def test_random_soft_mix_objective_matches(self):
        rnd = random.Random(7)
        for trial in range(4):
            p = base(rnd.randint(5, 9), rnd.randint(4, 8)); add_lesson(p, 'lx', 's1', ['tb'], ['c1'], rnd.randint(2, 4))
            p['teacher_rules']['ta'] = {'presence': {'v': rnd.randint(8, 14), 'w': rnd.randint(1, 5)}, 'max_consecutive': {'v': 2, 'w': rnd.randint(1, 5)},
                                        'avoid': [[d, 0] for d in range(5)], 'avoid_w': rnd.randint(1, 5)}
            p['teacher_rules']['tb'] = {'day_pattern': {'v': [[3, 2]], 'w': rnd.randint(1, 5)}, 'balance': {'v': True, 'w': rnd.randint(1, 5)}, 'min_daily': {'v': 2, 'w': rnd.randint(1, 5)}}
            p['subject_rules']['s1'] = {'max_per_day': {'v': 1, 'w': rnd.randint(1, 5)}}
            p['class_rules']['c1'] = {'allowed': [[d, i] for d in range(5) for i in range(1, 6)], 'compact': {'v': True, 'w': rnd.randint(1, 5)}}
            solved(self, p, 60)

if __name__ == '__main__': unittest.main(verbosity=2)

class Outputs(unittest.TestCase):
    def test_reports_xlsx_xml_with_rules(self):
        import outputs, zipfile, io
        p = base(4, 4); add_lesson(p, 'sw', 's2', ['tb'], ['c1', 'c2'], 2, duration=2, days=[3])
        p['teachers'][0]['color'] = '#00FF00'; p['classes'][0]['teacher'] = 'ta'; p['school'] = 'Σχολείο'; p['year'] = '2026 - 2027'
        p['teacher_rules']['ta'] = {'presence': {'v': 9, 'w': 3, 'on': True}, 'avoid': [[0, 0]], 'avoid_w': 2}
        q = solved(self, p)
        for kind in outputs.LABELS:
            for mode in outputs.MODES:
                for theme in ('color', 'mono'):
                    h = outputs.report(q, dict(kind=kind, mode=mode, theme=theme))
                    self.assertIn('</html>', h)
                z = zipfile.ZipFile(io.BytesIO(outputs.export_xlsx(q, dict(kind=kind, mode=mode))))
                self.assertIsNone(z.testzip())
        z = zipfile.ZipFile(io.BytesIO(outputs.export_xlsx(q)))
        self.assertGreaterEqual(len([n for n in z.namelist() if n.startswith('xl/worksheets/')]), 9)
        back = core.import_xml(outputs.export_xml(q))
        self.assertEqual(back, q)
        self.assertIn('Σχολείο', outputs.report(q, dict(kind='classes', mode='individual')))

class WhyNot(unittest.TestCase):
    def test_slot_reasons(self):
        p = base(2, 1)
        place = {'la0': [0, 1], 'la1': None, 'lb0': [0, 2]}
        for e in p['events']: e['place'] = place[e['id']]
        p['subject_rules']['s1'] = {'max_per_day': {'v': 1, 'w': 0}}
        p['teacher_rules']['ta'] = {'allowed': [[d, i] for d in range(5) for i in range(P) if (d, i) != (2, 4)], 'avoid': [[3, 3]]}
        r = core.slot_status(p, 'la1'); st, why = r['st'], r['why']
        self.assertEqual(st['0,3'], 'no'); self.assertIn('μέγιστο 1', why['0,3'])          # 2η Γλώσσα τη Δευτέρα
        self.assertEqual(st['2,4'], 'no'); self.assertIn('Διαθεσιμότητα', why['2,4'])
        self.assertEqual(st['3,3'], 'maybe'); self.assertEqual(st['1,1'], 'ok')
        p['lessons'][1]['teachers'] = ['ta']; r = core.slot_status(p, 'la1')
        self.assertEqual(r['st']['0,2'], 'busy'); self.assertIn('διδάσκει ήδη', r['why']['0,2'])  # σύγκρουση εκπαιδευτικού προηγείται (λύνεται με ανταλλαγή)


class AscExport(unittest.TestCase):
    def test_roundtrip_through_asc_importer(self):
        import asc
        p = base(4, 2); add_lesson(p, 'sw', 's2', ['tb'], ['c1', 'c2'], 2, duration=2, days=[3])
        p['teachers'][0]['color'] = '#00FF00'; p['classes'][0]['teacher'] = 'ta'
        q = solved(self, p)
        raw = asc.export_asc(q)
        self.assertTrue(raw.startswith(b'<?xml version="1.0" encoding="windows-1253"?>'))
        back = core.import_xml(raw)
        key = lambda pr: sorted((e['lesson'], tuple(e['place'])) for e in pr['events'])
        self.assertEqual(key(back), key(q))
        self.assertEqual(back['teachers'][0]['color'], '#00FF00'); self.assertEqual(back['classes'][0]['teacher'], 'ta')
        self.assertEqual(next(l for l in back['lessons'] if l['id'] == 'sw')['days'], [3])

class Curriculum(unittest.TestCase):
    def test_grade_detection_and_mismatches(self):
        p = base(4, 2)
        p['classes'] = [dict(id='c1', name='Α Τάξη', short='Α'), dict(id='c2', name='ΣΤ2', short='ΣΤ2'), dict(id='c3', name='Ολοήμερο', short='ΟΛ')]
        self.assertEqual([core.grade_of(c) for c in p['classes']], ['Α', 'ΣΤ', ''])
        p['classes'][2]['grade'] = 'Β'; self.assertEqual(core.grade_of(p['classes'][2]), 'Β')
        p['curriculum'] = {'Α': {'s1': 4}, 'ΣΤ': {'s2': 3}}
        core.check_structure(p)
        m = core.curriculum_check(p)
        self.assertNotIn('c1', m)                       # Α: 4 ώρες Γλώσσα, όπως πρέπει
        self.assertIn('2 αντί για 3', m['c2'][0])       # ΣΤ: 2 ώρες ΦΑ αντί 3
        p['curriculum'] = {'Α': {'zz': 3}}
        with self.assertRaises(ValueError): core.check_structure(p)


class Framework(unittest.TestCase):
    def test_required_hours_and_check(self):
        p = base(4, 2)
        ta, tb = p['teachers']
        self.assertIsNone(core.required_hours(p, ta))           # χωρίς έτη: άγνωστο
        ta['years'] = 5; self.assertEqual(core.required_hours(p, ta), 24)
        ta['years'] = 12; self.assertEqual(core.required_hours(p, ta), 23)
        ta['years'] = 25; self.assertEqual(core.required_hours(p, ta), 21)
        ta['role'] = 'deputy'; self.assertEqual(core.required_hours(p, ta), 19)
        p['positions'] = 3; self.assertEqual(core.required_hours(p, ta), 23)   # ολιγοθέσιο 25 − 2
        tb['role'] = 'director'; self.assertEqual(core.required_hours(p, tb), None)
        p['positions'] = 12; self.assertEqual(core.required_hours(p, tb), 6)
        tb['hours_override'] = 4; self.assertEqual(core.required_hours(p, tb), 4)
        p['framework'] = {'teacher_hours': {'deputy_reduction': 3}}
        self.assertEqual(core.required_hours(p, ta), 18)
        core.check_structure(p)
        c = core.teacher_hours_check(p)
        self.assertEqual(c['tb'], {'required': 4, 'assigned': 2, 'text': c['tb']['text']})
        self.assertIn('λείπουν 2', c['tb']['text'])
        for bad in ({'years': -1}, {'role': 'x'}, {'hours_override': 99}):
            q = copy.deepcopy(p); q['teachers'][0].update(bad)
            with self.assertRaises(ValueError): core.check_structure(q)
        q = copy.deepcopy(p); q['framework'] = {'teacher_hours': {'bands': [[10, 5, 20]]}}
        with self.assertRaises(ValueError): core.check_structure(q)

    def test_framework_print_and_excel(self):
        import outputs, zipfile, io
        p = base(4, 2); p['classes'][0]['grade'] = 'Α'; p['curriculum'] = {'Α': {'s1': 5}}
        p['framework'] = {'curriculum_source': 'ΦΕΚ δοκιμής 123'}; p['teachers'][0]['years'] = 3
        pages = outputs.pages(p, {'kind': 'teachers', 'mode': 'framework'})
        self.assertEqual(len(pages), 4)
        html = outputs.report(p, {'kind': 'teachers', 'mode': 'framework'})
        self.assertIn('ΦΕΚ δοκιμής 123', html); self.assertIn('Υποχρεωτικ', html)
        z = zipfile.ZipFile(io.BytesIO(outputs.export_xlsx(p, {'kind': 'teachers', 'mode': 'framework'})))
        self.assertTrue(any(n.startswith('xl/worksheets/') for n in z.namelist()))
