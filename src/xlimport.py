"""Εισαγωγή εκπαιδευτικών, τμημάτων, μαθημάτων και αναθέσεων από Excel (.xlsx) και πρότυπο.

• Ανάγνωση .xlsx χωρίς εξωτερικές βιβλιοθήκες (zip + XML).
• Αναγνώριση με βάση τα ονόματα: «Γλώσσα», «ΓΛΩΣΣΑ» και «γλώσσα » είναι το ίδιο.
• Δύο τρόποι:  merge   = προσθήκη νέων και ενημέρωση υπαρχόντων (τίποτα δεν διαγράφεται)
                replace = κάθε φύλλο του αρχείου είναι η πλήρης λίστα· ό,τι λείπει αφαιρείται
• Γραμμές με λάθη παραλείπονται και αναφέρονται στην προεπισκόπηση.
"""
import copy, io, re, unicodedata, zipfile
import xml.etree.ElementTree as ET
import core, outputs

MAX_SIZE = 10_000_000
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

SHEETS = {
    'teachers': ('Εκπαιδευτικοί', ['Ονοματεπώνυμο', 'Συντομογραφία', 'Ρόλος', 'Έτη υπηρεσίας', 'Υποχρεωτικό ωράριο (με το χέρι)']),
    'classes': ('Τμήματα', ['Τμήμα', 'Συντομογραφία', 'Τάξη', 'Υπεύθυνος εκπαιδευτικός']),
    'subjects': ('Μαθήματα', ['Μάθημα', 'Συντομογραφία'] + [g + '΄ (ώρες)' for g in core.GRADES]),
    'lessons': ('Αναθέσεις', ['Τμήμα', 'Μάθημα', 'Εκπαιδευτικός', 'Ώρες την εβδομάδα', 'Μορφή (1 = μονόωρα, 2 = δίωρα)', 'Ημέρες (κενό = όλες)']),
}
# λέξεις-κλειδιά κεφαλίδων (μετά από κανονικοποίηση) → πεδίο
HEAD = {
    'teachers': [('ΣΥΝΤΟΜ', 'short'), ('ΡΟΛ', 'role'), ('ΕΤΗ', 'years'), ('ΥΠΟΧΡ', 'override'), ('ΩΡΑΡ', 'override'), ('ΟΝΟΜ', 'name'), ('ΕΚΠΑΙΔ', 'name')],
    'classes': [('ΣΥΝΤΟΜ', 'short'), ('ΥΠΕΥΘ', 'teacher'), ('ΤΑΞ', 'grade'), ('ΤΜΗΜ', 'name'), ('ΟΝΟΜ', 'name')],
    'subjects': [('ΣΥΝΤΟΜ', 'short'), ('ΜΑΘΗΜ', 'name'), ('ΟΝΟΜ', 'name')] + [(g + ' ', 'g:' + g) for g in core.GRADES],
    'lessons': [('ΤΜΗΜ', 'classes'), ('ΜΑΘΗΜ', 'subject'), ('ΕΚΠΑΙΔ', 'teachers'), ('ΩΡΕΣ', 'hours'), ('ΜΟΡΦ', 'duration'), ('ΔΙΑΡΚ', 'duration'), ('ΗΜΕΡ', 'days')],
}


def norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').upper()
    s = s.replace('΄', '').replace("'", '').replace('’', '').replace('ʹ', '')
    # λατινικά που μοιάζουν με ελληνικά (συχνό σε συντομογραφίες τμημάτων)
    s = s.translate(str.maketrans('ABEZHIKMNOPTYX', 'ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ'))
    return re.sub(r'\s+', ' ', s).strip()


