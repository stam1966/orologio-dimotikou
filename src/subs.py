"""Αναπληρώσεις: κάλυψη των ωρών εκπαιδευτικών που απουσιάζουν σε συγκεκριμένη ημερομηνία.

Αποθήκευση στο έργο: p['substitutions'] = [
  {date: 'YYYY-MM-DD',
   absent: [{teacher, periods: null (όλη την ημέρα) ή [ώρες], reason}],
   covers: [{event, period, teacher ('' = ακάλυπτη), kind: teacher|merge|other, note}],
   compact: true (συμπτύξεις Β/θμιας), moves: [{event, from, to}] (μάθημα που ανεβαίνει μόνο εκείνη την ημέρα)}]

Συμπτύξεις (Γυμνάσιο/Λύκειο): οι ώρες του απόντα γεμίζουν ανεβάζοντας μαθήματα των τελευταίων ωρών του ίδιου
τμήματος, από εκπαιδευτικούς που διδάσκουν εκείνη την ημέρα στο τμήμα και είναι ελεύθεροι την ώρα του κενού·
το τμήμα σχολάει νωρίτερα. Ό,τι δεν γεμίζει έτσι μένει για αναπλήρωση με εκπαιδευτικό.

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
        if type(r.get('compact', False)) != bool or type(r.get('replan', False)) != bool:
            raise ValueError('Μη έγκυρη ρύθμιση συμπτύξεων.')
        r['moves'] = [m for m in r.get('moves', []) if isinstance(m, dict) and m.get('event') in evs]
        for m in r['moves']:
            if any(type(m.get(k)) != int or not 0 <= m[k] < n for k in ('from', 'to')):
                raise ValueError('Μη έγκυρη σύμπτυξη.')
        if not r['moves']:
            r.pop('moves')
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


def _moved(rec):
    return {m['event']: m for m in (rec or {}).get('moves', [])}


def day_map(p, wd, rec=None):
    """{(εκπαιδευτικός, ώρα): (διδασκαλία, ανάθεση)} για την ημέρα της εβδομάδας (με τις συμπτύξεις της ημέρας)."""
    q = R.active_view(p); ls = R.mapping(q, 'lessons'); out = {}; mv = _moved(rec)
    for e in q['events']:
        if e['place'] and e['place'][0] == wd:
            l = ls[e['lesson']]; start = mv[e['id']]['to'] if e['id'] in mv else e['place'][1]
            for j in range(start, start + l['duration']):
                for t in l['teachers']:
                    out[t, j] = (e, l)
    return out


def class_day(p, rec):
    """{τμήμα: {ώρα: (διδασκαλία, ανάθεση, αρχική ώρα)}} της ημέρας, με τις συμπτύξεις."""
    wd = weekday(rec['date']); q = R.active_view(p); ls = R.mapping(q, 'lessons'); mv = _moved(rec); out = {}
    for e in q['events']:
        if e['place'] and e['place'][0] == wd:
            l = ls[e['lesson']]; start = mv[e['id']]['to'] if e['id'] in mv else e['place'][1]
            for c in l['classes']:
                for k in range(l['duration']):
                    j = start + k; old = out.setdefault(c, {}).get(j)
                    if old and not _gone_at(rec, old[1], old[2]) and _gone_at(rec, l, e['place'][1] + k):
                        continue   # στη θέση ανέβηκε άλλο μάθημα: το μάθημα του απόντα δεν εμφανίζεται εκεί
                    out[c][j] = (e, l, e['place'][1] + k)
    return out


def _gone_at(rec, l, j):
    """Η διδασκαλία δεν γίνεται εκείνη την ώρα: λείπουν όλοι οι διδάσκοντες."""
    return bool(l['teachers']) and all(_absent_at(rec, t, j) for t in l['teachers'])


def class_end(rec, tl):
    """Τελευταία ώρα που γίνεται μάθημα στο τμήμα (μετά τις συμπτύξεις)."""
    js = [j for j, (e, l, j0) in tl.items() if not _gone_at(rec, l, j0)]
    return max(js) if js else -1


def compact(p, rec):
    """Συμπτύξεις: για κάθε τμήμα, τα κενά από απουσίες γεμίζουν με μαθήματα των τελευταίων ωρών του ίδιου
    τμήματος (μόνο μονόωρα, μόνο του τμήματος, με εκπαιδευτικό παρόντα και ελεύθερο την ώρα του κενού)."""
    rec = dict(rec, covers=[dict(c) for c in rec.get('covers', [])], moves=[], compact=True)
    wd = weekday(rec['date'])
    busy = {}
    for (t, j) in day_map(p, wd):
        busy.setdefault(t, set()).add(j)
    movable = lambda l: l['duration'] == 1 and len(l['classes']) == 1 and not l.get('groups') and l['teachers']
    free = lambda l, j: all(not _absent_at(rec, t, j) and j not in busy.get(t, set()) for t in l['teachers'])
    def move(e, l, h, g):
        rec['moves'].append({'event': e['id'], 'from': h, 'to': g})
        for t in l['teachers']:
            busy[t].discard(h); busy[t].add(g)
    for c, tl0 in sorted(class_day(p, rec).items()):
        tl = {j: v for j, v in tl0.items()}
        skip = set()
        while True:
            live = {j: v for j, v in tl.items() if not _gone_at(rec, v[1], v[2])}
            if not live:
                break
            last = max(live)
            gaps = [j for j in range(min(tl), last) if j not in live and j not in skip]
            if not gaps:
                break
            g = gaps[0]; done = False
            # 1) το μάθημα της τελευταίας ώρας ανεβαίνει απευθείας
            for h in sorted(live, reverse=True):
                if h <= g:
                    break
                e, l, j0 = live[h]
                if not movable(l) or not free(l, g):
                    continue
                if h != last:   # 2) ενδιάμεσο μάθημα ανεβαίνει, αν το τελευταίο μπορεί να καλύψει τη θέση του
                    e2, l2, _ = live[last]
                    if not movable(l2) or not all(not _absent_at(rec, t, h) and (h not in busy.get(t, set()) or t in l['teachers']) for t in l2['teachers']):
                        continue
                move(e, l, h, g); tl[g] = tl.pop(h)
                if h != last:
                    e2, l2, _ = live[last]; move(e2, l2, last, h); tl[h] = tl.pop(last)
                done = True; break
            if not done:
                skip.add(g)
    if not rec['moves']:
        rec.pop('moves')
    resolved = {(n['event'], n['period']) for n in compacted(p, rec)}
    rec['covers'] = [x for x in rec['covers'] if (x['event'], x['period']) not in resolved]
    return rec


def uncompact(rec):
    rec = dict(rec); rec.pop('moves', None); rec.pop('compact', None); rec.pop('replan', None)
    return rec


def replan(p, rec, iterations=40000, seed=1):
    """Ανασχεδιασμός της ημέρας (Β/θμια): τα μαθήματα όσων είναι παρόντες ξαναμπαίνουν σε ώρες της ίδιας ημέρας,
    ώστε τα τμήματα να μην έχουν κενά και να σχολάνε όσο νωρίτερα γίνεται, και οι εκπαιδευτικοί να φεύγουν νωρίτερα·
    κανένας εκπαιδευτικός δεν φεύγει αργότερα από ό,τι θα έφευγε (υποχρεωτικό)· μπορεί να έρθει νωρίτερα. Κάθε μάθημα μένει στο ίδιο τμήμα με τον ίδιο εκπαιδευτικό· αλλάζει μόνο
    η ώρα, μόνο γι' αυτή την ημέρα. Αναζήτηση με προσομοιωμένη ανόπτηση, με αφετηρία το κανονικό πρόγραμμα."""
    import random, math
    rnd = random.Random(seed)
    rec = dict(rec, covers=[dict(c) for c in rec.get('covers', [])], moves=[], compact=True, replan=True)
    wd = weekday(rec['date']); q = R.active_view(p); ls = R.mapping(q, 'lessons'); P = len(p['periods'])
    live = [e for e in q['events'] if e['place'] and e['place'][0] == wd and not _gone_at(rec, ls[e['lesson']], e['place'][1])]
    # δέσμες: διδασκαλίες του ίδιου τμήματος στην ίδια ώρα (π.χ. ομάδες) κινούνται μαζί
    parent = {e['id']: e['id'] for e in live}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    first = {}
    for e in live:
        for c in ls[e['lesson']]['classes']:
            k = (c, e['place'][1])
            if k in first:
                parent[find(e['id'])] = find(first[k])
            else:
                first[k] = e['id']
    groups = {}
    for e in live:
        groups.setdefault(find(e['id']), []).append(e)
    B = []   # (διδασκαλίες, διάρκεια, τμήματα, εκπαιδευτικοί, αρχική ώρα, επιτρεπτές ώρες έναρξης)
    for es in groups.values():
        durs = {ls[e['lesson']]['duration'] for e in es}; s0 = es[0]['place'][1]; d = max(durs)
        cls = sorted({c for e in es for c in ls[e['lesson']]['classes']})
        tch = sorted({t for e in es for t in ls[e['lesson']]['teachers'] if not _absent_at(rec, t, s0)})
        part = any(_absent_at(rec, t, j) for e in es for t in ls[e['lesson']]['teachers'] for j in range(P))
        if len(durs) > 1 or part:   # μικτή διάρκεια ή συνδιδάσκων που λείπει κάποιες ώρες: μένει στη θέση του
            ok = [s0]
        else:
            ok = [s for s in range(P - d + 1)]
        B.append((es, d, cls, tch, s0, ok))
    if not B:
        return dict(compact(p, rec), replan=False)
    of = {}; ol = {}
    for es, d, cls, tch, s0, ok in B:
        for t in tch:
            of[t] = min(of.get(t, P), s0); ol[t] = max(ol.get(t, -1), s0 + d - 1)
    def cost(S):
        oc = {}; ot = {}; bad = 0
        for (es, d, cls, tch, s0, ok), s in zip(B, S):
            for j in range(s, s + d):
                for c in cls:
                    oc.setdefault(c, []).append(j)
                for t in tch:
                    ot.setdefault(t, []).append(j)
            if s != s0:
                bad += 15   # όσο λιγότερες αλλαγές
        for c, js in oc.items():
            bad += 10000 * (len(js) - len(set(js)))
            u = set(js); bad += 1000 * (max(u) - min(u) + 1 - len(u)) + 100 * (max(u) + 1)
        for t, js in ot.items():
            bad += 10000 * (len(js) - len(set(js)))
            u = set(js); bad += 5 * (max(u) - min(u) + 1 - len(u)) + 20 * (max(u) + 1) + 1 * max(0, of[t] - min(u)) + 10000 * max(0, max(u) - ol[t])   # κανείς δεν φεύγει αργότερα
        return bad
    by_class = {}
    for k, b in enumerate(B):
        for c in b[2]:
            by_class.setdefault(c, []).append(k)
    # αφετηρίες: οι απλές συμπτύξεις και το κανονικό πρόγραμμα· κρατιέται η καλύτερη λύση
    cm = {m['event']: m['to'] for m in compact(p, rec).get('moves', [])}
    starts = [[cm.get(b[0][0]['id'], b[4]) if b[0][0]['id'] in cm and len(b[0]) == 1 else b[4] for b in B], [b[4] for b in B]]
    best = None; bestS = None
    for S0 in starts:
        S = list(S0); cur = cost(S)
        if best is None or cur < best:
            best, bestS = cur, list(S)
        T = 20.0
        for it in range(iterations // len(starts)):
            k = rnd.randrange(len(B)); old = list(S)
            if rnd.random() < 0.5 and len(B[k][5]) > 1:
                S[k] = rnd.choice(B[k][5])
            else:
                mates = [x for c in B[k][2] for x in by_class[c] if x != k and B[x][1] == B[k][1] and S[k] in B[x][5] and S[x] in B[k][5]]
                if not mates:
                    continue
                x = rnd.choice(mates); S[k], S[x] = S[x], S[k]
            n = cost(S)
            if n <= cur or rnd.random() < math.exp((cur - n) / T):
                cur = n
                if n < best:
                    best, bestS = n, list(S)
            else:
                S = old
            T = max(0.3, T * 0.9995)
    for (es, d, cls, tch, s0, ok), s in zip(B, bestS):
        if s != s0:
            for e in es:
                rec['moves'].append({'event': e['id'], 'from': s0, 'to': s})
    if not rec['moves']:
        rec.pop('moves')
    resolved = {(n['event'], n['period']) for n in compacted(p, rec)}
    rec['covers'] = [c for c in rec['covers'] if (c['event'], c['period']) not in resolved]
    return rec


def compacted(p, rec):
    """Ώρες απόντων που λύθηκαν με σύμπτυξη: γέμισαν με μάθημα που ανέβηκε, ή το τμήμα σχολάει νωρίτερα."""
    if not rec.get('compact'):
        return []
    wd = weekday(rec['date']); dm = day_map(p, wd); cd = class_day(p, rec); out = []
    seen = set()
    for (t, j), (e, l) in sorted(dm.items(), key=lambda x: (x[0][1], x[0][0])):
        if (e['id'], j) in seen or not _absent_at(rec, t, j) or len(l['classes']) != 1 or not _gone_at(rec, l, j):
            continue
        seen.add((e['id'], j))
        c = l['classes'][0]; tl = cd.get(c, {}); end = class_end(rec, tl)
        inn = tl.get(j)
        if inn and inn[0]['id'] != e['id']:
            how = ('ανεβαίνει ' if inn[2] > j else 'μετακινείται ') + R.name_of(p, 'subjects', inn[1]['subject']) + ' (' + ', '.join(R.name_of(p, 'teachers', x) for x in inn[1]['teachers']) + ') από την ' + p['periods'][inn[2]]['name'] + 'η'
        elif j > end:
            how = 'σχολάει νωρίτερα (μετά την ' + p['periods'][end]['name'] + 'η)' if end >= 0 else 'δεν έχει μάθημα'
        else:
            continue
        out.append(dict(event=e['id'], period=j, subject=R.name_of(p, 'subjects', l['subject']), classes=[R.name_of(p, 'classes', c)],
                        absent=[R.name_of(p, 'teachers', x) for x in l['teachers']], how=how))
    return out


def grid(p, rec):
    """Το πρόγραμμα της ημέρας ανά τμήμα, με απουσίες, αναπληρώσεις και συμπτύξεις."""
    wd = weekday(rec['date']); cd = class_day(p, rec)
    orig = class_day(p, dict(rec, moves=[]))
    cov = {(c['event'], c['period']): c for c in rec.get('covers', [])}
    S = lambda l: next((s.get('short') or s['name'] for s in p['subjects'] if s['id'] == l['subject']), '')
    Tn = lambda t: R.name_of(p, 'teachers', t)
    rows = []
    for c in p['classes']:
        tl = cd.get(c['id']); o = orig.get(c['id'], {})
        if not tl and not o:
            continue
        tl = tl or {}; end = class_end(rec, tl) if rec.get('compact') else max(list(tl) + [-1]); cells = {}
        for j in range(len(p['periods'])):
            v = tl.get(j)
            if v:
                e, l, j0 = v
                if _gone_at(rec, l, j0):
                    if rec.get('compact') and j > end:
                        cells[j] = dict(kind='off', top='—', bottom='σχολάει')
                        continue
                    x = cov.get((e['id'], j0)) or {}
                    who = Tn(x['teacher']) if x.get('teacher') else ({'merge': 'συνένωση', 'other': x.get('note') or 'άλλη λύση'}.get(x.get('kind')) or '')
                    cells[j] = dict(kind='cover' if who else 'absent', top=S(l), bottom=(who or 'ακάλυπτη'))
                elif j0 != j:
                    cells[j] = dict(kind='moved', top=S(l), bottom=', '.join(Tn(t) for t in l['teachers']) + ' · από ' + p['periods'][j0]['name'] + 'η')
                else:
                    cells[j] = dict(kind='normal', top=S(l), bottom=', '.join(Tn(t) for t in l['teachers']))
            elif j in o and rec.get('compact') and j > end:
                cells[j] = dict(kind='off', top='—', bottom='σχολάει')
        if cells:
            rows.append(dict(id=c['id'], name=c['name'], cells=cells, end=end))
    used = sorted({j for r in rows for j in r['cells']})
    return dict(periods=used, rows=rows)


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
    if rec.get('compact'):
        done = {(n['event'], n['period']) for n in compacted(p, rec)}
        out = {k: v for k, v in out.items() if k not in done}
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
    wd = weekday(rec['date']); dm = day_map(p, wd, rec); j = need['period']
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
                teachers_today=present, year=year, history=history(p, rec, ns), gone=rec.get('gone', []),
                compacted=compacted(p, rec), compact=bool(rec.get('compact')), grid=grid(p, rec))


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
    for n in compacted(p, rec):
        rows.append([p['periods'][n['period']]['name'] + 'η (' + p['periods'][n['period']]['start'] + ')', ', '.join(n['classes']), n['subject'],
                     ', '.join(n['absent']), 'Σύμπτυξη: ' + n['how'], ''])
    rows.sort(key=lambda r: r[0])
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
                 note='Απουσιάζουν: ' + ('; '.join(abs_rows + [x + ' (διαγράφηκε από τους εκπαιδευτικούς)' for x in rec.get('gone', [])]) or '—'))] + grid_pages(p, rec)


