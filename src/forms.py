"""«Έντυπα Διεύθυνσης»: συμπλήρωση των προτύπων Excel (src/forms) με τη μορφή που ζητά η Διεύθυνση.

Τα πρότυπα κρατούν μορφοποίηση, πλάτη, συγχωνεύσεις και σελιδοποίηση των εντύπων. Οι γραμμές
δεδομένων «σφραγίζονται» από γραμμές-υποδείγματα του προτύπου (ίδια στυλ), όσες χρειάζονται.
"""
import io, sys
from copy import copy
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE / 'vendor') not in sys.path:
    sys.path.insert(0, str(HERE / 'vendor'))
import openpyxl  # noqa: E402
from openpyxl.formatting.rule import CellIsRule  # noqa: E402
from openpyxl.styles import Font  # noqa: E402
from openpyxl.utils import get_column_letter as L  # noqa: E402

import core, admin  # noqa: E402

FORMS = HERE / 'forms'
DAYS_UP = ['ΔΕΥΤΕΡΑ', 'ΤΡΙΤΗ', 'ΤΕΤΑΡΤΗ', 'ΠΕΜΠΤΗ', 'ΠΑΡΑΣΚΕΥΗ']


# ------------------------------------------------------------------ βοηθητικά
class Proto:
    """Αποτύπωση μιας γραμμής του προτύπου (στυλ + τιμές + ύψος)."""
    def __init__(self, ws, r, maxcol=None):
        self.h = ws.row_dimensions[r].height
        self.cells = {}
        for c in range(1, (maxcol or ws.max_column) + 1):
            cell = ws.cell(r, c)
            self.cells[c] = (copy(cell._style), cell.value if type(cell).__name__ != 'MergedCell' else None)


def stamp(ws, proto, r, values=None, keep=False):
    """Γράφει τη γραμμή r με τα στυλ του υποδείγματος και τις τιμές values {στήλη: τιμή}."""
    values = values or {}
    for c, (st, v) in proto.cells.items():
        cell = ws.cell(r, c)
        cell._style = copy(st)
        cell.value = values.get(c, v if keep else None)
    for c, v in values.items():
        if c not in proto.cells:
            ws.cell(r, c).value = v
    ws.row_dimensions[r].height = proto.h


def cut(ws, start):
    """Σβήνει ό,τι υπάρχει από τη γραμμή start και κάτω (τιμές, στυλ, συγχωνεύσεις, ύψη)."""
    for m in list(ws.merged_cells.ranges):
        if m.max_row >= start:
            ws.merged_cells.remove(m)
    if ws.max_row >= start:
        ws.delete_rows(start, ws.max_row - start + 1)
    for r in list(ws.row_dimensions):
        if r >= start:
            del ws.row_dimensions[r]


def merge(ws, r1, c1, r2, c2):
    if (r1, c1) != (r2, c2):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


def nz(v):
    return v if v else None


def surname(name):
    w = (name or '').split()
    return admin.upper(w[0]) if w else ''


def period_label(p, i):
    n = str(p['periods'][i].get('name', i))
    return n + 'η' if n.isdigit() else n


def hhmm(s):
    return s.replace(':', '.')


def save(wb):
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def header_texts(p):
    a = admin.get(p)
    return a, a['region'] or 'ΠΕΡΙΦΕΡΕΙΑΚΗ Δ/ΝΣΗ Α/ΘΜΙΑΣ & Β/ΘΜΙΑΣ ΕΚΠ/ΣΗΣ …', a['directorate'] or 'ΔΙΕΥΘΥΝΣΗ Α/ΘΜΙΑΣ ΕΚΠΑΙΔΕΥΣΗΣ …'


def year_tail(p):
    y = ''.join(ch for ch in (p.get('year') or '') if ch.isdigit())
    return y[:4] if len(y) >= 4 else '20…'


def signature_names(names):
    names = sorted(names, key=admin.norm)
    h = (len(names) + 1) // 2
    return names[:h], names[h:]


