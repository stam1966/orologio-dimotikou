"""Εκτυπώσεις (HTML/PDF), Excel .xlsx χωρίς εξωτερικές βιβλιοθήκες και XML έργου.
Η εκτύπωση και το Excel παράγονται από την ίδια ενδιάμεση περιγραφή σελίδων."""
import html, io, json, zipfile, datetime
import xml.etree.ElementTree as ET
import core

PALETTE = ['A8D5F5', 'F8C59E', 'B8DFA4', 'D0B9EE', 'F5AEBC', '9CDDD2', 'E8D58D', 'B5C0F0', 'D5B79B', 'A7D6BE', 'E7B6DE', 'B8DCE6', 'D6DCA2', 'E9B5A7', 'C0C4CF', 'E3C99F']
LABELS = {'teachers': 'Εκπαιδευτικοί', 'classes': 'Τμήματα', 'rooms': 'Αίθουσες', 'subjects': 'Μαθήματα'}
SINGULAR = {'teachers': 'εκπαιδευτικού', 'classes': 'τμήματος', 'rooms': 'αίθουσας', 'subjects': 'μαθήματος'}
MODES = {'individual': 'Ωρολόγιο για κάθε εγγραφή', 'overview': 'Συνολικό ωρολόγιο', 'poster': 'Αφίσα τοίχου (A3)',
         'withtable': 'Ωρολόγιο με πίνακα αναθέσεων', 'assignments': 'Πίνακας μαθημάτων', 'distribution': 'Επισκόπηση κατανομής',
         'fairness': 'Δικαιοσύνη κατανομής', 'framework': 'Θεσμικό πλαίσιο (ώρες μαθημάτων, ωράριο εκπαιδευτικών)'}
# Χρωματικό θέμα: κεφαλίδα, λωρίδα τίτλου, ημέρες, στήλη ωρών
THEMES = {
    'color': dict(head='1F3A5F', head_fg='FFFFFF', band='3E7D6E', band_fg='FFFFFF', day='F2B04A', day_fg='1F2A36', per='4B4F8F', per_fg='FFFFFF', grid='3A3F47'),
    'mono': dict(head='FFFFFF', head_fg='000000', band='E6E6E6', band_fg='000000', day='F2F2F2', day_fg='000000', per='F2F2F2', per_fg='000000', grid='000000'),
}


# ------------------------------------------------------------------ δεδομένα
def belongs(l, kind, id):
    return id in l[kind] if kind in ('teachers', 'classes') else l['room' if kind == 'rooms' else 'subject'] == id


def by_id(p, k):
    return {x['id']: x for x in p[k]}


def teacher_color(p, tid):
    for i, t in enumerate(p['teachers']):
        if t['id'] == tid:
            return (t.get('color') or '#' + PALETTE[i % len(PALETTE)]).lstrip('#').upper()
    return 'DBE5EC'


def lesson_color(p, l):
    return teacher_color(p, l['teachers'][0]) if l['teachers'] else 'DBE5EC'


def fg_for(hexcolor):
    """Σκούρα ή λευκά γράμματα, με βάση τη σχετική φωτεινότητα (WCAG)."""
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(hexcolor[i:i + 2], 16)) for i in (0, 2, 4))
    return '1F2A36' if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.2 else 'FFFFFF'


def short(x):
    return x.get('short') or x['name']


def texts(p, l, kind, compact):
    """(πάνω, κάτω) κείμενο κελιού ανάλογα με την κατηγορία της αναφοράς."""
    S = by_id(p, 'subjects'); T = by_id(p, 'teachers'); C = by_id(p, 'classes'); R = by_id(p, 'rooms')
    s = S[l['subject']]
    tn = [short(T[t]) if compact else T[t]['name'] for t in l['teachers']]
    cn = [short(C[c]) for c in l['classes']]
    subj = short(s) if compact else s['name'].upper()
    if kind == 'classes':
        return subj, ', '.join(tn)
    if kind == 'teachers':
        if compact:  # αφίσα: τμήμα πάνω, μάθημα κάτω· μεγάλες ονομασίες τμήματος → συντομογραφία μαθήματος
            top = '+'.join(cn)
            return (top if top and len(top) <= 4 else short(s)), (short(s) if top and len(top) <= 4 else '')
        return (' + '.join(cn) or subj), (s['name'].upper() if cn else '')
    if kind == 'rooms':
        return subj, ' + '.join(cn) + (' · ' if cn and tn else '') + ', '.join(tn)
    return ' + '.join(cn) or '—', ', '.join(tn)


def placed(p, kind, id):
    ls = by_id(p, 'lessons')
    return [(e, ls[e['lesson']]) for e in p['events'] if e['place'] and belongs(ls[e['lesson']], kind, id)]


def used_periods(p, kind, ids):
    ls = by_id(p, 'lessons'); used = set()
    for e in p['events']:
        if not e['place']:
            continue
        l = ls[e['lesson']]
        if any(belongs(l, kind, i) for i in ids):
            used.update(range(e['place'][1], e['place'][1] + l['duration']))
    if not used:
        return list(range(len(p['periods'])))
    return list(range(min(used), max(used) + 1))