def grid_pages(p, rec):
    """Σελίδα «Πρόγραμμα ημέρας»: τμήματα × ώρες, με τις αλλαγές της ημέρας."""
    if not rec.get('absent'):
        return []
    g = grid(p, rec); d = datetime.date.fromisoformat(rec['date'])
    mark = {'absent': '✗ ', 'cover': '↻ ', 'moved': '⇡ ', 'off': '', 'normal': ''}
    head = ['Τμήμα'] + [p['periods'][j]['name'] + 'η' for j in g['periods']]
    rows = []; flags = []
    for r in g['rows']:
        row = [r['name']]; fl = [False]
        for j in g['periods']:
            c = r['cells'].get(j)
            row.append((mark[c['kind']] + c['top'] + '\n' + c['bottom']) if c else '')
            fl.append(bool(c) and c['kind'] in ('absent', 'cover', 'moved', 'off'))
        rows.append(row); flags.append(fl)
    return [dict(type='table', heading='', name='Πρόγραμμα ημέρας ' + p['days'][weekday(rec['date'])] + ' ' + d.strftime('%d/%m/%Y'),
                 header=head, rows=rows, flags=flags,
                 note='⇡ = μάθημα που ανέβηκε (σύμπτυξη) · ↻ = αναπλήρωση · ✗ = ακάλυπτη ώρα · «σχολάει» = το τμήμα φεύγει νωρίτερα. Οι επισημασμένες ώρες αλλάζουν μόνο σήμερα.')]


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