# ------------------------------------------------------------------ Αρχείο 1: Ω.Π. και διδακτικό ωράριο
def class_columns(p):
    """Στήλες «ΤΑΞΕΙΣ - ΤΜΗΜΑΤΑ» (έως 9): ένα τμήμα ανά στήλη, αλλιώς ανά τάξη."""
    gcs = admin.grade_classes(p)
    if len(gcs) <= 9:
        return [(c.get('short') or c['name'], [c['id']]) for c in gcs]
    by = {}
    for c in gcs:
        by.setdefault(core.grade_of(c), []).append(c['id'])
    return list(by.items())[:9]


def sheet_orario(p, ws, rows, warn):
    a, _, _ = header_texts(p)
    pr_first, pr = Proto(ws, 9, 34), Proto(ws, 10, 34)
    pr_tot, pr_sp = Proto(ws, 25, 34), Proto(ws, 26, 34)
    pr_foot = [Proto(ws, r, 34) for r in range(27, 36)]
    cols = class_columns(p)
    for k in range(9):
        ws.cell(7, 9 + k).value = cols[k][0] if k < len(cols) else None
    cut(ws, 9)
    r = 9
    for i, row in enumerate(rows):
        v = {1: i + 1, 2: row['name'], 3: row['title'], 4: row['duty'] or None, 5: row['homeroom'] or None, 6: row['students'],
             7: row['years'], 8: row['required']}
        for k, (_, ids) in enumerate(cols):
            v[9 + k] = nz(sum(row['by_class'].get(c, 0) for c in ids))
        director = row['t'].get('role') == 'director'
        v.update({18: '=SUM(I%d:Q%d)' % (r, r), 19: nz(row['allday']), 20: nz(row['other']), 21: nz(row['library']), 22: nz(row['edy']),
                  23: ('=SUM(R%d:V%d)' if director or row['edy'] else '=SUM(R%d:U%d)') % (r, r), 24: '=H%d-W%d' % (r, r),
                  25: nz(row['extra']), 26: row['notes'] or None})
        if row['required'] is None:
            warn.append(row['name'] + ': δεν υπολογίζεται υποχρεωτικό ωράριο (' + ('ορίστε την οργανικότητα του σχολείου στο Θεσμικό πλαίσιο' if row['t'].get('role') == 'director' and row['years'] is not None else 'λείπουν τα έτη υπηρεσίας') + ').')
        stamp(ws, pr_first if i == 0 else pr, r, v); r += 1
    last = max(r - 1, 9)
    tot = {1: 'Γ Ε Ν Ι Κ Ο  Σ Υ Ν Ο Λ Ο', 6: '=SUM(F9:F%d)' % last}
    for c in range(8, 26):
        tot[c] = '=SUM(%s9:%s%d)' % (L(c), L(c), last)
    stamp(ws, pr_tot, r, tot); merge(ws, r, 1, r, 4)
    ws.conditional_formatting.add('X9:X%d' % last, CellIsRule(operator='lessThan', formula=['0'], font=Font(color='FFC00000', bold=True)))
    stamp(ws, pr_sp, r + 1)
    f = r + 2
    city = a['city'] or '…………'
    sig = [x['name'] for x in rows if x['t'].get('role') != 'director']
    left, right = signature_names(sig)
    director = next((x['name'] for x in rows if x['t'].get('role') == 'director'), '')
    n = max(len(left) + 1, 6)
    for k in range(n):
        stamp(ws, pr_foot[min(k, len(pr_foot) - 1)], f + k)
    ws.cell(f, 2).value = city + ' …… / …… / ' + year_tail(p)
    ws.cell(f, 7).value = 'Το Εκπαιδευτικό Προσωπικό'; merge(ws, f, 7, f, 17)
    ws.cell(f, 25).value = city + (', ' + a['date'] if a['date'] else ', …… / …… / ' + year_tail(p))
    ws.cell(f + 1, 2).value = 'Θεωρήθηκε'
    ws.cell(f + 2, 2).value = a['approver']
    ws.cell(f + 2, 25).value = a['director_title']
    ws.cell(f + 5, 25).value = admin.upper(director) if director else None
    for k, nm in enumerate(left):
        ws.cell(f + 1 + k, 7).value = nm
    for k, nm in enumerate(right):
        ws.cell(f + 1 + k, 14).value = nm
    ws.print_area = 'A1:Z%d' % (f + n)