def week_page(p, kind, ent, opts):
    """Ατομικό εβδομαδιαίο ωρολόγιο: γραμμές = ώρες, στήλες = ημέρες."""
    periods = used_periods(p, kind, [ent['id']]) if opts.get('used', True) else list(range(len(p['periods'])))
    cells = {}; origin = {}
    groups = {}
    for e, l in placed(p, kind, ent['id']):
        d, i = e['place']
        groups.setdefault((d, i, l['duration']), []).append(l)
    for (d, i, dur), lst in sorted(groups.items()):
        top = ' / '.join(dict.fromkeys(texts(p, l, kind, False)[0] for l in lst))
        bottom = ' / '.join(dict.fromkeys(texts(p, l, kind, False)[1] for l in lst if texts(p, l, kind, False)[1]))
        span = [j for j in range(i, i + dur) if j in periods]
        if not span:
            continue
        key = origin.get((d, span[0]), (d, span[0]))
        if key in cells:  # παράλληλες ομάδες ή επικάλυψη: ένωση στο ίδιο κελί
            c = cells[key]; c['top'] += ' / ' + top; c['bottom'] += (' / ' if c['bottom'] and bottom else '') + bottom; c['color'] = None
            end = max(key[1] + c['span'], span[-1] + 1)
            for j in range(key[1] + c['span'], end):
                if j in periods and (d, j) not in cells:
                    cells[(d, j)] = 'covered'; origin[(d, j)] = key
            c['span'] = len([j for j in range(key[1], end) if j in periods])
            continue
        cells[key] = dict(top=top, bottom=bottom, color=lesson_color(p, lst[0]) if len(lst) == 1 else None, span=len(span))
        for j in span[1:]:
            if (d, j) in cells and cells[(d, j)] != 'covered':  # ξεκινούσε ήδη κάτι εδώ: ένωση
                o = cells.pop((d, j)); c = cells[key]; c['top'] += ' / ' + o['top']; c['bottom'] += ' / ' + o['bottom']; c['color'] = None
            cells[(d, j)] = 'covered'; origin[(d, j)] = key
    return dict(type='week', heading=opts.get('title') or p.get('title') or 'Ωρολόγιο Πρόγραμμα Διδασκαλίας', name=ent['name'], periods=periods, cells=cells)


def matrix_page(p, kind, ents, opts, poster=False):
    """Συνολικό: γραμμές = εγγραφές, στήλες = ημέρες × ώρες."""
    periods = used_periods(p, kind, [x['id'] for x in p[kind]]) if opts.get('used', True) else list(range(len(p['periods'])))
    rows = []
    for ent in ents:
        cells = {}
        for e, l in placed(p, kind, ent['id']):
            d, i = e['place']
            for j in range(i, i + l['duration']):
                if j not in periods:
                    continue
                top, bottom = texts(p, l, kind, True)
                if (d, j) in cells:
                    c = cells[(d, j)]; c['top'] += '/' + top; c['bottom'] += '/' + bottom; c['color'] = None
                else:
                    cells[(d, j)] = dict(top=top, bottom=bottom, color=lesson_color(p, l))
        rows.append(dict(name=ent['name'], color=teacher_color(p, ent['id']) if kind == 'teachers' else None, cells=cells))
    title = ('Αφίσα τοίχου' if poster else 'Συνολικό ωρολόγιο') + ' — ' + LABELS[kind]
    return dict(type='matrix', heading=opts.get('title') or p.get('title') or 'Ωρολόγιο Πρόγραμμα', name=title, periods=periods, rows=rows, poster=poster)


def subjects_table(p):
    C = [c for c in p['classes']]
    head = ['Μάθημα'] + [short(c) for c in C] + ['Σύνολο']
    rows = []
    for s in p['subjects']:
        vals = []; total = 0
        for c in C:
            ls = [l for l in p['lessons'] if l['subject'] == s['id'] and c['id'] in l['classes']]
            h = sum(l['hours'] for l in ls); total += h
            T = by_id(p, 'teachers')
            who = ', '.join(dict.fromkeys(short(T[t]) for l in ls for t in l['teachers']))
            vals.append((str(h) if h else '') + ('\n' + who if who else ''))
        other = sum(l['hours'] for l in p['lessons'] if l['subject'] == s['id'] and not l['classes'])
        rows.append([s['name']] + vals + [str(total + other)])
    rows.append(['Σύνολο'] + [str(sum(l['hours'] for l in p['lessons'] if c['id'] in l['classes'])) for c in C] + [str(sum(l['hours'] for l in p['lessons']))])
    return dict(type='table', heading=p.get('title') or '', name='Πίνακας μαθημάτων (ώρες ανά τμήμα και διδάσκοντες)', header=head, rows=rows)


def assignments_table(p, kind=None, id=None):
    head = ['Μάθημα', 'Εκπαιδευτικοί', 'Τμήματα', 'Ώρες', 'Διάρκεια', 'Τοποθετημένες']
    rows = []; colors = []
    for l in p['lessons']:
        if kind and not belongs(l, kind, id):
            continue
        rows.append([by_id(p, 'subjects')[l['subject']]['name'], ', '.join(by_id(p, 'teachers')[t]['name'] for t in l['teachers']),
                     ', '.join(by_id(p, 'classes')[c]['name'] for c in l['classes']), str(l['hours']), 'δίωρο' if l['duration'] == 2 else str(l['duration']),
                     str(sum(l['duration'] for e in p['events'] if e['lesson'] == l['id'] and e['place']))])
        colors.append(lesson_color(p, l))
    return dict(type='table', heading='', name='Αναθέσεις', header=head, rows=rows, colors=colors)


def main_day(p):
    """Κύριο ωράριο: η συνηθέστερη πρώτη και τελευταία ώρα των τμημάτων."""
    from collections import Counter
    ls = by_id(p, 'lessons'); used = {}
    for e in p['events']:
        if e['place']:
            l = ls[e['lesson']]
            for c in l['classes']:
                used.setdefault((c, e['place'][0]), set()).update(range(e['place'][1], e['place'][1] + l['duration']))
    firsts = Counter(min(u) for u in used.values()); lasts = Counter(max(u) for u in used.values())
    return (firsts.most_common(1)[0][0] if firsts else 0), (lasts.most_common(1)[0][0] if lasts else len(p['periods']) - 1)