# ------------------------------------------------------------------ ανάγνωση xlsx
def _col(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(raw):
    """{όνομα φύλλου: [[κείμενο κελιού, ...], ...]} με τα κελιά ως κείμενο."""
    if len(raw) > MAX_SIZE:
        raise ValueError('Το αρχείο Excel είναι πολύ μεγάλο.')
    if raw[:4] == b'\xd0\xcf\x11\xe0':
        raise ValueError('Παλιά μορφή Excel (.xls). Ανοίξτε το στο Excel και «Αποθήκευση ως» → «Βιβλίο εργασίας Excel (.xlsx)».')
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        wb = ET.fromstring(z.read('xl/workbook.xml'))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError('Το αρχείο δεν είναι έγκυρο Excel (.xlsx).')
    rels = {}
    try:
        for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
            t = r.get('Target', '').lstrip('/')
            rels[r.get('Id')] = t if t.startswith('xl/') else 'xl/' + t
    except KeyError:
        pass
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    out = {}
    for sh in wb.findall('m:sheets/m:sheet', NS):
        path = rels.get(sh.get(RNS))
        if not path or path not in z.namelist():
            continue
        rows = {}
        for row in ET.fromstring(z.read(path)).findall('m:sheetData/m:row', NS):
            cells = {}
            for c in row.findall('m:c', NS):
                typ = c.get('t'); v = c.find('m:v', NS)
                if typ == 'inlineStr':
                    val = ''.join(t.text or '' for t in c.iter('{%s}t' % NS['m']))
                elif v is None or v.text is None:
                    continue
                elif typ == 's':
                    val = shared[int(v.text)]
                elif typ == 'b':
                    val = 'ΝΑΙ' if v.text == '1' else ''
                else:
                    val = v.text
                    if typ not in ('str', 'e'):
                        try:
                            f = float(val); val = str(int(f)) if f == int(f) else str(f)
                        except ValueError:
                            pass
                ref = c.get('r')
                cells[_col(ref) if ref else len(cells)] = val.strip()
            if cells:
                rows[int(row.get('r', len(rows) + 1))] = [cells.get(i, '') for i in range(max(cells) + 1)]
        out[sh.get('name', '')] = [rows[k] for k in sorted(rows)], sorted(rows)
    return out


def _kind_of_sheet(name):
    n = norm(name)
    for kind, key in (('lessons', 'ΑΝΑΘ'), ('teachers', 'ΕΚΠΑΙΔ'), ('classes', 'ΤΜΗΜ'), ('subjects', 'ΜΑΘΗΜ')):
        if key in n:
            return kind
    return None


def _columns(kind, header):
    cols = {}
    for i, h in enumerate(header):
        n = norm(h) + ' '
        if kind == 'subjects':
            m = re.match(r'(ΣΤ|[ΑΒΓΔΕ])( |\(|$)', n)
            if m and m.group(1) in core.GRADES and len(norm(h)) <= 12:
                cols.setdefault('g:' + m.group(1), i); continue
        for key, field in HEAD[kind]:
            if key in n and not field.startswith('g:'):
                cols.setdefault(field, i); break
    return cols


def tables(raw):
    """{kind: [(αρ. γραμμής Excel, {πεδίο: τιμή})]} για τα φύλλα που αναγνωρίστηκαν."""
    out = {}
    for name, (rows, numbers) in read_xlsx(raw).items():
        kind = _kind_of_sheet(name)
        if not kind or kind in out:
            continue
        # κεφαλίδα: η πρώτη γραμμή (στις 5 πρώτες) που έχει τη βασική στήλη
        need = {'teachers': 'name', 'classes': 'name', 'subjects': 'name', 'lessons': 'subject'}[kind]
        for k, row in enumerate(rows[:5]):
            cols = _columns(kind, row)
            if need in cols:
                break
        else:
            raise ValueError('Στο φύλλο «%s» δεν βρέθηκε γραμμή κεφαλίδων (π.χ. «%s»).' % (name, SHEETS[kind][1][0 if kind != 'lessons' else 1]))
        data = []
        for row, num in zip(rows[k + 1:], numbers[k + 1:]):
            rec = {f: (row[i] if i < len(row) else '') for f, i in cols.items()}
            if any(v for v in rec.values()):
                data.append((num, rec))
        out[kind] = data
    if not out:
        raise ValueError('Δεν βρέθηκαν φύλλα «Εκπαιδευτικοί», «Τμήματα», «Μαθήματα» ή «Αναθέσεις». Χρησιμοποιήστε το πρότυπο της εφαρμογής.')
    return out


# ------------------------------------------------------------------ εφαρμογή
def _int(v, lo, hi, what):
    if v in ('', None):
        return None
    try:
        f = float(str(v).replace(',', '.'))
    except ValueError:
        raise ValueError('%s: «%s» δεν είναι αριθμός' % (what, v))
    if f != int(f) or not lo <= f <= hi:
        raise ValueError('%s: «%s» εκτός ορίων (%d–%d)' % (what, v, lo, hi))
    return int(f)


def _role(v):
    n = norm(v)
    if not n or n.startswith('ΕΚΠΑΙΔ'):
        return ''
    if n.startswith('ΥΠΟΔ'):
        return 'deputy'
    if n.startswith('ΔΙΕΥΘ') or n.startswith('ΔΙΕΥΘΥΝ'):
        return 'director'
    raise ValueError('Ρόλος: «%s» (γράψτε Εκπαιδευτικός, Διευθυντής ή Υποδιευθυντής)' % v)


def _grade(v):
    n = norm(v).replace(' ΤΑΞΗ', '').strip()
    if not n:
        return None
    if n in core.GRADES:
        return n
    if n in ('1', '2', '3', '4', '5', '6'):
        return core.GRADES[int(n) - 1]
    if n == 'ΣΤ' or n == 'ΣT':
        return 'ΣΤ'
    raise ValueError('Τάξη: «%s» (γράψτε Α, Β, Γ, Δ, Ε ή ΣΤ)' % v)


def _days(v, p):
    n = norm(v)
    if not n or n in ('ΟΛΕΣ', 'ΟΛΑ'):
        return [0, 1, 2, 3, 4]
    keys = [norm(d)[:2] for d in p['days']]
    out = set()
    for tok in re.split(r'[,;/ +]+', n):
        if not tok:
            continue
        if tok.isdigit() and 1 <= int(tok) <= 5:
            out.add(int(tok) - 1); continue
        if tok[:2] in keys:
            out.add(keys.index(tok[:2])); continue
        raise ValueError('Ημέρες: άγνωστη ημέρα «%s» (π.χ. «Δευ, Τετ»)' % tok)
    return sorted(out)


def _split_names(v):
    return [x.strip() for x in re.split(r'[,;+/]|\s{2,}|\n', v or '') if x.strip()]


class Index:
    """Αναζήτηση οντότητας με βάση το όνομα ή τη συντομογραφία."""
    def __init__(self, items):
        self.by = {}
        for x in items:
            self.add(x)

    def add(self, x):
        for k in (x.get('name'), x.get('short')):
            if k and norm(k) not in self.by:
                self.by[norm(k)] = x

    def get(self, name):
        return self.by.get(norm(name))


def apply(p, raw, mode='merge'):
    """Επιστρέφει (νέο έργο, αναφορά). Δεν αποθηκεύει τίποτα."""
    if mode not in ('merge', 'replace'):
        raise ValueError('Μη έγκυρος τρόπος εισαγωγής.')
    t = tables(raw)
    q = copy.deepcopy(p)
    rep = {'mode': mode, 'sheets': [SHEETS[k][0] for k in SHEETS if k in t], 'added': {}, 'updated': {}, 'removed': {}, 'skipped': [], 'notes': []}
    bump = lambda what, k, n=1: rep[what].__setitem__(k, rep[what].get(k, 0) + n)
    seen = {k: set() for k in SHEETS}

    def skip(kind, num, msg):
        rep['skipped'].append({'sheet': SHEETS[kind][0], 'row': num, 'msg': msg})

    def upsert(kind, num, rec, fill):
        name = (rec.get('name') or '').strip()
        if not name:
            return skip(kind, num, 'Λείπει το όνομα')
        if len(name) > 120:
            return skip(kind, num, 'Πολύ μεγάλο όνομα')
        x = idx[kind].get(name)
        if x is not None and x['id'] in seen[kind]:
            return skip(kind, num, '«%s» υπάρχει ήδη σε προηγούμενη γραμμή' % name)
        new = x is None
        x = {'id': core.uid(), 'name': name, 'short': ''} if new else dict(x)
        try:
            fill(x, rec)
        except ValueError as ex:
            return skip(kind, num, str(ex))
        if rec.get('short'):
            x['short'] = rec['short'].strip()[:20]
        if not x.get('short'):
            x['short'] = name[:6]
        if new:
            q[kind].append(x); idx[kind].add(x); bump('added', kind)
        else:
            old = next(o for o in q[kind] if o['id'] == x['id'])
            if old != x:
                q[kind][q[kind].index(old)] = x; bump('updated', kind)
        seen[kind].add(x['id'])
        return x

    idx = {k: Index(q[k]) for k in ('teachers', 'classes', 'subjects')}
    created = {'teachers': [], 'classes': [], 'subjects': []}
    def autocreate(kind, name):
        x = {'id': core.uid(), 'name': name.strip()[:120], 'short': name.strip()[:6]}
        q[kind].append(x); idx[kind].add(x); seen[kind].add(x['id']); bump('added', kind); created[kind].append(x['name'])
        return x

    def fill_teacher(x, r):
        if 'role' in r:
            role = _role(r['role'])
            if role: x['role'] = role
            else: x.pop('role', None)
        if 'years' in r:
            y = _int(r['years'], 0, 60, 'Έτη υπηρεσίας')
            if y is None: x.pop('years', None)
            else: x['years'] = y
        if 'override' in r:
            o = _int(r['override'], 0, 40, 'Υποχρεωτικό ωράριο')
            if o is None: x.pop('hours_override', None)
            else: x['hours_override'] = o

    for num, r in t.get('teachers', []):
        upsert('teachers', num, r, fill_teacher)

    homes = []
    def fill_class(x, r):
        if 'grade' in r:
            g = _grade(r['grade'])
            auto = core.grade_of({k: v for k, v in x.items() if k != 'grade'})
            if g and g != auto: x['grade'] = g
            elif g == auto or not g: x.pop('grade', None)
    for num, r in t.get('classes', []):
        c = upsert('classes', num, r, fill_class)
        if c and 'teacher' in r:
            homes.append((num, c, r['teacher']))

    cur = q.setdefault('curriculum', {})
    for num, r in t.get('subjects', []):
        hours = {}
        try:
            for g in core.GRADES:
                if 'g:' + g in r:
                    hours[g] = _int(r['g:' + g], 0, 40, 'Ώρες ' + g + '΄')
        except ValueError as ex:
            skip('subjects', num, str(ex)); continue
        s = upsert('subjects', num, r, lambda x, rr: None)
        if s:
            for g, h in hours.items():
                if h is None:
                    if s['id'] in cur.get(g, {}): cur[g].pop(s['id'])
                elif cur.get(g, {}).get(s['id']) != h:
                    cur.setdefault(g, {})[s['id']] = h
                    if any(s['id'] == y['id'] for y in p['subjects']): bump('updated', 'curriculum')
                    else: bump('added', 'curriculum')

    # υπεύθυνοι τμημάτων (μετά τους εκπαιδευτικούς)
    for num, c, tname in homes:
        cc = next(o for o in q['classes'] if o['id'] == c['id'])
        if not tname:
            cc.pop('teacher', None); continue
        tt = idx['teachers'].get(tname) or autocreate('teachers', tname)
        for o in q['classes']:
            if o.get('teacher') == tt['id'] and o['id'] != cc['id']:
                o.pop('teacher')
        cc['teacher'] = tt['id']

    # αναθέσεις
    def lkey(l):
        return (l['subject'], tuple(sorted(l['classes'])), tuple(sorted(l['teachers'])))
    existing = {}
    for l in q['lessons']:
        existing.setdefault(lkey(l), []).append(l)
    occ = {}; kept = set()   # ίδιες γραμμές = ξεχωριστές αναθέσεις (π.χ. δύο ίδιες με διαφορετικές ημέρες)
    for num, r in t.get('lessons', []):
        try:
            if not r.get('subject'): raise ValueError('Λείπει το μάθημα')
            tnames = _split_names(r.get('teachers', ''))
            if not tnames: raise ValueError('Λείπει ο εκπαιδευτικός')
            hours = _int(r.get('hours', ''), 1, 40, 'Ώρες')
            if hours is None: raise ValueError('Λείπουν οι ώρες')
            dur = _int(r.get('duration', ''), 1, len(q['periods']), 'Μορφή') or 1
            if hours % dur: raise ValueError('%d ώρες δεν μοιράζονται σε %dωρα' % (hours, dur))
            days = _days(r.get('days', ''), q)
        except ValueError as ex:
            skip('lessons', num, str(ex)); continue
        # ό,τι δεν υπάρχει στα άλλα φύλλα δημιουργείται από τις Αναθέσεις
        s = idx['subjects'].get(r['subject']) or autocreate('subjects', r['subject'])
        cls = [(idx['classes'].get(n) or autocreate('classes', n))['id'] for n in _split_names(r.get('classes', ''))]
        tch = [(idx['teachers'].get(n) or autocreate('teachers', n))['id'] for n in tnames]
        key = (s['id'], tuple(sorted(set(cls))), tuple(sorted(set(tch))))
        n = occ[key] = occ.get(key, -1) + 1
        l = existing.get(key, [])[n] if n < len(existing.get(key, [])) else None
        if l is None:
            l = dict(id=core.uid(), subject=s['id'], teachers=list(dict.fromkeys(tch)), classes=list(dict.fromkeys(cls)), groups=[], room='', hours=hours, duration=dur, days=days, max_daily=0)
            q['lessons'].append(l)
            q['events'] += [dict(id=core.uid(), lesson=l['id'], place=None, locked=False) for _ in range(hours // dur)]
            bump('added', 'lessons')
        kept.add(l['id'])
        if n >= len(existing.get(key, [])):
            continue
        if (l['hours'], l['duration'], sorted(l['days'])) != (hours, dur, days):
            if (l['hours'], l['duration']) != (hours, dur):
                if any(e['lesson'] == l['id'] and e['place'] for e in q['events']):
                    rep['notes'].append('Άλλαξαν οι ώρες της ανάθεσης στη γραμμή %d: οι θέσεις της στο πρόγραμμα γίνονται εκκρεμότητες.' % num)
                q['events'] = [e for e in q['events'] if e['lesson'] != l['id']]
                q['events'] += [dict(id=core.uid(), lesson=l['id'], place=None, locked=False) for _ in range(hours // dur)]
            elif set(days) != set(l['days']):
                for e in q['events']:
                    if e['lesson'] == l['id'] and e['place'] and e['place'][0] not in days:
                        e['place'] = None; e['locked'] = False
            l.update(hours=hours, duration=dur, days=days); bump('updated', 'lessons')

    for kind, names in created.items():
        if names:
            rep['notes'].append('Νέα %s που δεν υπήρχαν σε δικό τους φύλλο (ελέγξτε για ορθογραφικά λάθη): %s' % ({'teachers': 'ονόματα εκπαιδευτικών', 'classes': 'τμήματα', 'subjects': 'μαθήματα'}[kind], ', '.join(names)))
    # αντικατάσταση: ό,τι λείπει από ένα φύλλο αφαιρείται
    if mode == 'replace':
        if 'lessons' in t:
            gone = [l for l in q['lessons'] if l['id'] not in kept]
            ids = {l['id'] for l in gone}
            q['lessons'] = [l for l in q['lessons'] if l['id'] not in ids]
            q['events'] = [e for e in q['events'] if e['lesson'] not in ids]
            if gone: bump('removed', 'lessons', len(gone))
        used = {k: set() for k in ('teachers', 'classes', 'subjects')}
        for l in q['lessons']:
            used['subjects'].add(l['subject']); used['teachers'].update(l['teachers']); used['classes'].update(l['classes'])
        for kind in ('teachers', 'classes', 'subjects'):
            if kind not in t:
                continue
            drop = [x for x in q[kind] if x['id'] not in seen[kind]]
            stay = [x for x in drop if x['id'] in used[kind]]
            for x in stay:
                rep['notes'].append('«%s» δεν υπάρχει στο φύλλο %s αλλά έχει αναθέσεις· κρατήθηκε.' % (x['name'], SHEETS[kind][0]))
            ids = {x['id'] for x in drop if x['id'] not in used[kind]}
            if ids:
                q[kind] = [x for x in q[kind] if x['id'] not in ids]; bump('removed', kind, len(ids))
                rk = core.R.RULE_KEYS[kind]
                q[rk] = {k: v for k, v in q.get(rk, {}).items() if k not in ids}
                if kind == 'teachers':
                    for c in q['classes']:
                        if c.get('teacher') in ids: c.pop('teacher')
                if kind == 'classes':
                    q['groups'] = [g for g in q['groups'] if g['classid'] not in ids]
                if kind == 'subjects':
                    for g in list(cur):
                        cur[g] = {k: v for k, v in cur[g].items() if k not in ids}
    q['curriculum'] = {g: row for g, row in cur.items() if row}
    if not q['curriculum']:
        q.pop('curriculum', None)
    core.check_structure(q)
    rep['changed'] = q != p
    return q, rep


# ------------------------------------------------------------------ πρότυπο / εξαγωγή
GUIDE = [
    ('Πώς συμπληρώνεται', True),
    ('Συμπληρώστε τα φύλλα «Εκπαιδευτικοί», «Τμήματα», «Μαθήματα» και «Αναθέσεις». Μην αλλάζετε τις κεφαλίδες της πρώτης γραμμής.', False),
    ('Μπορείτε να συμπληρώσετε μόνο όσα φύλλα θέλετε· τα υπόλοιπα αφήστε τα κενά ή διαγράψτε τα.', False),
    ('Τα ονόματα αναγνωρίζονται χωρίς διάκριση πεζών/κεφαλαίων και τόνων: «Γλώσσα» = «ΓΛΩΣΣΑ». Στις Αναθέσεις μπορείτε να γράψετε και τη συντομογραφία.', False),
    ('', False),
    ('Εκπαιδευτικοί', True),
    ('Ρόλος: Εκπαιδευτικός, Διευθυντής ή Υποδιευθυντής (κενό = Εκπαιδευτικός). Τα έτη υπηρεσίας χρησιμοποιούνται για το υποχρεωτικό ωράριο.', False),
    ('Υποχρεωτικό ωράριο: μόνο αν ισχύει κάτι ειδικό· αλλιώς κενό και υπολογίζεται αυτόματα.', False),
    ('', False),
    ('Τμήματα', True),
    ('Τάξη: Α, Β, Γ, Δ, Ε ή ΣΤ (ή 1–6). Κενό για Ολοήμερο, Πρωινή Ζώνη κ.λπ. Υπεύθυνος: όπως είναι γραμμένος στους Εκπαιδευτικούς.', False),
    ('', False),
    ('Μαθήματα', True),
    ('Οι στήλες Α΄–ΣΤ΄ είναι προαιρετικές: οι υποχρεωτικές ώρες του μαθήματος σε κάθε τάξη (θεσμικό πλαίσιο).', False),
    ('', False),
    ('Αναθέσεις', True),
    ('Μία γραμμή για κάθε μάθημα κάθε τμήματος. Παράδειγμα: Τμήμα «Α1», Μάθημα «Γλώσσα», Εκπαιδευτικός «Παπαδοπούλου Μαρία», Ώρες 9, Μορφή 1.', False),
    ('Συνδιδασκαλία: δύο εκπαιδευτικοί χωρισμένοι με κόμμα. Κοινό μάθημα σε πολλά τμήματα (π.χ. κολύμβηση): «Δ1, Δ2».', False),
    ('Μορφή: 1 = μονόωρα, 2 = δίωρα. Ημέρες: κενό = όλες, ή π.χ. «Δευ, Τετ».', False),
    ('', False),
    ('Εισαγωγή', True),
    ('Στην εφαρμογή: «Σχολείο & ωράριο» → «Εισαγωγή από Excel…» ή σύρετε το αρχείο μέσα στο παράθυρο. Πριν από κάθε αλλαγή εμφανίζεται προεπισκόπηση.', False),
]


def template(p=None):
    """Το πρότυπο Excel· με έργο, συμπληρωμένο με τα τρέχοντα στοιχεία (για διόρθωση και επανεισαγωγή)."""
    x = outputs.Xlsx()
    head = x.style(dict(bold=True, fill='24433C', fg='FFFFFF', box=True, bcolor='9AA5A0'))
    cell = x.style(dict(box=True, bcolor='C9D1CC'))
    title = x.style(dict(bold=True, size=13, fg='24433C'))
    sh = x.sheet('Οδηγίες', landscape=False); sh['widths'][1] = 130
    for r, (txt, bold) in enumerate(GUIDE, 1):
        sh['cells'][r, 1] = (txt, title if bold else 0)
    data = {k: [] for k in SHEETS}
    if p:
        tn = {t['id']: t['name'] for t in p['teachers']}; cn = {c['id']: c['name'] for c in p['classes']}; sn = {s['id']: s['name'] for s in p['subjects']}
        rn = {'': 'Εκπαιδευτικός', 'director': 'Διευθυντής', 'deputy': 'Υποδιευθυντής'}
        data['teachers'] = [[t['name'], t.get('short', ''), rn.get(t.get('role', ''), ''), t.get('years', ''), t.get('hours_override', '')] for t in p['teachers']]
        data['classes'] = [[c['name'], c.get('short', ''), c.get('grade', '') or core.grade_of(c), tn.get(c.get('teacher'), '')] for c in p['classes']]
        cur = p.get('curriculum', {})
        data['subjects'] = [[s['name'], s.get('short', '')] + [cur.get(g, {}).get(s['id'], '') for g in core.GRADES] for s in p['subjects']]
        dn = [d[:3] for d in p['days']]
        data['lessons'] = [[', '.join(cn[c] for c in l['classes']), sn[l['subject']], ', '.join(tn[t] for t in l['teachers']), l['hours'], l['duration'],
                            '' if sorted(l['days']) == [0, 1, 2, 3, 4] else ', '.join(dn[d] for d in sorted(l['days']))]
                           for l in sorted(p['lessons'], key=lambda l: (not l['classes'], [cn[c] for c in l['classes']], sn[l['subject']]))]
    widths = {'teachers': [30, 14, 16, 14, 22], 'classes': [18, 14, 8, 30], 'subjects': [28, 14] + [9] * 6, 'lessons': [18, 26, 36, 10, 16, 18]}
    for kind, (name, cols) in SHEETS.items():
        sh = x.sheet(name, freeze=(1, 0))
        for c, h in enumerate(cols, 1):
            sh['cells'][1, c] = (h, head); sh['widths'][c] = widths[kind][c - 1]
        sh['heights'][1] = 30
        rows = data[kind] or [[''] * len(cols) for _ in range(30)]
        for r, row in enumerate(rows, 2):
            for c, v in enumerate(row, 1):
                sh['cells'][r, c] = (v if v is not None else '', cell)
    return x.save()