SUBJ_ROWS = [  # (γραμμή μέσα στο μπλοκ, κανονικοποιημένο κλειδί αντιστοίχισης)
    (2, 'ΘΡΗΣΚ'), (3, 'ΓΛΩΣΣ'), (4, 'ΜΑΘΗΜ'), (5, 'ΙΣΤΟΡ'), (6, 'ΜΕΛΕΤ'), (7, 'ΓΕΩΓΡ'), (8, 'ΦΥΣΙΚΑ'), (9, 'ΚΟΙΝ'),
    (10, 'ΕΙΚΑΣΤ'), (11, 'ΜΟΥΣ'), (12, 'ΘΕΑΤΡ'), (13, 'ΦΥΣΑΓ'), (14, 'ΑΓΓΛ'), (15, 'ΓΕΡΜ'), (16, 'ΓΑΛΛ'), (17, 'ΤΠΕ'), (18, 'ΕΡΓΑΣΤ')]


def subject_row(name):
    n = admin.norm(name)
    if admin.subject_klados(name) == 'ΠΕ11': return 13
    if admin.subject_klados(name) == 'ΠΕ86': return 17
    if 'ΦΥΣΙΚ' in n or 'ΦΥΣΙΚΗ' in n: return 8
    if 'ΚΟΙΝ' in n or 'ΠΟΛΙΤ' in n: return 9
    for off, key in SUBJ_ROWS:
        if key in n:
            return off
    return None