def fairness(p):
    """Μετρήσεις ανά εκπαιδευτικό και ποιες ξεχωρίζουν (πάνω από μέσο όρο + 1 τυπική απόκλιση)."""
    import statistics, rules
    first, last = main_day(p)
    head = ['Εκπαιδευτικός', 'Ώρες', 'Ημέρες', 'Κενά', 'Παρουσία', 'Πρώτη ώρα', 'Τελευταία ώρα', 'Μετά τη λήξη', 'Αργή Παρασκευή', 'Ημέρες με 1 ώρα', 'Ώρες ανά ημέρα']
    rows = []; colors = []; data = []
    for t in p['teachers']:
        days = []
        for d in range(5):
            u = set()
            for e, l in placed(p, 'teachers', t['id']):
                if e['place'][0] == d:
                    u.update(range(e['place'][1], e['place'][1] + l['duration']))
            days.append(u)
        if not any(days):
            continue
        hs = [len(u) for u in days]
        m = dict(hours=sum(hs), days=sum(1 for h in hs if h), gaps=sum(max(u) - min(u) + 1 - len(u) for u in days if u),
                 first=sum(1 for u in days if first in u), last=sum(1 for u in days if last in u),
                 after=sum(1 for u in days for i in u if i > last), friday=1 if days[4] and max(days[4]) >= last else 0,
                 ones=sum(1 for h in hs if h == 1))
        m['presence'] = m['hours'] + m['gaps']
        data.append((t, m, hs))
    keys = ['hours', 'days', 'gaps', 'presence', 'first', 'last', 'after', 'friday', 'ones']
    flag = {}
    for k in ('gaps', 'last', 'after', 'ones'):
        vals = [m[k] for _, m, _ in data]
        if len(vals) > 2:
            mu, sd = statistics.mean(vals), statistics.pstdev(vals)
            flag[k] = mu + max(sd, 0.5)
    flags = []
    for t, m, hs in data:
        rows.append([t['name']] + [str(m[k]) if k != 'friday' else ('ναι' if m[k] else '') for k in keys] + ['-'.join(map(str, hs))])
        colors.append(teacher_color(p, t['id']))
        flags.append([False] + [k in flag and m[k] > flag[k] for k in keys] + [False])
    note = ('Πρώτη ώρα = ' + p['periods'][first]['name'] + 'η (' + p['periods'][first]['start'] + '), τελευταία ώρα = ' + p['periods'][last]['name'] + 'η (λήξη ' + p['periods'][last]['end'] + '): οι συνηθέστερες του κύριου ωραρίου. Με χρώμα: τιμές αισθητά πάνω από τον μέσο όρο.') if p['periods'] else ''
    return dict(type='table', heading='', name='Δικαιοσύνη κατανομής', header=head, rows=rows, colors=colors, flags=flags, note=note)


def framework_pages(p):
    """Τα στοιχεία του θεσμικού πλαισίου σε πίνακες για εκτύπωση/Excel."""
    fw = core.framework(p); th = fw['teacher_hours']; cur = p.get('curriculum') or {}
    grades = [g for g in core.GRADES if g in cur] or [g for g in core.GRADES if any(core.grade_of(c) == g for c in p['classes'])]
    subj = [s for s in p['subjects'] if any(cur.get(g, {}).get(s['id']) for g in grades)]
    rows = [[s['name']] + [str(cur.get(g, {}).get(s['id'], '')) for g in grades] for s in subj]
    rows.append(['Σύνολο'] + [str(sum(cur.get(g, {}).values())) for g in grades])
    pages = [dict(type='table', heading='', name='Υποχρεωτικές ώρες μαθημάτων ανά τάξη — ' + fw['level'], header=['Μάθημα'] + [g + '΄' for g in grades],
                  rows=rows if subj else [['Δεν έχουν καταχωριστεί ώρες. Ανοίξτε «Θεσμικό πλαίσιο».'] + [''] * len(grades)],
                  note='Πηγή: ' + (fw['curriculum_source'] or '— (συμπληρώστε το ΦΕΚ στο «Θεσμικό πλαίσιο»)'))]
    r2 = [['Εκπαιδευτικός με ' + (('έως ' + str(b) if a == 0 else str(a) + ' έως ' + str(b)) + ' έτη' if b < 99 else str(a) + '+ έτη') + ' υπηρεσίας', str(h)] for a, b, h in th['bands']]
    r2.append(['Ολιγοθέσια (έως ' + str(th['small_school_max']) + 'θέσια), ανεξαρτήτως ετών', str(th['small_school_hours'])])
    r2 += [['Διευθυντής/ντρια ' + str(a) + (('–' + str(b)) if b < 99 and b != a else ('+' if b >= 99 else '')) + 'θέσιου σχολείου', str(h)] for a, b, h in th['director']]
    r2.append(['Υποδιευθυντής/ντρια: μείωση', '−' + str(th['deputy_reduction'])])
    pages.append(dict(type='table', heading='', name='Υποχρεωτικό διδακτικό ωράριο εκπαιδευτικών', header=['Κατηγορία', 'Ώρες/εβδομάδα'], rows=r2, note='Πηγή: ' + th['source']))
    chk = core.teacher_hours_check(p); r3 = []; colors = []; flags = []
    for t in p['teachers']:
        c = chk.get(t['id']); got = sum(l['hours'] for l in p['lessons'] if t['id'] in l['teachers'])
        r3.append([t['name'], core.ROLES.get(t.get('role', ''), ''), '' if t.get('years') is None else str(t['years']),
                   ('' if not c else str(c['required'])) + (' (ορίστηκε)' if t.get('hours_override') is not None else ''), str(got),
                   '' if not c else ('✓' if not c['text'] else ('−' if got < c['required'] else '+') + str(abs(got - c['required'])))])
        colors.append(teacher_color(p, t['id'])); flags.append([False] * 5 + [bool(c and c['text'])])
    pages.append(dict(type='table', heading='', name='Ωράριο ανά εκπαιδευτικό', header=['Εκπαιδευτικός', 'Ρόλος', 'Έτη υπηρεσίας', 'Υποχρεωτικό', 'Ανάθεση', 'Διαφορά'],
                      rows=r3, colors=colors, flags=flags, note='Οργανικότητα σχολείου: ' + (str(p['positions']) + 'θέσιο' if p.get('positions') else '— (συμπληρώστε στο «Σχολείο & ωράριο»)')))
    mis = core.curriculum_check(p)
    r4 = [[c['name'], m] for c in p['classes'] for m in mis.get(c['id'], [])]
    pages.append(dict(type='table', heading='', name='Αποκλίσεις τμημάτων από το ωρολόγιο πρόγραμμα', header=['Τμήμα', 'Απόκλιση'], rows=r4 or [['—', 'Καμία απόκλιση']]))
    return pages


