"""Εισαγωγή του JSON της εφαρμογής «Δεδομένα Προγράμματος» (HTML εφαρμογή Γυμνασίου).

Μορφή: {school, days:[…5], periods:N, classes:[ονόματα], subjects:[ονόματα],
        teachers:[{name, avail:[5·N τιμές 1/0.5/0], cond:{…}, active, …}],
        lessons:[{id, cls:"Α1" ή "Γ1,Γ2", subject, teacher, hours, block, group}],
        links:[{id, type: support|parallel|co, lessonIds:[…], note}], pins:[…]}
"""
import unicodedata
import core

WHOLE = {'', 'ΟΛΟ ΤΟ ΤΜΗΜΑ'}
DEFAULT_TIMES = ['08:15', '09:00', '09:05', '09:50', '10:00', '10:45', '10:55', '11:40', '11:50', '12:35',
                 '12:40', '13:25', '13:30', '14:10', '14:15', '14:55', '15:00', '15:40', '15:45', '16:25']


def is_gym_json(d):
    return (isinstance(d, dict) and isinstance(d.get('teachers'), list) and isinstance(d.get('lessons'), list)
            and isinstance(d.get('periods'), int) and any(isinstance(t, dict) and 'avail' in t for t in d['teachers']))


def _short(name, n=4):
    w = [x for x in name.replace('-', ' ').split() if x]
    if len(w) == 1:
        return w[0][:n]
    return ''.join(x[0] for x in w)[:5]


def _norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    return ' '.join(''.join(c for c in s if unicodedata.category(c) != 'Mn').upper().split())