def sheet_classes(p, ws, warn):
    a, region, direc = header_texts(p)
    ws['B2'] = a['ministry']; ws['B3'] = region; ws['B4'] = direc; ws['B5'] = a['school_form']
    ws['Q4'] = 'Σχολικό έτος: ' + (p.get('year') or '')
    gcs = admin.grade_classes(p)
    protos = [Proto(ws, r, 22) for r in range(29, 51)]   # μπλοκ 2 (γραμμές 29–48) + 2 κενές
    merges0 = [m for m in ws.merged_cells.ranges if 29 <= m.min_row <= 48]
    S = core.mapping(p, 'subjects'); L_ = core.mapping(p, 'lessons')
    nblocks = max(2, (len(gcs) + 2) // 3)
    if nblocks > 2:
        for b in range(2, nblocks):
            top = 7 + 22 * b
            for k, pr in enumerate(protos):
                stamp(ws, pr, top + k, keep=True)
            for m in merges0:
                merge(ws, m.min_row + 22 * (b - 1), m.min_col, m.max_row + 22 * (b - 1), m.max_col)
    for b in range(nblocks):
        top = 7 + 22 * b
        for k in range(3):
            ci = 3 * b + k; base = 5 + 6 * k
            c = gcs[ci] if ci < len(gcs) else None
            ws.cell(top, base + 3).value = (c.get('short') or c['name']) if c else None
            for off in range(2, 20):
                for d in range(6):
                    ws.cell(top + off, base + d).value = None
            if not c:
                continue
            per = {}
            daycount = [set() for _ in range(5)]
            for e in p['events']:
                l = L_[e['lesson']]
                if c['id'] not in l['classes'] or not e['place']:
                    continue
                d, i = e['place']
                for j in range(i, i + l['duration']):
                    daycount[d].add(j)
                    sname = S[l['subject']]['name'] if l['subject'] in S else ''
                    off = subject_row(sname)
                    if off is None:
                        msg = 'Το μάθημα «' + sname + '» (' + (c.get('short') or c['name']) + ') δεν έχει γραμμή στο έντυπο «Ωρολόγιο ανά τάξη».'
                        if msg not in warn: warn.append(msg)
                        continue
                    per.setdefault(off, [set() for _ in range(5)])[d].add(j)
            for off, days in per.items():
                for d in range(5):
                    if days[d]:
                        ws.cell(top + off, base + d).value = '-'.join(period_label(p, j) for j in sorted(days[d]))
                ws.cell(top + off, base + 5).value = sum(len(x) for x in days)
            for d in range(5):
                ws.cell(top + 19, base + d).value = len(daycount[d]) or None
            col = L(base + 5)
            ws.cell(top + 19, base + 5).value = '=SUM(%s%d:%s%d)' % (col, top + 2, col, top + 18)
    ws.print_area = 'A1:V%d' % (7 + 22 * nblocks - 3)


def export_op(p):
    """Αρχείο «Ω.Π. και διδακτικό ωράριο εκπαιδευτικών» (2 φύλλα). Επιστρέφει (bytes, προειδοποιήσεις)."""
    core.check_structure(p)
    wb = openpyxl.load_workbook(FORMS / 'op.xlsx'); warn = []
    rows = admin.teacher_rows(p)
    sheet_orario(p, wb.worksheets[0], rows, warn)
    sheet_classes(p, wb.worksheets[1], warn)
    return save(wb), warn


# ------------------------------------------------------------------ Αρχείο 2: Ολοήμερο
def names_at(m, si, d, j, T, short=False):
    out = []
    for tids, _ in m['cells'].get((si, d, j), []):
        for t in tids:
            nm = surname(T[t]['name']) if short else admin.upper(T[t]['name'])
            if t in T and nm not in out:
                out.append(nm)
    return out


def sheet_allday_program(p, ws, m, warn):
    a, region, direc = header_texts(p); ad = a['allday']
    ws['A5'] = a['ministry']; ws['A6'] = region; ws['A7'] = direc; ws['A8'] = a['school_form']
    ws['I8'] = 'Σχολ. Έτος:'; ws['J8'] = p.get('year') or ''
    T = m['T']; secs = m['sections']; per = m['periods']
    pr_tr, pr_meal, pr_brk = Proto(ws, 14, 10), Proto(ws, 15, 10), Proto(ws, 16, 10)
    pr_s1 = [Proto(ws, r, 10) for r in (17, 18, 19)]; pr_s2 = [Proto(ws, r, 10) for r in (20, 21, 22)]
    pr_st = [Proto(ws, r, 10) for r in (33, 34, 35, 36)]
    resp = ad.get('responsible')
    for d in range(5):
        ws.cell(13, 6 + d).value = admin.upper(T[resp]['name']) if resp in T else None
    cut(ws, 14)
    r = 14
    if not per:
        warn.append('Δεν βρέθηκαν ώρες Ολοήμερου στο πρόγραμμα (τμήματα όπως «ΟΛ1»).')
    P = p['periods']
    meal = per[0] if per and ad.get('meal', True) is not False else None
    if meal is not None and meal > 0:
        prev_end, start = P[meal - 1]['end'], P[meal]['start']
        if core.minutes(prev_end) < core.minutes(start):
            stamp(ws, pr_tr, r, {2: hhmm(prev_end) + '-' + hhmm(start), 6: 'Χρόνος μετάβασης στην αίθουσα σίτισης'}); merge(ws, r, 6, r, 10); r += 1
    hour_no = 0; prev = None
    for j in per:
        if prev is not None and core.minutes(P[prev]['end']) < core.minutes(P[j]['start']):
            stamp(ws, pr_brk, r, {2: hhmm(P[prev]['end']) + '-' + hhmm(P[j]['start']), 6: 'Διάλειμμα'}); merge(ws, r, 6, r, 10); r += 1
        prev = j; hour_no += 1
        time = hhmm(P[j]['start']) + '-' + hhmm(P[j]['end'])
        if j == meal:
            v = {1: '%dη ώρα' % hour_no, 2: time, 4: ad.get('meal_text') or 'Διατροφική Αγωγή - Όλα τα τμήματα'}
            for d in range(5):
                nm = []
                for si, s in enumerate(secs):
                    if s['kind'] == 'allday':
                        nm += [x for x in names_at(m, si, d, j, T, True) if x not in nm]
                v[6 + d] = ' / '.join(nm) or None
            stamp(ws, pr_meal, r, v); merge(ws, r, 4, r, 5); r += 1
            continue
        act = [si for si, s in enumerate(secs) if s['kind'] == 'allday' and any((si, d, j) in m['cells'] for d in range(5))]
        if not act:
            continue
        r0 = r
        for n, si in enumerate(act):
            s = secs[si]; pr3 = pr_s1 if n == 0 else pr_s2
            num = sum(1 for x in secs[:si + 1] if x['kind'] == 'allday')
            grades = (s.get('by_period') or {}).get(str(j)) or s.get('grades') or ''
            subj = s.get('subject') or 'ΜΕΛ/ΠΡΟΕΤΟΙΜΑΣΙΑ'
            rows = [{4: 'Τάξεις'}, {4: 'Διδάσκων'}, {4: 'Διδακτικό αντικείμενο'}]
            rows[0][3] = '%dο τμήμα' % num
            for d in range(5):
                if (si, d, j) in m['cells']:
                    rows[0][6 + d] = grades or None
                    rows[1][6 + d] = ' / '.join(names_at(m, si, d, j, T)) or None
                    rows[2][6 + d] = subj
            for k in range(3):
                stamp(ws, pr3[k], r + k, rows[k]); merge(ws, r + k, 4, r + k, 5)
            merge(ws, r, 3, r + 2, 3); r += 3
        ws.cell(r0, 1).value = '%dη ώρα' % hour_no; ws.cell(r0, 2).value = time
        merge(ws, r0, 1, r - 1, 1); merge(ws, r0, 2, r - 1, 2)
    # Πίνακας μαθητών
    srows = ad.get('student_rows') or [{'label': '1η & 2η ώρα', 'counts': {}}, {'label': '3η ώρα', 'counts': {}}]
    enrolled = ad.get('enrolled') or {}
    stamp(ws, pr_st[0], r, {1: 'Αριθμός μαθητών ανα τάξη και ώρα', 4: 'Α', 5: 'Β', 6: 'Γ', 7: 'Δ', 8: 'Ε', 9: 'ΣΤ', 10: 'ΣΥΝΟΛΟ'})
    top = r; r += 1
    for k, sr in enumerate(srows):
        v = {3: sr.get('label', '')}
        for g, gr in enumerate(admin.GRADES6):
            v[4 + g] = (sr.get('counts') or {}).get(gr)
        v[10] = '=SUM(D%d:I%d)' % (r, r)
        stamp(ws, pr_st[1 if k == 0 else 2], r, v); r += 1
    merge(ws, top, 1, r - 1, 2)
    v = {1: 'ΣΥΝΟΛΟ ΕΓΓΕΓΡΑΜΜΕΝΩΝ', 10: '=SUM(D%d:I%d)' % (r, r)}
    for g, gr in enumerate(admin.GRADES6):
        v[4 + g] = enrolled.get(gr)
    stamp(ws, pr_st[3], r, v); merge(ws, r, 1, r, 3)
    ws.print_area = 'A1:J%d' % r


def sheet_allday_hours(p, ws, m, warn):
    a, _, _ = header_texts(p)
    T = m['T']; secs = m['sections']
    pr_first, pr, pr_right = Proto(ws, 9, 24), Proto(ws, 10, 24), Proto(ws, 17, 24)
    pr_tot, pr_sp = Proto(ws, 20, 24), Proto(ws, 21, 24)
    pr_foot = [Proto(ws, r, 24) for r in range(22, 29)]
    if len(secs) > 11:
        warn.append('Το έντυπο Ολοήμερου έχει θέση για 11 τμήματα· τα υπόλοιπα δεν εμφανίζονται.')
    rows = []
    kl = {r['id']: r['klados'] for r in admin.teacher_rows(p)}
    for tid, hs in m['hours'].items():
        if tid not in T or not sum(hs.values()):
            continue
        kinds = {secs[si]['kind'] for si in hs}
        note = '/'.join((['ΣΙΤΙΣΗ-ΜΕΛΕΤΗ/ΠΡΟΕΤ'] if 'allday' in kinds else []) + (['ΠΡΩΙΝΗ ΖΩΝΗ'] if 'morning' in kinds else []))
        rows.append({'id': tid, 'name': admin.upper(T[tid]['name']), 'kl': kl.get(tid, ''), 'hours': hs, 'note': note,
                     'key': (min(hs), -sum(hs.values()), admin.norm(T[tid]['name']))})
    rows.sort(key=lambda x: x['key'])
    cut(ws, 9)
    nleft = len(secs) + 2; n = max(len(rows) + 1, nleft)
    for i in range(n):
        v = {}
        if i < len(secs):
            s = secs[i]
            v.update({1: i + 1, 2: s['label'], 3: s.get('grades') or None})
        if i < len(rows):
            x = rows[i]
            v.update({5: i + 1, 6: x['name'], 7: x['kl'] or None, 20: x['note']})
            for si, h in x['hours'].items():
                if si < 11:
                    v[8 + si] = h
        v[19] = '=SUM(H%d:R%d)' % (9 + i, 9 + i)
        stamp(ws, pr_first if i == 0 else (pr if i < nleft else pr_right), 9 + i, v)
        merge(ws, 9 + i, 20, 9 + i, 24)
    r = 9 + n
    tot = {5: 'Σ  Υ  Ν  Ο  Λ  Ο'}
    for c in range(8, 20):
        tot[c] = '=SUM(%s9:%s%d)' % (L(c), L(c), r - 1)
    stamp(ws, pr_tot, r, tot); merge(ws, r, 5, r, 7); merge(ws, r, 20, r, 24)
    stamp(ws, pr_sp, r + 1)
    f = r + 2
    city = a['city'] or '…………'
    names = [T[x['id']]['name'] for x in rows if T[x['id']].get('role') != 'director']
    left, right = signature_names(names)
    director = next((t['name'] for t in p['teachers'] if t.get('role') == 'director'), '')
    k_rows = max(len(left) + 2, 6)
    for k in range(k_rows):
        stamp(ws, pr_foot[min(k, len(pr_foot) - 1)], f + k)
    merge(ws, f, 2, f, 4); merge(ws, f + 1, 2, f + 1, 3); merge(ws, f + 2, 2, f + 2, 3)
    ws.cell(f, 2).value = city + '   ….... / …..... /' + year_tail(p)
    ws.cell(f, 20).value = admin.upper(city) + (', ' + a['date'] if a['date'] else ', …… / …… / ' + year_tail(p)); merge(ws, f, 20, f, 24)
    ws.cell(f + 1, 2).value = 'ΘΕΩΡΗΘΗΚΕ'
    ws.cell(f + 1, 7).value = '   ΤΟ ΔΙΔΑΚΤΙΚΟ ΠΡΟΣΩΠΙΚΟ ΤΟΥ ΟΛΟΗΜΕΡΟΥ ΣΧΟΛΕΙΟΥ'; merge(ws, f + 1, 7, f + 1, 19)
    ws.cell(f + 1, 20).value = a['director_title']; merge(ws, f + 1, 20, f + 1, 24)
    ws.cell(f + 2, 2).value = a['approver']
    for k, nm in enumerate(left):
        ws.cell(f + 2 + k, 7).value = nm
    for k, nm in enumerate(right):
        ws.cell(f + 2 + k, 13).value = nm
    ws.cell(f + 5, 20).value = admin.upper(director) if director else None; merge(ws, f + 5, 20, f + 5, 24)
    ws.print_area = 'A1:X%d' % (f + k_rows)


def export_allday(p):
    """Αρχείο «Ολοήμερο» (ΠΡΟΓΡΑΜΜΑ + ΩΡΑΡΙΟ ΕΚΠ). Επιστρέφει (bytes, προειδοποιήσεις)."""
    core.check_structure(p)
    wb = openpyxl.load_workbook(FORMS / 'oloimero.xlsx'); warn = []
    m = admin.allday_matrix(p)
    if any(s['kind'] == 'allday' and not s.get('grades') for s in m['sections']):
        warn.append('Δεν έχουν οριστεί οι τάξεις κάθε τμήματος Ολοήμερου (π.χ. «Α - Β»)· ορίστε τες στα «Βοηθητικά εργαλεία».')
    if not m['sections']:
        warn.append('Δεν βρέθηκαν τμήματα Ολοήμερου ή Πρωινής Ζώνης (π.χ. «ΟΛ1», «Πρωινή Ζώνη»). Ορίστε τα στα «Βοηθητικά εργαλεία».')
    sheet_allday_program(p, wb['ΠΡΟΓΡΑΜΜΑ'], m, warn)
    sheet_allday_hours(p, wb['ΩΡΑΡΙΟ ΕΚΠ'], m, warn)
    return save(wb), warn
