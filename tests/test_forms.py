"""Βοηθητικά εργαλεία (admin.py) και Έντυπα Διεύθυνσης (forms.py)."""
import unittest, sys, json, copy, io, sqlite3, tempfile, zipfile
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
import core, admin, forms
import openpyxl   # από το src/vendor (το φορτώνει το forms)

DEMO = json.loads((SRC / 'demo_school.json').read_text(encoding='utf-8'))


def school():
    p = core.check_structure(copy.deepcopy(DEMO))
    for i, t in enumerate(p['teachers']):
        t['years'] = 5 + i
    p['teachers'][-1]['role'] = 'director'; p['positions'] = 12; p['school'] = 'Δοκιμαστικό Δημοτικό Σχολείο'
    return p


def by_name(p, n):
    return next(t for t in p['teachers'] if t['name'] == n)


class Admin(unittest.TestCase):
    def test_validate(self):
        p = school()
        p['admin'] = {'edy': 1, 'library': {'teacher': p['teachers'][0]['id'], 'hours': 3}, 'city': 'ΠΟΛΗ',
                      'teachers': {p['teachers'][1]['id']: {'duty': 2, 'extras': [{'kind': 'ενισχυτική', 'hours': 2}]}}}
        core.check_structure(p)
        for bad in ({'edy': 99}, {'library': {'teacher': 'zzz', 'hours': 3}}, {'teachers': {'zzz': {}}},
                    {'teachers': {p['teachers'][0]['id']: {'duty': 7}}}, {'teachers': {p['teachers'][0]['id']: {'extras': [{'kind': 'x', 'hours': 1}]}}},
                    {'students': {p['classes'][0]['id']: -1}}, {'needs': {'hours': {'ΠΕ70': [1, 2]}}}, {'allday': {'sections': [{'class': 'zzz'}]}}):
            q = copy.deepcopy(p); q['admin'] = bad
            with self.assertRaises(ValueError, msg=str(bad)):
                core.check_structure(q)

    def test_klados(self):
        self.assertEqual(admin.klados_code('ΠΕ 86'), 'ΠΕ86')
        self.assertEqual(admin.klados_code('ΠΕ19-20'), 'ΠΕ86')
        self.assertEqual(admin.klados_code('pe70'), 'ΠΕ70')
        self.assertEqual(admin.klados_code('ΠΕ16'), 'ΠΕ79.01')
        self.assertEqual(admin.klados_code('ΠΕ79.01'), 'ΠΕ79.01')
        self.assertEqual(admin.klados_code('ΠΕ32'), 'ΠΕ91.01')
        self.assertEqual(admin.subject_klados('Φ ΑΓΩΓΗ'), 'ΠΕ11')
        self.assertEqual(admin.subject_klados('Φυσικά'), '')

    def test_teacher_rows(self):
        p = school(); d = by_name(p, 'Παππά Θεοδώρα')
        p['admin'] = {'library': {'teacher': d['id'], 'hours': 3}, 'teachers': {p['teachers'][1]['id']: {'duty': 4, 'extras': [{'kind': 'παράλληλη', 'hours': 2}]}}}
        rows = admin.teacher_rows(p)
        self.assertEqual(rows[0]['name'], 'Παππά Θεοδώρα')            # διευθυντής πρώτος
        self.assertEqual((rows[0]['edy'], rows[0]['library']), (1, 3))  # Ε.Δ.Υ. πάντα στον διευθυντή
        self.assertEqual([r['homeroom'] for r in rows[1:7]], ['Α', 'Β', 'Γ', 'Δ', 'Ε', 'Στ'])
        b = next(r for r in rows if r['id'] == p['teachers'][1]['id'])
        self.assertEqual(b['duty'], 'Παρασκευή'); self.assertEqual(b['extra'], 2); self.assertIn('2 παράλληλη', b['notes'])
        # όλες οι ώρες αναθέσεων σε τμήματα τάξεων μετρούν μία φορά
        gids = {c['id'] for c in admin.grade_classes(p)}
        total = sum(l['hours'] for l in p['lessons'] for _ in l['teachers'] if any(c in gids for c in l['classes']))
        self.assertEqual(sum(sum(r['by_class'].values()) for r in rows), total)

    def test_sections_and_allday(self):
        p = school(); m = admin.allday_matrix(p)
        self.assertEqual([s['kind'] for s in m['sections']], ['allday', 'allday', 'allday', 'morning'])
        self.assertEqual(m['periods'], [7, 8, 9])
        hours = sum(h for per in m['hours'].values() for h in per.values())
        secs = {s['class'] for s in m['sections']}
        self.assertEqual(hours, sum(l['hours'] * len(l['teachers']) for l in p['lessons'] if any(c in secs for c in l['classes'])))

    def test_needs(self):
        p = school(); n = admin.needs(p)
        r = {x['code']: x for x in n['rows']}
        self.assertEqual(r['ΠΕ11']['required'], 3 + 3 + 3 + 3 + 2 + 2)
        self.assertEqual(r['ΠΕ70']['required'], sum(admin.NEEDS_HOURS['ΠΕ70']) + sum(n['extra'][k] for k in ('morning', 'meal', 'study', 'library')))
        for x in n['rows']:
            self.assertEqual(x['balance'], x['available'] - x['required'])
        # σενάριο: δύο τμήματα Ε΄
        p['admin'] = {'needs': {'sections': {'Ε': 2}}}
        self.assertEqual({x['code']: x for x in admin.needs(p)['rows']}['ΠΕ70']['required'], r['ΠΕ70']['required'] + 20)
        # παλιά αρχεία με «ώρες σε άλλο σχολείο»: αγνοούνται (διαθέσιμο = υποχρεωτικό ωράριο στο σχολείο)
        t = by_name(p, 'Ιωάννου Παναγιώτης'); p['admin']['teachers'] = {t['id']: {'other': 5}}
        self.assertEqual({x['code']: x for x in admin.needs(p)['rows']}['ΠΕ11']['available'], r['ΠΕ11']['available'])

    def test_counted_hours(self):
        """Ε.Δ.Υ. και βιβλιοθήκη μετρούν στο ωράριο (δεν βγαίνει «λείπουν ώρες»)."""
        p = school(); d = by_name(p, 'Παππά Θεοδώρα'); o = p['teachers'][0]
        p['admin'] = {'edy': 0}; base = core.teacher_hours_check(p)
        p['admin'] = {'library': {'teacher': o['id'], 'hours': 3}}   # Ε.Δ.Υ. προεπιλογή 1
        c = core.teacher_hours_check(p)
        self.assertEqual(c[d['id']]['assigned'], base[d['id']]['assigned'] + 1)
        self.assertEqual(c[o['id']]['assigned'], base[o['id']]['assigned'] + 3)
        self.assertIn('βιβλιοθήκη', c[o['id']]['extra'])
        p['framework'] = dict(p.get('framework') or {}, level='Γυμνάσιο')
        self.assertEqual(admin.counted_hours(p)[o['id']][0], 3)
        self.assertNotIn(d['id'], admin.counted_hours(p))

    def test_efimeries(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'efimeries_2026-2027.db'; con = sqlite3.connect(db)
            con.executescript("CREATE TABLE teachers(id INTEGER PRIMARY KEY, name TEXT, primary_day INTEGER DEFAULT -1);"
                              "CREATE TABLE assignments(id INTEGER PRIMARY KEY, d TEXT, teacher_id INTEGER, mode TEXT);"
                              "INSERT INTO teachers VALUES(1,'ΑΛΕΞΙΟΥ ΜΑΡΙΑ',2),(2,'Βασιλείου Ευτυχία',-1),(3,'Άγνωστος Κάποιος',1);"
                              "INSERT INTO assignments(d,teacher_id,mode) VALUES('2026-11-06',2,'daily'),('2026-11-13',2,'daily'),('2026-11-10',2,'daily');")
            con.commit(); con.close()
            found = admin.efimeries_days(db)
            self.assertEqual({f['name']: f['day'] for f in found}, {'ΑΛΕΞΙΟΥ ΜΑΡΙΑ': 2, 'Βασιλείου Ευτυχία': 4, 'Άγνωστος Κάποιος': 1})
            m = {x['name']: x['teacher_name'] for x in admin.match_names(school(), found)}
            self.assertEqual(m['ΑΛΕΞΙΟΥ ΜΑΡΙΑ'], 'Αλεξίου Μαρία'); self.assertEqual(m['Άγνωστος Κάποιος'], '')


class Forms(unittest.TestCase):
    def test_templates_clean(self):
        for f in ('op.xlsx', 'oloimero.xlsx'):
            z = zipfile.ZipFile(SRC / 'forms' / f)
            self.assertNotIn('xl/embeddings/oleObject1.bin', z.namelist())
            core_xml = z.read('docProps/core.xml').decode('utf-8')
            self.assertIn('Ωρολόγιο Σχολείου', core_xml)
        ws = openpyxl.load_workbook(SRC / 'forms' / 'op.xlsx').worksheets[0]
        self.assertTrue(all(ws.cell(r, 2).value is None for r in range(9, 25)))

    def test_op(self):
        p = school(); p['admin'] = {'city': 'ΠΟΛΗ', 'date': '1/10/2026', 'directorate': 'ΔΙΕΥΘΥΝΣΗ ΔΟΚΙΜΗΣ'}
        data, warn = forms.export_op(p)
        wb = openpyxl.load_workbook(io.BytesIO(data)); ws = wb.worksheets[0]
        rows = admin.teacher_rows(p); n = len(rows)
        self.assertEqual([ws.cell(9 + i, 2).value for i in range(n)], [r['name'] for r in rows])
        self.assertEqual(ws.cell(9, 18).value, '=SUM(I9:Q9)')
        self.assertEqual(ws.cell(9 + n, 1).value, 'Γ Ε Ν Ι Κ Ο  Σ Υ Ν Ο Λ Ο')
        self.assertEqual(ws.cell(9 + n, 8).value, '=SUM(H9:H%d)' % (8 + n))
        self.assertEqual(ws['I7'].value, 'Α')
        cls = wb.worksheets[1]
        self.assertEqual(cls['B4'].value, 'ΔΙΕΥΘΥΝΣΗ ΔΟΚΙΜΗΣ'); self.assertEqual(cls['H7'].value, 'Α')
        # Γλώσσα Α΄: ώρες της στήλης = ώρες αναθέσεων Γλώσσας στην Α΄
        A = admin.grade_classes(p)[0]; S = core.mapping(p, 'subjects')
        want = sum(l['hours'] for l in p['lessons'] if A['id'] in l['classes'] and 'ΓΛΩΣΣ' in admin.norm(S[l['subject']]['name']))
        self.assertEqual(cls['J10'].value, want)
        self.assertEqual(cls['J26'].value, '=SUM(J9:J25)')
        self.assertTrue(any('Νηπιαγωγείο' not in w for w in warn) or warn == [])

    def test_many_classes(self):
        """12 τμήματα: ώρες ανά τάξη (όχι ανά τμήμα) και 4 μπλοκ στο ωρολόγιο ανά τάξη."""
        p = school(); C = list(p['classes'])
        extra = []
        for c in admin.grade_classes(p):
            nc = dict(c, id=c['id'] + 'X', name=c['name'] + ' 2', short=(c.get('short') or c['name']) + '2'); nc.pop('teacher', None); extra.append(nc)
        p['classes'] = C + extra
        data, warn = forms.export_op(p)
        wb = openpyxl.load_workbook(io.BytesIO(data))
        self.assertEqual([wb.worksheets[0].cell(7, 9 + k).value for k in range(6)], ['Α', 'Β', 'Γ', 'Δ', 'Ε', 'ΣΤ'])
        self.assertEqual(wb.worksheets[1].cell(7 + 22 * 3 + 2, 2).value, 'Θρησκευτικά')

    def test_allday(self):
        p = school()
        secs = admin.sections(p)
        p['admin'] = {'allday': {'responsible': p['teachers'][0]['id'], 'sections': [dict(s, grades=g) for s, g in zip(secs, ['Α - Β', 'Γ - Δ', 'Ε - ΣΤ', 'Α - Β - Γ'])]}}
        for s in p['admin']['allday']['sections']:
            s.pop('name', None)
        data, warn = forms.export_allday(p)
        wb = openpyxl.load_workbook(io.BytesIO(data)); pr = wb['ΠΡΟΓΡΑΜΜΑ']; hrs = wb['ΩΡΑΡΙΟ ΕΚΠ']
        self.assertEqual(pr['F13'].value, admin.upper(p['teachers'][0]['name']))
        texts = [pr.cell(r, c).value for r in range(14, 40) for c in range(1, 11)]
        self.assertIn('1η ώρα', texts); self.assertIn('Γ - Δ', texts); self.assertIn('ΜΕΛ/ΠΡΟΕΤΟΙΜΑΣΙΑ', texts)
        self.assertEqual([hrs.cell(9 + i, 3).value for i in range(4)], ['Α - Β', 'Γ - Δ', 'Ε - ΣΤ', 'Α - Β - Γ'])
        m = admin.allday_matrix(p)
        total = sum(h for per in m['hours'].values() for h in per.values())
        got = sum(v for r in range(9, 30) for c in range(8, 19) for v in [hrs.cell(r, c).value] if isinstance(v, int))
        self.assertEqual(got, total)
        self.assertFalse([w for w in warn if 'τάξεις' in w])



class Prints(unittest.TestCase):
    def test_poster_band_and_extra_table(self):
        import outputs
        p = school()
        pg = outputs.pages(p, {'kind': 'teachers', 'mode': 'poster'})[0]
        self.assertEqual(pg['periods'], [1, 2, 3, 4, 5, 6]); self.assertEqual(pg['extra'], [0, 7, 8, 9])
        h = outputs.report(p, {'kind': 'teachers', 'mode': 'poster', 'title': 'ΛΩΡΙΔΑ ΔΟΚΙΜΗΣ'})
        self.assertIn('ΛΩΡΙΔΑ ΔΟΚΙΜΗΣ - Αφίσα', h); self.assertEqual(h.count('<table class="matrix'), 2)
        self.assertIn('Πρωινή Ζώνη / Ολοήμερο', h)
        wb = openpyxl.load_workbook(io.BytesIO(outputs.export_xlsx(p, {'kind': 'classes', 'mode': 'overview', 'title': 'ΛΩΡΙΔΑ'})))
        vals = [c.value for row in wb.worksheets[0].iter_rows() for c in row]
        self.assertTrue(any(isinstance(v, str) and 'ΛΩΡΙΔΑ - Συνολικό' in v for v in vals)); self.assertIn('Πρωινή Ζώνη / Ολοήμερο', vals)

    def test_needs_print(self):
        import outputs
        p = school(); pg = outputs.pages(p, {'mode': 'needs'})[0]
        self.assertEqual(pg['rows'][-1][0], 'Σύνολο')
        self.assertIn('Προϋπολογισμός', outputs.report(p, {'mode': 'needs'}))
        outputs.export_xlsx(p, {'mode': 'needs'})


if __name__ == '__main__':
    unittest.main()