class _DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def parse(d):
    if not is_gym_json(d):
        raise ValueError('Το JSON δεν είναι αρχείο της εφαρμογής «Δεδομένα Προγράμματος».')
    n = d['periods']
    if not 1 <= n <= 20:
        raise ValueError('Μη έγκυρος αριθμός ωρών.')
    if len(d.get('days') or []) not in (0, 5):
        raise ValueError('Υποστηρίζονται μόνο 5 ημέρες.')
    p = core.blank()
    p['title'] = 'Ωρολόγιο Πρόγραμμα'; p['school'] = str(d.get('school') or '')
    p['periods'] = [dict(id=str(i), name=str(i + 1), start=DEFAULT_TIMES[2 * i] if 2 * i + 1 < len(DEFAULT_TIMES) else '%02d:00' % (8 + i),
                         end=DEFAULT_TIMES[2 * i + 1] if 2 * i + 1 < len(DEFAULT_TIMES) else '%02d:45' % (8 + i)) for i in range(n)]
    notes = ['Οι ώρες έναρξης και λήξης δεν υπάρχουν στο αρχείο· μπήκαν ενδεικτικές. Διορθώστε τες στο «Σχολείο & ωράριο».']
    if p['school']:
        notes.append('Σχολείο: ' + p['school'])

    cls = {}
    for name in d.get('classes', []):
        name = str(name).strip()
        if name and _norm(name) not in cls:
            c = dict(id=core.uid(), name=name, short=name[:6]); p['classes'].append(c); cls[_norm(name)] = c
    subj = {}

    def subject(name):
        k = _norm(name)
        if k not in subj:
            s = dict(id=core.uid(), name=str(name).strip(), short=_short(str(name).strip()))
            p['subjects'].append(s); subj[k] = s
        return subj[k]
    for s in d.get('subjects', []):
        if str(s).strip():
            subject(s)

    # ---- εκπαιδευτικοί
    tea = {}; inactive = []; unsupported = {}
    for t in d['teachers']:
        name = str(t.get('name', '')).strip()
        if not name:
            continue
        if t.get('active') is False:
            inactive.append(name); continue
        x = dict(id=core.uid(), name=name, short=_short(name, 3))
        p['teachers'].append(x); tea[_norm(name)] = x
        rr = {}
        av = t.get('avail') or []
        if len(av) == 5 * n:
            allowed = [[dd, i] for dd in range(5) for i in range(n) if av[dd * n + i] > 0]
            maybe = [[dd, i] for dd in range(5) for i in range(n) if 0 < av[dd * n + i] < 1]
            if len(allowed) < 5 * n:
                rr['allowed'] = allowed
            if maybe:
                rr['avoid'] = maybe; rr['avoid_w'] = 3
        c = t.get('cond') or {}
        on = lambda k: isinstance(c.get(k), dict) and c[k].get('on')
        if on('perDay'):
            mx, mn = int(c['perDay'].get('max', 0) or 0), int(c['perDay'].get('min', 0) or 0)
            if 0 < mx < n:
                rr['max_daily'] = dict(v=mx, w=0, on=True)
            if mn > 0:
                rr['min_daily'] = dict(v=mn, w=4, on=True)
        if on('kena'):
            rr['max_gaps_week'] = dict(v=int(c['kena'].get('val', 0) or 0), w=3, on=True)
        if c.get('no2'):
            rr['max_gaps_day'] = dict(v=1, w=3, on=True)
        elif c.get('no3'):
            rr['max_gaps_day'] = dict(v=2, w=3, on=True)
        if on('syn'):
            v = int(c['syn'].get('val', 0) or 0)
            if 0 < v < n:
                rr['max_consecutive'] = dict(v=v, w=4, on=True)
        if c.get('from2'):
            rr['earliest'] = dict(v=1, w=0, on=True)
        for k, label in (('meres', 'πλήθος ημερών παρουσίας'), ('sev7', 'όριο τελευταίων ωρών'), ('qmax', 'όριο θέσεων «υπό όρους»')):
            if on(k) and not (k == 'meres' and int(c[k].get('val', 5) or 5) >= 5):
                unsupported.setdefault(label, []).append(name)
        if c.get('early'):
            unsupported.setdefault('«να έρχεται 1η ώρα»', []).append(name)
        if rr:
            p['teacher_rules'][x['id']] = rr
    if inactive:
        notes.append('Δεν συμμετέχουν (δεν εισήχθησαν, ούτε οι αναθέσεις τους): ' + ', '.join(inactive) + '.')
    for label, names in unsupported.items():
        notes.append('Δεν υποστηρίζεται ακόμη το «%s» (%d εκπαιδευτικοί: %s).' % (label, len(names), ', '.join(names[:6]) + (' …' if len(names) > 6 else '')))
    notes.append('Αυστηρότητα των κανόνων: μέγιστες ώρες/ημέρα και «όχι 1η ώρα» υποχρεωτικά· κενά, ελάχιστες ώρες και συνεχόμενες ώρες επιθυμητά. Αλλάζουν στους Κανόνες.')

    # ---- ομάδες τμημάτων: όσες ομάδες «δένονται» στην ίδια ώρα ανήκουν στον ίδιο διαχωρισμό
    src = {l.get('id'): l for l in d['lessons'] if isinstance(l, dict)}
    def lesson_groups(l):
        cs = [x.strip() for x in str(l.get('cls', '')).split(',') if x.strip()]
        gs = [x.strip() for x in str(l.get('group', '')).split(',')]
        if len(gs) != len(cs):
            gs = [gs[0] if gs else ''] * len(cs)
        return [(c, g) for c, g in zip(cs, gs)]
    dsu = _DSU()
    for k in d.get('links', []):
        ids = [i for i in k.get('lessonIds', []) if i in src]
        byclass = {}
        for i in ids:
            for c, g in lesson_groups(src[i]):
                if _norm(g) not in WHOLE:
                    byclass.setdefault(_norm(c), []).append((_norm(c), _norm(g)))
        for pairs in byclass.values():
            for a, b in zip(pairs, pairs[1:]):
                dsu.union(a, b)
    groups = {}; division = {}

    def group(cname, gname):
        key = (_norm(cname), _norm(gname))
        if key not in groups:
            root = dsu.find(key)
            tags = division.setdefault(key[0], {})
            tag = tags.setdefault(root, str(len(tags) + 1))
            g = dict(id=core.uid(), name=gname, classid=cls[key[0]]['id'], entireclass='0', divisiontag=tag, studentids='', studentcount='')
            p['groups'].append(g); groups[key] = g
        return groups[key]

    # ---- αναθέσεις
    made = {}; skipped = 0; split = 0; off = {_norm(x) for x in inactive}
    for l in d['lessons']:
        if not isinstance(l, dict):
            continue
        t = tea.get(_norm(l.get('teacher')))
        pairs = lesson_groups(l)
        if not t or not pairs or not all(_norm(c) in cls for c, _ in pairs) or not str(l.get('subject', '')).strip():
            if _norm(l.get('teacher')) not in off:
                skipped += 1
            continue
        hours = int(l.get('hours') or 0)
        if hours < 1:
            continue
        base = dict(subject=subject(l['subject'])['id'], teachers=[t['id']], classes=[cls[_norm(c)]['id'] for c, _ in pairs],
                    groups=[group(c, g)['id'] for c, g in pairs if _norm(g) not in WHOLE], room='', days=[0, 1, 2, 3, 4], max_daily=0)
        parts = [(hours, 1)]
        if l.get('block'):
            parts = [(hours, 2)] if hours % 2 == 0 else [(hours - 1, 2), (1, 1)] if hours > 1 else [(1, 1)]
            split += hours % 2 == 1 and hours > 1
        made[l.get('id')] = []
        for h, dur in parts:
            les = dict(base, id=core.uid(), hours=h, duration=dur)
            p['lessons'].append(les); made[l.get('id')].append(les['id'])
            p['events'] += [dict(id=core.uid(), lesson=les['id'], place=None, locked=False) for _ in range(h // dur)]
    if skipped:
        notes.append('%d αναθέσεις παραλείφθηκαν (άγνωστος εκπαιδευτικός, τμήμα ή μάθημα).' % skipped)
    if split:
        notes.append('%d διώρα με μονό αριθμό ωρών χωρίστηκαν σε διώρο + μονόωρο.' % split)

    # ---- δεσίματα → ταυτόχρονα μαθήματα (ή συνδιδασκαλία όταν δεν υπάρχουν ομάδες)
    ls = {x['id']: x for x in p['lessons']}; merged = 0; links = 0
    for k in d.get('links', []):
        ids = [x for i in k.get('lessonIds', []) for x in made.get(i, [])]
        ids = [x for x in ids if x in ls]
        if len(ids) < 2:
            continue
        sides = {frozenset(ls[x]['groups']) for x in ids}
        if len(sides) >= 2:
            p.setdefault('links', []).append(dict(id=core.uid(), lessons=ids, note=str(k.get('note') or '')[:200])); links += 1
            continue
        # Χωρίς ομάδες: ίδια μορφή → μία ανάθεση με όλους τους εκπαιδευτικούς (συνδιδασκαλία)
        first = ls[ids[0]]
        if all(ls[x]['hours'] == first['hours'] and ls[x]['duration'] == first['duration'] and ls[x]['classes'] == first['classes'] for x in ids):
            for x in ids[1:]:
                for tt in ls[x]['teachers']:
                    if tt not in first['teachers']:
                        first['teachers'].append(tt)
                p['lessons'] = [y for y in p['lessons'] if y['id'] != x]
                p['events'] = [e for e in p['events'] if e['lesson'] != x]
            merged += 1
        else:
            notes.append('Το δέσιμο «%s» δεν μεταφέρθηκε: οι αναθέσεις δεν έχουν ομάδες ή ίδια μορφή.' % (k.get('note') or k.get('id')))
    if links:
        notes.append('%d δεσίματα έγιναν «ταυτόχρονα μαθήματα»: οι ομάδες τους έχουν μάθημα πάντα την ίδια ώρα.' % links)
    if merged:
        notes.append('%d δεσίματα χωρίς ομάδες έγιναν συνδιδασκαλία (μία ανάθεση με δύο εκπαιδευτικούς).' % merged)
    if d.get('pins'):
        notes.append('Οι σταθερές θέσεις (pins) δεν μεταφέρονται· κλειδώστε τες μετά τη δημιουργία.')
    # ώρες ανά τμήμα: προειδοποίηση αν ξεπερνούν τις θέσεις
    core.check_structure(p)
    report = dict(kind='gym', counts=dict(periods=n, teachers=len(p['teachers']), classes=len(p['classes']), subjects=len(p['subjects']),
                                          lessons=len(p['lessons']), events=len(p['events']), placed=0, links=len(p.get('links', []))), notes=notes)
    return p, report