def distribution_table(p):
    import rules
    head = ['Εκπαιδευτικός'] + p['days'] + ['Ανάθεση', 'Τοποθετημένες', 'Κενά', 'Παρουσία']
    rows = []; colors = []
    for t in p['teachers']:
        days = []; gaps = 0
        for d in range(5):
            used = set()
            for e, l in placed(p, 'teachers', t['id']):
                if e['place'][0] == d:
                    used.update(range(e['place'][1], e['place'][1] + l['duration']))
            days.append(len(used))
            if used:
                gaps += max(used) - min(used) + 1 - len(used)
        hours = sum(l['hours'] for l in p['lessons'] if t['id'] in l['teachers'])
        pr = rules.rule(p, 'teachers', t['id'], 'presence')
        rows.append([t['name']] + [str(x) for x in days] + [str(hours), str(sum(days)), str(gaps), str(sum(days) + gaps) + (' / ' + str(pr['v']) if pr else '')])
        colors.append(teacher_color(p, t['id']))
    return dict(type='table', heading='', name='Επισκόπηση κατανομής ωρών', header=head, rows=rows, colors=colors, first_color=True)


def pages(p, opts):
    kind = opts.get('kind', 'teachers'); mode = opts.get('mode', 'individual')
    if kind not in LABELS or mode not in MODES:
        raise ValueError('Μη έγκυρη αναφορά.')
    ents = [x for x in p[kind] if not opts.get('entity') or x['id'] == opts['entity']]
    if mode == 'assignments':
        return [subjects_table(p), dict(assignments_table(p), heading='')]
    if mode == 'distribution':
        return [distribution_table(p)]
    if mode == 'fairness':
        return [fairness(p)]
    if mode == 'framework':
        return framework_pages(p)
    if mode in ('overview', 'poster'):
        return [matrix_page(p, kind, ents, opts, mode == 'poster')]
    out = []
    for x in ents:
        out.append(week_page(p, kind, x, opts))
        if mode == 'withtable':
            out.append(dict(assignments_table(p, kind, x['id']), name='Αναθέσεις — ' + x['name'], attach=True))
    return out


