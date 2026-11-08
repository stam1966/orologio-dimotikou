"""Αναπληρώσεις: κάλυψη των ωρών εκπαιδευτικών που απουσιάζουν σε συγκεκριμένη ημερομηνία.

Αποθήκευση στο έργο: p['substitutions'] = [
  {date: 'YYYY-MM-DD',
   absent: [{teacher, periods: null (όλη την ημέρα) ή [ώρες], reason}],
   covers: [{event, period, teacher ('' = ακάλυπτη), kind: teacher|merge|other, note}]}]

Υποψήφιοι για κάθε ώρα, με σειρά προτίμησης:
  0 «ώρα διάθεσης»: ο εκπαιδευτικός έχει εκείνη την ώρα ανάθεση χωρίς τμήμα
  1 «κενό»: είναι στο σχολείο, ανάμεσα σε δύο μαθήματά του
  2 «πριν/μετά»: έχει μαθήματα εκείνη την ημέρα, αλλά η ώρα είναι πριν το πρώτο ή μετά το τελευταίο
  3 «εκτός σχολείου»: δεν έχει μάθημα εκείνη την ημέρα
Μέσα στην ίδια κατηγορία: όποιος έχει κάνει λιγότερες αναπληρώσεις σήμερα και φέτος,
και όποιος ήδη διδάσκει το τμήμα.
"""
import datetime, re
import rules as R

KIND_LABEL = {0: 'ώρα διάθεσης', 1: 'κενό', 2: 'πριν/μετά τα μαθήματά του', 3: 'δεν έχει μάθημα την ημέρα'}
COVER_KINDS = {'teacher': 'Εκπαιδευτικός', 'merge': 'Συνένωση με άλλο τμήμα', 'other': 'Άλλη λύση'}
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def weekday(date):
    try:
        d = datetime.date.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError('Μη έγκυρη ημερομηνία.')
    if d.weekday() > 4:
        raise ValueError('Η ημερομηνία είναι Σαββατοκύριακο.')
    return d.weekday()


def validate(p, ids):
    S = p.get('substitutions')
    if S is None:
        return
    if not isinstance(S, list):
        raise ValueError('Μη έγκυρες αναπληρώσεις.')
    seen = set(); evs = {e['id'] for e in p['events']}; n = len(p['periods'])
    for r in S:
        if not isinstance(r, dict) or not DATE.match(str(r.get('date', ''))) or r['date'] in seen:
            raise ValueError('Μη έγκυρη ημερομηνία αναπληρώσεων.')
        seen.add(r['date'])
        r['absent'] = [a for a in r.get('absent', []) if isinstance(a, dict)]
        r['covers'] = [c for c in r.get('covers', []) if isinstance(c, dict)]
        snapshot(p, r, ids)
        # εκπαιδευτικός που διαγράφηκε: η απουσία του δεν μετρά πια, αλλά το όνομά του μένει στο ιστορικό της ημέρας
        gone = [str(a.get('name') or '')[:120] for a in r['absent'] if a.get('teacher') not in ids['teachers'] and a.get('name')]
        r['gone'] = list(dict.fromkeys([str(x)[:120] for x in r.get('gone', []) if isinstance(x, str)] + gone))[:60]
        if not r['gone']:
            r.pop('gone')
        r['absent'] = [a for a in r['absent'] if a.get('teacher') in ids['teachers']]
        for a in r['absent']:
            if a.get('periods') is not None and (not isinstance(a['periods'], list) or any(type(i) != int or not 0 <= i < n for i in a['periods'])):
                raise ValueError('Μη έγκυρες ώρες απουσίας.')
            if len(str(a.get('reason', ''))) > 120:
                raise ValueError('Πολύ μεγάλη αιτιολογία απουσίας.')
        # κάλυψη για διδασκαλία που δεν υπάρχει πια: μένει στο ιστορικό αν έχει «φωτογραφία» της ημέρας
        r['covers'] = [c for c in r['covers'] if c.get('event') in evs or isinstance(c.get('snap'), dict)]
        for c in r['covers']:
            if type(c.get('period')) != int or not 0 <= c['period'] < n:
                raise ValueError('Μη έγκυρη ώρα αναπλήρωσης.')
            if c.get('teacher', '') not in ('',) and c['teacher'] not in ids['teachers']:
                # η κάλυψη έγινε από εκπαιδευτικό που διαγράφηκε: κρατιέται ως «άλλη λύση»
                who = (c.get('snap') or {}).get('teacher') or 'εκπαιδευτικός'
                c['teacher'] = ''; c['kind'] = 'other'; c['note'] = (str(c.get('note', '')) or who + ' (διαγράφηκε)')[:200]
            if c.get('kind', 'teacher') not in COVER_KINDS or len(str(c.get('note', ''))) > 200:
                raise ValueError('Μη έγκυρη αναπλήρωση.')