# ------------------------------------------------------------------ HTML
def report(p, opts):
    esc = lambda x: html.escape(str(x))
    paper = opts.get('paper', 'A4'); font = max(6, min(22, int(opts.get('font', 11))))
    if paper not in ('A4', 'A3'):
        raise ValueError('Μη έγκυρο χαρτί.')
    landscape = opts.get('orientation', 'landscape') != 'portrait'
    th = THEMES['mono' if opts.get('theme') == 'mono' else 'color']; colors = opts.get('colors', True)
    school = p.get('school', ''); year = ('Σχολικό Έτος ' + p['year']) if p.get('year') else ''
    stamp = datetime.date.today().strftime('%d/%m/%Y')
    body = []
    pgs = pages(p, opts)
    for pg in pgs:
        top = '' if pg.get('attach') else ('<div class="head"><span>' + esc(school) + '</span><span>' + esc(year) + '</span></div>' if school or year else '')
        band = '<div class="band">' + esc(((pg['heading'] + ' - ') if pg['heading'] and pg['type'] == 'week' else '') + pg['name']) + '</div>'
        if pg.get('attach'):
            band = '<h3>' + esc(pg['name']) + '</h3>'
        if pg['type'] == 'week':
            rows = []
            for i in pg['periods']:
                per = p['periods'][i]
                tr = '<tr><th class="per"><b>' + esc(per['name']) + '</b><small>' + esc(per['start'] + ' - ' + per['end']) + '</small></th>'
                for d in range(5):
                    c = pg['cells'].get((d, i))
                    if c == 'covered':
                        continue
                    if not c:
                        tr += '<td></td>'; continue
                    st = ' style="background:#' + c['color'] + ';color:#' + fg_for(c['color']) + '"' if colors and c['color'] else ''
                    tr += '<td' + (' rowspan="' + str(c['span']) + '"' if c['span'] > 1 else '') + st + '><b>' + esc(c['top']) + '</b><i>' + esc(c['bottom']) + '</i></td>'
                rows.append(tr + '</tr>')
            content = '<table class="week"><thead><tr><th class="corner"></th>' + ''.join('<th class="day">' + esc(d) + '</th>' for d in p['days']) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        elif pg['type'] == 'matrix':
            per = pg['periods']
            head = '<thead><tr><th class="corner" rowspan="2"></th>' + ''.join('<th class="day dsep" colspan="' + str(len(per)) + '">' + esc(d) + '</th>' for d in p['days']) + '</tr><tr>' + ''.join('<th class="pn' + (' dsep' if k == 0 else '') + '">' + esc(p['periods'][i]['name']) + '</th>' for d in range(5) for k, i in enumerate(per)) + '</tr></thead>'
            body_rows = []
            for r in pg['rows']:
                nm = '<th class="rn">' + (('<i class="sw" style="background:#' + r['color'] + '"></i>') if colors and r['color'] else '') + esc(r['name']) + '</th>'
                cells = ''
                for d in range(5):
                    for k, i in enumerate(per):
                        c = r['cells'].get((d, i)); cls = ' class="dsep"' if k == 0 else ''
                        if not c:
                            cells += '<td' + cls + '></td>'; continue
                        st = ' style="background:#' + c['color'] + ';color:#' + fg_for(c['color']) + '"' if colors and c['color'] else ''
                        cells += '<td' + cls + st + '><b>' + esc(c['top']) + '</b><i>' + esc(c['bottom']) + '</i></td>'
                body_rows.append('<tr>' + nm + cells + '</tr>')
            content = '<table class="matrix' + (' poster' if pg['poster'] else '') + '">' + head + '<tbody>' + ''.join(body_rows) + '</tbody></table>'
        else:
            cs = pg.get('colors'); fl = pg.get('flags')
            content = ('<p class="note">' + esc(pg['note']) + '</p>' if pg.get('note') else '') + '<table class="plain' + (' few' if len(pg['header']) <= 3 else '') + '"><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in pg['header']) + '</tr></thead><tbody>' + ''.join(
                '<tr>' + ''.join('<td' + ((' style="background:#' + cs[ri] + ';color:#' + fg_for(cs[ri]) + '"') if colors and cs and ci == 0 else (' class="hi"' if fl and fl[ri][ci] else '')) + '>' + esc(v) + '</td>' for ci, v in enumerate(row)) + '</tr>' for ri, row in enumerate(pg['rows'])) + '</tbody></table>'
        foot = '' if pg.get('attach') else '<div class="foot">Ωρολόγιο Δημοτικού · ' + stamp + '</div>'
        body.append('<section class="' + ('attach' if pg.get('attach') else '') + '">' + top + band + content + foot + '</section>')
    css = '''
    *{box-sizing:border-box}body{margin:0;font:%(f)spx "Segoe UI",Arial,sans-serif;color:#1f2a36;background:#e9edf1}
    .bar{position:sticky;top:0;background:#1f2a36;padding:8px 12px;z-index:9}.bar button{font:14px Arial;padding:8px 14px;border-radius:6px;border:0;cursor:pointer}
    section{background:#fff;margin:14px auto;padding:10mm;width:%(w)s;box-shadow:0 2px 10px #0002;break-after:page}section:last-child{break-after:auto}section.attach{margin-top:-14px;padding-top:0;box-shadow:none}
    .head{display:flex;justify-content:space-between;background:#%(head)s;color:#%(head_fg)s;padding:.5em .9em;font-size:1.65em;font-weight:700;border:1px solid #%(grid)s}
    .band{background:#%(band)s;color:#%(band_fg)s;text-align:center;font-size:1.9em;font-weight:700;padding:.45em;margin:.55em 0;border:1px solid #%(grid)s}
    table{border-collapse:collapse;width:100%%;table-layout:fixed}td,th{border:1px solid #%(grid)s;text-align:center;vertical-align:middle;overflow-wrap:anywhere}
    th.day{background:#%(day)s;color:#%(day_fg)s;font-size:1.45em;padding:.45em}th.corner{background:#fff;width:9%%}
    th.per{background:#%(per)s;color:#%(per_fg)s;padding:.3em}th.per b{display:block;font-size:1.5em}th.per small{font-size:.85em}
    .week td{height:4.2em;padding:.25em}.week td b{display:block;font-size:1.15em}.week td i{display:block;font-size:.9em;margin-top:.35em}
    .matrix{font-size:.72em}.matrix th.rn{width:11%%;text-align:left;padding:.2em .4em;font-size:1.05em;background:#f4f6f8;color:#1f2a36}.matrix th.day{font-size:1.2em;padding:.25em}.matrix th.pn{background:#%(per)s;color:#%(per_fg)s;font-weight:600;padding:.15em 0}
    .matrix td{padding:.1em 0;height:2.6em;font-size:.95em;line-height:1.15;white-space:nowrap;overflow:hidden;overflow-wrap:normal}.matrix td b{display:block}.matrix td i{display:block;font-style:normal;font-size:.85em;opacity:.85}
    .matrix.poster{font-size:1em}.matrix.poster td{height:3.2em}.matrix.poster td b{font-size:1.15em}.dsep{border-left:2.5px solid #%(grid)s!important}
    .sw{display:inline-block;width:.9em;height:.9em;border-radius:2px;margin-right:.35em;vertical-align:-.1em;border:1px solid #0003}
    .plain th{background:#%(per)s;color:#%(per_fg)s;padding:.4em}.plain th:first-child{width:18%%}.plain.few{table-layout:auto;width:auto;min-width:55%%}.plain.few th:first-child{width:auto}.plain td{padding:.35em;white-space:pre-line}.plain td:first-child{text-align:left;font-weight:600}
    .hi{background:#FBE1DC!important;color:#8E2A1D;font-weight:700}.note{font-size:.9em;color:#555;margin:.3em 0 .6em}.foot{text-align:right;font-size:.8em;color:#667;margin-top:.4em}h3{margin:.8em 0 .4em}
    @page{size:%(paper)s %(orient)s;margin:8mm}
    @media print{body{background:#fff}.bar{display:none}section{margin:0;padding:0;width:auto;box-shadow:none}*{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
    ''' % dict(f=font, w=('400mm' if paper == 'A3' else '287mm') if landscape else ('287mm' if paper == 'A3' else '200mm'), paper=paper, orient='landscape' if landscape else 'portrait', **th)
    return ('<!doctype html><html lang="el"><meta charset="utf-8"><title>' + esc(MODES.get(opts.get('mode', 'individual'), 'Εκτύπωση')) + '</title><style>' + css + '</style>' +
            ('' if opts.get('pdf') else '<div class="bar"><button onclick="window.print()">Εκτύπωση / Αποθήκευση PDF</button></div>') + (''.join(body) or '<p>Δεν υπάρχουν εγγραφές.</p>') +
            ('' if opts.get('pdf') else '<script>function fit(){var s=document.querySelector("section");if(!s)return;document.body.style.zoom="";var w=s.offsetWidth+40;document.body.style.zoom=innerWidth<w?(innerWidth/w):"";}addEventListener("resize",fit);fit();addEventListener("beforeprint",function(){document.body.style.zoom="";});addEventListener("afterprint",fit);</script>') + '</html>')


# ------------------------------------------------------------------ XLSX
class Xlsx:
    """Ελάχιστος συγγραφέας OOXML: στυλ, συγχωνεύσεις, πλάτη, ύψη, ρύθμιση σελίδας.
    Όλα τα κείμενα γράφονται ως inline strings (καμία ερμηνεία ως τύπος)."""
    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

    def __init__(self):
        self.sheets = []; self.styles = {}; self.style_list = []; self.fonts = {}; self.fills = {}
        self.style(dict())

    def style(self, s):
        key = tuple(sorted(s.items()))
        if key not in self.styles:
            self.styles[key] = len(self.style_list); self.style_list.append(s)
        return self.styles[key]

    def sheet(self, title, landscape=True, a3=False, freeze=None):
        title = ''.join(c for c in title if c not in '[]:*?/\\')[:31] or 'Φύλλο'
        base = title; k = 2
        while any(s['title'] == title for s in self.sheets):
            suffix = ' (' + str(k) + ')'; title = base[:31 - len(suffix)] + suffix; k += 1
        sh = dict(title=title, cells={}, merges=[], widths={}, heights={}, landscape=landscape, a3=a3, freeze=freeze)
        self.sheets.append(sh); return sh

    @staticmethod
    def col(n):
        s = ''
        while n:
            n, r = divmod(n - 1, 26); s = chr(65 + r) + s
        return s

    def save(self):
        ns = self.NS; rel = self.REL
        xml = lambda node: ET.tostring(node, encoding='utf-8', xml_declaration=True)
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
            ct = ET.Element('Types', xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
            ET.SubElement(ct, 'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
            ET.SubElement(ct, 'Default', Extension='xml', ContentType='application/xml')
            for part, typ in [('workbook', 'sheet.main'), ('styles', 'styles')]:
                ET.SubElement(ct, 'Override', PartName='/xl/' + part + '.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.' + typ + '+xml')
            rr = ET.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
            ET.SubElement(rr, 'Relationship', Id='rId1', Type=rel + '/officeDocument', Target='xl/workbook.xml'); z.writestr('_rels/.rels', xml(rr))
            wb = ET.Element('workbook', xmlns=ns, attrib={'xmlns:r': rel}); ws = ET.SubElement(wb, 'sheets')
            rels = ET.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
            for idx, sh in enumerate(self.sheets, 1):
                ET.SubElement(ws, 'sheet', name=sh['title'], sheetId=str(idx), attrib={'r:id': 'rId' + str(idx)})
                ET.SubElement(rels, 'Relationship', Id='rId' + str(idx), Type=rel + '/worksheet', Target='worksheets/sheet' + str(idx) + '.xml')
                ET.SubElement(ct, 'Override', PartName='/xl/worksheets/sheet' + str(idx) + '.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
                w = ET.Element('worksheet', xmlns=ns)
                pr = ET.SubElement(w, 'sheetPr'); ET.SubElement(pr, 'pageSetUpPr', fitToPage='1')
                views = ET.SubElement(w, 'sheetViews'); v = ET.SubElement(views, 'sheetView', workbookViewId='0', zoomScale='90')
                if sh['freeze']:
                    r0, c0 = sh['freeze']
                    ET.SubElement(v, 'pane', xSplit=str(c0), ySplit=str(r0), topLeftCell=self.col(c0 + 1) + str(r0 + 1), activePane='bottomRight', state='frozen')
                if sh['widths']:
                    cols = ET.SubElement(w, 'cols')
                    for c in sorted(sh['widths']):
                        ET.SubElement(cols, 'col', min=str(c), max=str(c), width=str(sh['widths'][c]), customWidth='1')
                data = ET.SubElement(w, 'sheetData')
                rows = sorted({r for r, c in sh['cells']} | set(sh['heights']))
                for r in rows:
                    attrs = dict(r=str(r))
                    if r in sh['heights']:
                        attrs.update(ht=str(sh['heights'][r]), customHeight='1')
                    row = ET.SubElement(data, 'row', **attrs)
                    for c in sorted(c for rr_, c in sh['cells'] if rr_ == r):
                        val, st = sh['cells'][r, c]
                        cell = ET.SubElement(row, 'c', r=self.col(c) + str(r), s=str(st))
                        if isinstance(val, (int, float)) and not isinstance(val, bool):
                            ET.SubElement(cell, 'v').text = str(val)
                        elif val not in (None, ''):
                            cell.set('t', 'inlineStr'); t = ET.SubElement(ET.SubElement(cell, 'is'), 't'); t.text = str(val)
                            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                if sh['merges']:
                    mg = ET.SubElement(w, 'mergeCells', count=str(len(sh['merges'])))
                    for r1, c1, r2, c2 in sh['merges']:
                        ET.SubElement(mg, 'mergeCell', ref=self.col(c1) + str(r1) + ':' + self.col(c2) + str(r2))
                ET.SubElement(w, 'printOptions', horizontalCentered='1')
                ET.SubElement(w, 'pageMargins', left='0.3', right='0.3', top='0.35', bottom='0.35', header='0.2', footer='0.2')
                ET.SubElement(w, 'pageSetup', paperSize='8' if sh['a3'] else '9', orientation='landscape' if sh['landscape'] else 'portrait', fitToWidth='1', fitToHeight='0')
                z.writestr('xl/worksheets/sheet' + str(idx) + '.xml', xml(w))
            ET.SubElement(rels, 'Relationship', Id='rIdS', Type=rel + '/styles', Target='styles.xml')
            z.writestr('xl/workbook.xml', xml(wb)); z.writestr('xl/_rels/workbook.xml.rels', xml(rels))
            z.writestr('xl/styles.xml', xml(self._styles())); z.writestr('[Content_Types].xml', xml(ct))
        return b.getvalue()

    def _styles(self):
        ns = self.NS; st = ET.Element('styleSheet', xmlns=ns)
        fonts, fills, borders, xfs = [], [None, None], [], []
        for s in self.style_list:
            f = (s.get('size', 10), s.get('bold', False), s.get('italic', False), s.get('fg', '1F2A36'))
            if f not in fonts: fonts.append(f)
            fl = s.get('fill')
            if fl and fl not in fills: fills.append(fl)
            bd = s.get('border', 'thin' if s.get('box') else None), s.get('bcolor', '3A3F47')
            if bd not in borders: borders.append(bd)
        if (None, '3A3F47') not in borders: borders.insert(0, (None, '3A3F47'))
        fe = ET.SubElement(st, 'fonts', count=str(len(fonts)))
        for size, bold, italic, fg in fonts:
            f = ET.SubElement(fe, 'font')
            if bold: ET.SubElement(f, 'b')
            if italic: ET.SubElement(f, 'i')
            ET.SubElement(f, 'sz', val=str(size)); ET.SubElement(f, 'color', rgb='FF' + fg); ET.SubElement(f, 'name', val='Calibri')
        fle = ET.SubElement(st, 'fills', count=str(len(fills)))
        ET.SubElement(ET.SubElement(fle, 'fill'), 'patternFill', patternType='none')
        ET.SubElement(ET.SubElement(fle, 'fill'), 'patternFill', patternType='gray125')
        for c in fills[2:]:
            pf = ET.SubElement(ET.SubElement(fle, 'fill'), 'patternFill', patternType='solid'); ET.SubElement(pf, 'fgColor', rgb='FF' + c); ET.SubElement(pf, 'bgColor', indexed='64')
        be = ET.SubElement(st, 'borders', count=str(len(borders)))
        for style, color in borders:
            b = ET.SubElement(be, 'border')
            for side in ('left', 'right', 'top', 'bottom'):
                e = ET.SubElement(b, side)
                if style:
                    e.set('style', style); ET.SubElement(e, 'color', rgb='FF' + color)
            ET.SubElement(b, 'diagonal')
        ET.SubElement(ET.SubElement(st, 'cellStyleXfs', count='1'), 'xf', numFmtId='0', fontId='0', fillId='0', borderId='0')
        xe = ET.SubElement(st, 'cellXfs', count=str(len(self.style_list)))
        for s in self.style_list:
            fid = fonts.index((s.get('size', 10), s.get('bold', False), s.get('italic', False), s.get('fg', '1F2A36')))
            flid = fills.index(s['fill']) if s.get('fill') else 0
            bid = borders.index((s.get('border', 'thin' if s.get('box') else None), s.get('bcolor', '3A3F47')))
            x = ET.SubElement(xe, 'xf', numFmtId='0', fontId=str(fid), fillId=str(flid), borderId=str(bid), xfId='0', applyFont='1', applyFill='1', applyBorder='1', applyAlignment='1')
            ET.SubElement(x, 'alignment', horizontal=s.get('h', 'center'), vertical='center', wrapText='1')
        cs = ET.SubElement(st, 'cellStyles', count='1'); ET.SubElement(cs, 'cellStyle', name='Normal', xfId='0', builtinId='0')
        return st


def xlsx_pages(x, p, pgs, opts):
    th = THEMES['mono' if opts.get('theme') == 'mono' else 'color']; colors = opts.get('colors', True)
    school = p.get('school', ''); year = ('Σχολικό Έτος ' + p['year']) if p.get('year') else ''
    for pg in pgs:
        if pg['type'] == 'week':
            ncol = 6; sh = x.sheet(pg['name'], landscape=True, a3=opts.get('paper') == 'A3')
            sh['widths'] = {1: 14, **{c: 26 for c in range(2, 7)}}
            r = 1
            if school or year:
                hs = dict(size=16, bold=True, fill=th['head'], fg=th['head_fg'], h='left', box=True)
                sh['cells'][r, 1] = (school, x.style(hs)); sh['merges'].append((r, 1, r, 3))
                sh['cells'][r, 4] = (year, x.style(dict(hs, h='right'))); sh['merges'].append((r, 4, r, 6))
                for c in (2, 3, 5, 6): sh['cells'][r, c] = ('', x.style(hs if c < 4 else dict(hs, h='right')))
                sh['heights'][r] = 30; r += 1
            band = dict(size=18, bold=True, fill=th['band'], fg=th['band_fg'], box=True)
            sh['cells'][r, 1] = (((pg['heading'] + ' - ') if pg['heading'] else '') + pg['name'], x.style(band))
            for c in range(2, 7): sh['cells'][r, c] = ('', x.style(band))
            sh['merges'].append((r, 1, r, 6)); sh['heights'][r] = 36; r += 1
            day = x.style(dict(size=14, bold=True, fill=th['day'], fg=th['day_fg'], box=True))
            sh['cells'][r, 1] = ('', x.style(dict(box=True)))
            for d in range(5): sh['cells'][r, d + 2] = (p['days'][d], day)
            sh['heights'][r] = 26; sh['freeze'] = (r, 1); r += 1
            per = x.style(dict(size=11, bold=True, fill=th['per'], fg=th['per_fg'], box=True))
            empty = x.style(dict(box=True))
            row_of = {}
            for i in pg['periods']:
                pr = p['periods'][i]; row_of[i] = r
                sh['cells'][r, 1] = (pr['name'] + '\n' + pr['start'] + ' - ' + pr['end'], per); sh['heights'][r] = 44
                for d in range(5): sh['cells'][r, d + 2] = ('', empty)
                r += 1
            for (d, i), c in pg['cells'].items():
                if c == 'covered': continue
                fill = c['color'] if colors and c['color'] else None
                s = x.style(dict(size=11, bold=True, box=True, fill=fill, fg=fg_for(fill) if fill else '1F2A36'))
                rr = row_of[i]; sh['cells'][rr, d + 2] = (c['top'] + ('\n' + c['bottom'] if c['bottom'] else ''), s)
                if c['span'] > 1:
                    sh['merges'].append((rr, d + 2, rr + c['span'] - 1, d + 2))
                    for k in range(1, c['span']): sh['cells'][rr + k, d + 2] = ('', s)
        elif pg['type'] == 'matrix':
            per = pg['periods']; poster = pg['poster']
            sh = x.sheet(pg['name'].replace('Συνολικό ωρολόγιο', 'Συνολικό').replace('Αφίσα τοίχου', 'Αφίσα'), landscape=True, a3=True)
            ncols = 1 + 5 * len(per)
            sh['widths'] = {1: 24 if poster else 20, **{c: (7 if poster else 5.5) for c in range(2, ncols + 1)}}
            r = 1
            title = (school + ' · ' if school else '') + pg['name'] + (' · ' + year if year else '')
            band = dict(size=16, bold=True, fill=th['band'], fg=th['band_fg'], box=True)
            sh['cells'][r, 1] = (title, x.style(band))
            for c in range(2, ncols + 1): sh['cells'][r, c] = ('', x.style(band))
            sh['merges'].append((r, 1, r, ncols)); sh['heights'][r] = 30; r += 1
            day = x.style(dict(size=12, bold=True, fill=th['day'], fg=th['day_fg'], box=True, border='medium'))
            sh['cells'][r, 1] = ('', x.style(dict(box=True))); sh['cells'][r + 1, 1] = ('', x.style(dict(box=True)))
            pn = x.style(dict(size=9, bold=True, fill=th['per'], fg=th['per_fg'], box=True))
            for d in range(5):
                c0 = 2 + d * len(per)
                sh['cells'][r, c0] = (p['days'][d], day)
                for k in range(1, len(per)): sh['cells'][r, c0 + k] = ('', day)
                sh['merges'].append((r, c0, r, c0 + len(per) - 1))
                for k, i in enumerate(per): sh['cells'][r + 1, c0 + k] = (p['periods'][i]['name'], pn)
            sh['merges'].append((r, 1, r + 1, 1)); sh['freeze'] = (r + 1, 1); r += 2
            size = 10 if poster else 8
            for row in pg['rows']:
                nf = row['color'] if colors and row['color'] else 'F4F6F8'
                sh['cells'][r, 1] = (row['name'], x.style(dict(size=11 if poster else 10, bold=True, h='left', box=True, fill=nf, fg=fg_for(nf))))
                for d in range(5):
                    for k, i in enumerate(per):
                        c = row['cells'].get((d, i)); col = 2 + d * len(per) + k
                        if not c:
                            sh['cells'][r, col] = ('', x.style(dict(box=True))); continue
                        fill = c['color'] if colors and c['color'] else None
                        sh['cells'][r, col] = (c['top'] + ('\n' + c['bottom'] if c['bottom'] else ''), x.style(dict(size=size, bold=True, box=True, fill=fill, fg=fg_for(fill) if fill else '1F2A36')))
                sh['heights'][r] = 40 if poster else 30; r += 1
        else:
            sh = x.sheet(pg['name'][:31], landscape=True)
            n = len(pg['header'])
            longest = lambda c: max([len(line) for v in [pg['header'][c - 1]] + [r[c - 1] for r in pg['rows']] for line in str(v).split('\n')] or [4])
            sh['widths'] = {c: max(7, min(42, longest(c) + 3)) for c in range(1, n + 1)}
            hd = x.style(dict(size=11, bold=True, fill=th['per'], fg=th['per_fg'], box=True))
            for c, h in enumerate(pg['header'], 1): sh['cells'][1, c] = (h, hd)
            sh['heights'][1] = 28; sh['freeze'] = (1, 1)
            cs = pg.get('colors')
            for ri, row in enumerate(pg['rows'], 2):
                for ci, v in enumerate(row, 1):
                    fill = cs[ri - 2] if colors and cs and ci == 1 else ('FBE1DC' if pg.get('flags') and pg['flags'][ri - 2][ci - 1] else None)
                    val = int(v) if isinstance(v, str) and v.isdigit() else v
                    sh['cells'][ri, ci] = (val, x.style(dict(size=10, bold=ci == 1, h='left' if ci == 1 else 'center', box=True, fill=fill, fg=fg_for(fill) if fill else '1F2A36')))
                sh['heights'][ri] = 16 * max(1, max(str(v).count('\n') + 1 for v in row)) + 4


def export_xlsx(p, opts=None):
    """Χωρίς επιλογές: πλήρες βιβλίο. Με επιλογές: μόνο η τρέχουσα αναφορά."""
    x = Xlsx()
    if opts:
        xlsx_pages(x, p, pages(p, opts), opts)
    else:
        o = {'colors': True}
        xlsx_pages(x, p, [matrix_page(p, 'teachers', p['teachers'], o, True), matrix_page(p, 'classes', p['classes'], o, True),
                          subjects_table(p), assignments_table(p), distribution_table(p)], o)
        for kind in ('classes', 'teachers'):
            xlsx_pages(x, p, [week_page(p, kind, e, o) for e in p[kind]], o)
    if not x.sheets:
        x.sheet('Κενό')
    return x.save()


# ------------------------------------------------------------------ XML έργου
def export_xml(p):
    root = ET.Element('orologio', {'format': '1', 'version': core.VERSION})

    def write(parent, value):
        if isinstance(value, dict):
            parent.set('type', 'object')
            for key, val in value.items():
                write(ET.SubElement(parent, 'item', {'key': str(key)}), val)
        elif isinstance(value, list):
            parent.set('type', 'array')
            for val in value:
                write(ET.SubElement(parent, 'item'), val)
        else:
            parent.set('type', 'value'); parent.text = json.dumps(value, ensure_ascii=False)
    write(root, p)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def import_native(root):
    if root.get('format') != '1':
        raise ValueError('Μη υποστηριζόμενη έκδοση XML.')

    def read(node):
        typ = node.get('type')
        if typ == 'object':
            return {n.attrib['key']: read(n) for n in node}
        if typ == 'array':
            return [read(n) for n in node]
        if typ == 'value':
            return json.loads(node.text)
        raise ValueError('Μη έγκυρο XML έργου.')
    return core.check_structure(read(root))