SNAP_KEYS = ('period', 'classes', 'subject', 'absent', 'teacher')


def snapshot(p, r, ids=None):
    """Κρατά μέσα σε κάθε αναπλήρωση τι ήταν (ώρα, τμήμα, μάθημα, απών, αναπληρωτής) με βάση το πρόγραμμα
    εκείνης της στιγμής, ώστε το ιστορικό να μη χάνεται αν αργότερα διαγραφεί ανάθεση ή εκπαιδευτικός
    ή αλλάξει το πρόγραμμα. Όσες αντιστοιχούν σε ώρα που χρειάζεται κάλυψη σήμερα ανανεώνονται."""
    tnames = {t['id']: t['name'] for t in p.get('teachers', []) if isinstance(t, dict) and 'id' in t}
    for a in r['absent']:
        if a.get('teacher') in tnames:
            a['name'] = tnames[a['teacher']]
    try:
        ns, _ = needs(p, r)
    except Exception:
        ns = []
    by = {(n['event'], n['period']): n for n in ns}
    per = p.get('periods') or []
    for c in r['covers']:
        n = by.get((c.get('event'), c.get('period')))
        if n:
            j = n['period']
            c['snap'] = dict(period=per[j]['name'] + 'η (' + per[j]['start'] + ')', classes=n['classes'], subject=n['subject'],
                             absent=n['absent'], teacher=tnames.get(c.get('teacher'), ''))
        elif isinstance(c.get('snap'), dict):
            c['snap'] = {k: c['snap'].get(k) for k in SNAP_KEYS}
            c['snap']['classes'] = [str(x)[:60] for x in (c['snap']['classes'] or [])][:20]
            c['snap']['absent'] = [str(x)[:120] for x in (c['snap']['absent'] or [])][:20]
            for k in ('period', 'subject', 'teacher'):
                c['snap'][k] = str(c['snap'][k] or '')[:120]
        else:
            c.pop('snap', None)


def history(p, rec, ns=None):
    """Αναπληρώσεις της ημέρας που δεν αντιστοιχούν πια σε ώρα του τρέχοντος προγράμματος."""
    if ns is None:
        ns, _ = needs(p, rec)
    keys = {(n['event'], n['period']) for n in ns}
    out = []
    for c in rec.get('covers', []):
        sn = c.get('snap')
        if (c.get('event'), c.get('period')) in keys or not isinstance(sn, dict):
            continue
        who = R.name_of(p, 'teachers', c['teacher']) if c.get('teacher') else (sn.get('teacher') or '')
        if c.get('kind') in ('merge', 'other'):
            who = COVER_KINDS[c['kind']] + (': ' + who if who else '')
        out.append(dict(event=c.get('event'), period=c.get('period'), label=sn.get('period') or '', classes=sn.get('classes') or [],
                        subject=sn.get('subject') or '', absent=sn.get('absent') or [], who=who or '— ακάλυπτη —', note=c.get('note', '')))
    return sorted(out, key=lambda x: (x['period'] if isinstance(x['period'], int) else 99, x['classes']))


def record(p, date):
    return next((r for r in p.get('substitutions', []) if r['date'] == date), None) or dict(date=date, absent=[], covers=[])


def _absent_at(rec, tid, j):
    for a in rec.get('absent', []):
        if a['teacher'] == tid and (a.get('periods') is None or j in a['periods']):
            return True
    return False


def day_map(p, wd):
    """{(εκπαιδευτικός, ώρα): (διδασκαλία, ανάθεση)} για την ημέρα της εβδομάδας."""
    q = R.active_view(p); ls = R.mapping(q, 'lessons'); out = {}
    for e in q['events']:
        if e['place'] and e['place'][0] == wd:
            l = ls[e['lesson']]
            for j in range(e['place'][1], e['place'][1] + l['duration']):
                for t in l['teachers']:
                    out[t, j] = (e, l)
    return out


def needs(p, rec):
    """Οι ώρες που χρειάζονται κάλυψη, και όσες καλύπτονται ήδη από συνδιδάσκοντα."""
    wd = weekday(rec['date']); dm = day_map(p, wd); out = {}; info = []
    for (t, j), (e, l) in sorted(dm.items(), key=lambda x: (x[0][1], x[0][0])):
        if not _absent_at(rec, t, j) or not l['classes']:
            continue
        key = (e['id'], j)
        if key in out:
            continue
        present = [x for x in l['teachers'] if not _absent_at(rec, x, j)]
        item = dict(event=e['id'], period=j, lesson=l['id'], subject=R.name_of(p, 'subjects', l['subject']),
                    classes=[R.name_of(p, 'classes', c) for c in l['classes']], class_ids=l['classes'],
                    absent=[R.name_of(p, 'teachers', x) for x in l['teachers'] if x not in present])
        if present:
            item['covered_by'] = [R.name_of(p, 'teachers', x) for x in present]; info.append(item)
        else:
            out[key] = item
    return list(out.values()), info


def counts(p, upto=None):
    """Πλήθος αναπληρώσεων ανά εκπαιδευτικό (όλων των αποθηκευμένων ημερών, ή έως μια ημερομηνία)."""
    c = {}
    for r in p.get('substitutions', []):
        if upto and r['date'] > upto:
            continue
        for x in r.get('covers', []):
            if x.get('teacher') and x.get('kind', 'teacher') == 'teacher':
                c[x['teacher']] = c.get(x['teacher'], 0) + 1
    return c


def candidates(p, rec, need, year=None, today=None):
    wd = weekday(rec['date']); dm = day_map(p, wd); j = need['period']
    year = counts(p) if year is None else year
    taken = {x['teacher'] for x in rec.get('covers', []) if x.get('period') == j and x.get('teacher') and x['event'] != need['event']}
    today = today if today is not None else _today(rec, (need['event'], j))
    teaches = {t for l in p['lessons'] for t in l['teachers'] if set(l['classes']) & set(need['class_ids'])}
    out = []
    for t in p['teachers']:
        tid = t['id']
        if t.get('active') is False or _absent_at(rec, tid, j) or tid in taken:
            continue
        busy = dm.get((tid, j))
        if busy:
            if busy[1]['classes']:
                continue
            kind = 0
        else:
            mine = sorted(i for (x, i) in dm if x == tid)
            kind = 3 if not mine else (1 if mine[0] < j < mine[-1] else 2)
        out.append(dict(teacher=tid, name=t['name'], kind=kind, label=KIND_LABEL[kind], today=today.get(tid, 0),
                        year=year.get(tid, 0), knows=tid in teaches))
    out.sort(key=lambda c: (c['kind'], c['today'], c['year'], not c['knows'], c['name']))
    return out


def _today(rec, skip=None):
    c = {}
    for x in rec.get('covers', []):
        if (x['event'], x['period']) == skip:
            continue
        if x.get('teacher') and x.get('kind', 'teacher') == 'teacher':
            c[x['teacher']] = c.get(x['teacher'], 0) + 1
    return c


def day(p, rec):
    """Όλα όσα χρειάζεται η οθόνη αναπληρώσεων για μία ημερομηνία."""
    wd = weekday(rec['date'])
    ns, info = needs(p, rec)
    year = counts(p); year_wo = dict(year)
    saved = next((r for r in p.get('substitutions', []) if r['date'] == rec['date']), None)
    for x in (saved or {}).get('covers', []):            # χωρίς τη σημερινή, για να μη μετρά διπλά
        if x.get('teacher') and x.get('kind', 'teacher') == 'teacher':
            year_wo[x['teacher']] -= 1
    for n in ns:
        n['candidates'] = candidates(p, rec, n, year_wo)
    dm = day_map(p, wd)
    present = sorted({t for (t, _) in dm})
    return dict(date=rec['date'], weekday=wd, day=p['days'][wd], needs=ns, covered=info,
                teachers_today=present, year=year, history=history(p, rec, ns), gone=rec.get('gone', []))


def auto(p, rec, max_per_day=2):
    """Συμπληρώνει τις ακάλυπτες ώρες με τον καλύτερο διαθέσιμο, δίκαια."""
    rec = dict(rec, covers=[dict(c) for c in rec.get('covers', [])])
    ns, _ = needs(p, rec)
    have = {(c['event'], c['period']) for c in rec['covers'] if c.get('teacher') or c.get('kind') != 'teacher'}
    year = counts(p)
    todo = [n for n in ns if (n['event'], n['period']) not in have]
    # πρώτα όσες ώρες έχουν τους λιγότερους υποψηφίους
    todo.sort(key=lambda n: len([c for c in candidates(p, rec, n, year) if c['kind'] < 3]))
    for n in todo:
        cs = [c for c in candidates(p, rec, n, year) if c['today'] < max_per_day]
        rec['covers'] = [c for c in rec['covers'] if (c['event'], c['period']) != (n['event'], n['period'])]
        rec['covers'].append(dict(event=n['event'], period=n['period'], teacher=cs[0]['teacher'] if cs else '', kind='teacher', note=''))
    return rec


# ------------------------------------------------------------------ εκτυπώσεις
def day_pages(p, date):
    rec = record(p, date); wd = weekday(date)
    ns, info = needs(p, rec)
    cov = {(c['event'], c['period']): c for c in rec.get('covers', [])}
    d = datetime.date.fromisoformat(date)
    rows = []
    for n in sorted(ns, key=lambda n: (n['period'], n['classes'])):
        c = cov.get((n['event'], n['period'])) or {}
        who = R.name_of(p, 'teachers', c['teacher']) if c.get('teacher') else ''
        if c.get('kind') in ('merge', 'other'):
            who = COVER_KINDS[c['kind']] + (': ' + who if who else '')
        rows.append([p['periods'][n['period']]['name'] + 'η (' + p['periods'][n['period']]['start'] + ')', ', '.join(n['classes']), n['subject'],
                     ', '.join(n['absent']), who or '— ακάλυπτη —', c.get('note', '')])
    for n in info:
        rows.append([p['periods'][n['period']]['name'] + 'η', ', '.join(n['classes']), n['subject'], ', '.join(n['absent']),
                     'συνδιδασκαλία: ' + ', '.join(n['covered_by']), ''])
    for h in history(p, rec, ns):
        rows.append([h['label'], ', '.join(h['classes']), h['subject'], ', '.join(h['absent']), h['who'],
                     ((h['note'] + ' · ') if h['note'] else '') + 'από παλαιότερο πρόγραμμα'])
    abs_rows = []
    for a in rec.get('absent', []):
        per = 'όλη την ημέρα' if a.get('periods') is None else ', '.join(p['periods'][i]['name'] + 'η' for i in sorted(a['periods']))
        abs_rows.append(R.name_of(p, 'teachers', a['teacher']) + ' (' + per + (', ' + a['reason'] if a.get('reason') else '') + ')')
    title = 'Αναπληρώσεις ' + p['days'][wd] + ' ' + d.strftime('%d/%m/%Y')
    return [dict(type='table', heading='', name=title, header=['Ώρα', 'Τμήμα', 'Μάθημα', 'Απών/ούσα', 'Αναπληρώνει', 'Σημείωση'],
                 rows=rows or [['—', '', '', '', 'Δεν υπάρχουν ώρες για κάλυψη', '']],
                 note='Απουσιάζουν: ' + ('; '.join(abs_rows + [x + ' (διαγράφηκε από τους εκπαιδευτικούς)' for x in rec.get('gone', [])]) or '—'))]


def stats_pages(p):
    c = counts(p); days = sorted(r['date'] for r in p.get('substitutions', []))
    rows = sorted(([t['name'], str(c.get(t['id'], 0))] for t in p['teachers'] if t.get('active') is not False), key=lambda r: (-int(r[1]), r[0]))
    absn = {}
    for r in p.get('substitutions', []):
        for a in r.get('absent', []):
            absn[a['teacher']] = absn.get(a['teacher'], 0) + 1
    for r in rows:
        tid = next(t['id'] for t in p['teachers'] if t['name'] == r[0])
        r.append(str(absn.get(tid, 0)))
    span = (datetime.date.fromisoformat(days[0]).strftime('%d/%m/%Y') + ' – ' + datetime.date.fromisoformat(days[-1]).strftime('%d/%m/%Y')) if days else '—'
    return [dict(type='table', heading='', name='Αναπληρώσεις ανά εκπαιδευτικό', header=['Εκπαιδευτικός', 'Ώρες αναπλήρωσης', 'Ημέρες απουσίας'],
                 rows=rows or [['—', '0', '0']], note='Περίοδος: ' + span + ' · ' + str(len(days)) + ' ημέρες με καταγραφή')]
