"""Εισαγωγή αρχείου .roz του aSc TimeTables (δυαδική μορφή, ελληνικά σε windows-1253).

Η μορφή δεν είναι δημοσιευμένη· η ανάγνωση βασίζεται σε ό,τι επαληθεύτηκε σε πραγματικό
αρχείο σε σύγκριση με το XML του ίδιου προγράμματος:
  • εγγραφές με κεφαλίδα 02 00 01 xx + αναγνωριστικό 8 byte (ίδιο με το id του XML, ανάποδα)
  • ώρες (ώρα/λεπτά έναρξης–λήξης), μαθήματα, εκπαιδευτικοί, ομάδες, τμήματα (CLASSTT)
  • αναθέσεις: μάθημα, ομάδες τμημάτων, εκπαιδευτικοί, κάρτες × διάρκεια
  • κάρτες 75 byte: ανάθεση, ώρα, ημέρα (bit), κλείδωμα
  • πίνακας διαθεσιμότητας 10 ημέρες × 32 ώρες: 4 = επιτρεπτό, 0 = όχι (όλα 0 = χωρίς περιορισμό)
Ό,τι δεν αναγνωρίζεται με βεβαιότητα δεν εισάγεται· η αναφορά το λέει.
"""
import re, struct
import core

HDR = re.compile(rb'\x02\x00\x01[\x00\x01](.{8})\x00\x00\x00\x00.{3}[\x00-\x02]', re.S)
CARD = 75
DAYBIT = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}


class RozError(ValueError):
    pass


def _i32(d, o):
    return struct.unpack_from('<i', d, o)[0]


def _pstr(d, o):
    n = d[o]
    return d[o + 1:o + 1 + n].decode('cp1253', 'replace'), o + 1 + n


def _records(d):
    out = []
    for m in HDR.finditer(d):
        h = m.start(); o = h + 20
        if o >= len(d) or d[o] > 120:
            continue
        name, o2 = _pstr(d, o)
        if o2 >= len(d) or d[o2] > 120:
            continue
        short, o3 = _pstr(d, o2)
        out.append(dict(h=h, id=m.group(1)[::-1].hex().upper(), name=name, short=short, after_name=o2, after=o3))
    for a, b in zip(out, out[1:]):
        a['end'] = b['h']
    if out:
        out[-1]['end'] = len(d)
    return out


def _grid(d, r, nper):
    """Πίνακας διαθεσιμότητας μέσα στην εγγραφή: None αν δεν υπάρχει, αλλιώς 5×nper τιμές."""
    for i in range(r['after'], max(r['after'], r['end'] - 1280)):
        ok = True
        for k in range(10):
            blk = struct.unpack_from('<32i', d, i + 128 * k)
            if any(v != 6 for v in blk[nper:]):
                ok = False; break
        if ok:
            return [list(struct.unpack_from('<%di' % nper, d, i + 128 * k)) for k in range(5)]
    return None


def _allowed(grid, nper):
    """[[ημέρα, ώρα], …] επιτρεπτών θέσεων, None αν δεν υπάρχει περιορισμός· και πλήθος άγνωστων τιμών."""
    if grid is None or all(v == 0 for row in grid for v in row):
        return None, 0
    unknown = sum(1 for row in grid for v in row if v not in (0, 4))
    return [[dd, i] for dd in range(5) for i in range(nper) if grid[dd][i] != 0], unknown


def parse(raw):
    """Επιστρέφει (έργο, αναφορά)."""
    d = bytes(raw)
    if len(d) > 30_000_000:
        raise RozError('Το αρχείο .roz είναι πολύ μεγάλο.')
    if d[5:10] != b'ASCTT':
        raise RozError('Το αρχείο δεν είναι .roz του aSc TimeTables.')
    recs = _records(d)
    cls_recs = [r for r in recs if r['name'] == 'CLASSTT']
    if not cls_recs:
        raise RozError('Δεν βρέθηκαν τμήματα στο αρχείο .roz (μη υποστηριζόμενη έκδοση aSc;). Δοκιμάστε την εξαγωγή XML.')
    first_cls = recs.index(cls_recs[0])

    # ---- ώρες
    periods = []
    for r in recs[:first_cls]:
        h = r['h']
        if h + 45 > len(d):
            continue
        idx = _i32(d, h + 20); h1, m1, h2, m2 = struct.unpack_from('<4i', d, h + 29)
        ok = idx == len(periods) and 0 <= h1 < 24 and 0 <= m1 < 60 and 0 <= h2 < 24 and 0 <= m2 < 60 and h1 * 60 + m1 < h2 * 60 + m2
        if ok and periods and periods[-1][1] * 60 > 0 and periods[-1][2] > h1 * 60 + m1:
            ok = False
        if ok:
            periods.append((r, h1 * 60 + m1, h2 * 60 + m2))
        elif periods:
            break
    nper = len(periods)
    if not 1 <= nper <= 20:
        raise RozError('Δεν αναγνωρίστηκαν οι διδακτικές ώρες στο αρχείο .roz. Δοκιμάστε την εξαγωγή XML.')
    hm = lambda x: '%d:%02d' % divmod(x, 60)

    # ---- τμήματα και ομάδες
    classes = []
    for r in cls_recs:
        name, o = _pstr(d, r['after_name'])
        short, o = _pstr(d, o)
        o += 1 + 4
        cnt = _i32(d, o); o += 4
        if not 0 < cnt < 64:
            raise RozError('Μη αναγνωρίσιμη εγγραφή τμήματος «%s».' % name)
        gidx = [_i32(d, o + 4 * k) for k in range(cnt)]
        classes.append(dict(rec=r, name=name, short=short or name, groups=gidx))
    G = max(i for c in classes for i in c['groups']) + 1
    if G > first_cls:
        raise RozError('Μη αναγνωρίσιμες ομάδες τμημάτων.')
    grp_recs = recs[first_cls - G:first_cls]
    groups = []
    for r in grp_recs:
        o = r['after_name']
        groups.append(dict(rec=r, name=r['name'], entire=d[o], division=_i32(d, o + 4)))
    gclass = {}
    for ci, c in enumerate(classes):
        for g in c['groups']:
            gclass[g] = ci

    # ---- μαθήματα και εκπαιδευτικοί (ανάμεσα στις ώρες και στις ομάδες)
    start = recs.index(periods[-1][0]) + 1
    middle = recs[start:first_cls - G]
    subj_pos = [k for k, r in enumerate(middle) if d[r['after']:r['after'] + 5] == b'\x00\xff\xff\xff\xff']
    if not subj_pos:
        raise RozError('Δεν βρέθηκαν μαθήματα στο αρχείο .roz.')
    subj_recs = [middle[k] for k in subj_pos]
    teach_recs = [r for r in middle[subj_pos[-1] + 1:] if _i32(d, r['after'] + 21) == nper or _i32(d, r['after'] + 22) == nper]

    # ---- αναθέσεις
    lessons = []
    for r in recs[recs.index(cls_recs[-1]) + 1:]:
        if r['name']:
            break
        a = r['after']
        try:
            dur = d[a + 11] + 1; ncards = _i32(d, a + 15); subj = _i32(d, a + 32)
            o = a + 36; ng = _i32(d, o); o += 4
            if not 0 <= ng < 64:
                break
            gl = [_i32(d, o + 4 * k) for k in range(ng)]; o += 4 * ng
            nt = _i32(d, o); o += 4
            if not 0 <= nt < 16:
                break
            tl = [_i32(d, o + 4 * k) for k in range(nt)]
        except (struct.error, IndexError):
            break
        if not (0 <= subj < len(subj_recs) and all(0 <= g < G for g in gl) and all(0 <= t < len(teach_recs) for t in tl)
                and 0 <= ncards < 100 and 1 <= dur <= nper):
            break
        lessons.append(dict(rec=r, dur=dur, cards=ncards, subject=subj, groups=gl, teachers=tl))
    if not lessons:
        raise RozError('Δεν αναγνωρίστηκαν αναθέσεις στο αρχείο .roz. Δοκιμάστε την εξαγωγή XML.')

    # ---- κάρτες (τοποθετήσεις)
    total = sum(l['cards'] for l in lessons)
    def card(o):
        les, per, mask = _i32(d, o + 14), _i32(d, o + 26), _i32(d, o + 38)
        return les, per, mask, d[o + 10]
    def valid(c):
        les, per, mask, lock = c
        return 0 <= les < len(lessons) and lock in (0, 1) and ((0 <= per < nper and mask in DAYBIT) or (per < 0 or mask == 0))
    base = lessons[-1]['rec']['h']; cards = None
    want = [l['cards'] for l in lessons]; best = -1
    for s in range(base + 40, min(len(d) - CARD * total, base + 3000) + 1):
        if not all(valid(card(s + CARD * k)) for k in range(min(total, 3))):
            continue
        cs = [card(s + CARD * k) for k in range(total)]
        if not all(valid(c) for c in cs) or any(a[0] > b[0] for a, b in zip(cs, cs[1:])):
            continue
        cnt = [0] * len(lessons)
        for c in cs:
            cnt[c[0]] += 1
        if cnt == want:
            placed = sum(1 for c in cs if c[2] in DAYBIT and c[1] >= 0)
            if cards is None or placed > best:
                cards, best = cs, placed
            if placed == total:
                break
    if cards is None and total:
        raise RozError('Δεν αναγνωρίστηκαν οι κάρτες του προγράμματος στο .roz. Δοκιμάστε την εξαγωγή XML.')
    per_lesson = {}
    for les, per, mask, lock in cards or []:
        per_lesson.setdefault(les, []).append((DAYBIT.get(mask), per if per >= 0 else None, lock))
    for k, l in enumerate(lessons):
        if len(per_lesson.get(k, [])) != l['cards']:
            raise RozError('Ασυμφωνία καρτών στο αρχείο .roz· η εισαγωγή ακυρώθηκε. Δοκιμάστε την εξαγωγή XML.')

    # ---- κατασκευή έργου
    p = core.blank(); p['title'] = 'Πρόγραμμα από aSc (.roz)'; p['source_version'] = 'roz:%d' % struct.unpack_from('<I', d, 0)[0]
    m = re.search(rb'(20\d\d) - (20\d\d)', d)
    if m:
        p['year'] = m.group(0).decode()
    p['periods'] = [dict(id=str(i), name=str(i), start=hm(a), end=hm(b)) for i, (r, a, b) in enumerate(periods)]
    ent = lambda r: dict(id=r['id'], name=r['name'], short=r['short'] or r['name'])
    p['subjects'] = [ent(r) for r in subj_recs]
    p['teachers'] = [ent(r) for r in teach_recs]
    p['classes'] = [dict(id=c['rec']['id'], name=c['name'], short=c['short']) for c in classes]
    p['groups'] = [dict(id=g['rec']['id'], name=g['name'], classid=p['classes'][gclass[i]]['id'] if i in gclass else '',
                        studentids='', entireclass='1' if g['entire'] == 1 else '0', divisiontag=str(g['division']), studentcount='')
                   for i, g in enumerate(groups)]
    p['groups'] = [g for g in p['groups'] if g['classid']]
    gids = {g['id'] for g in p['groups']}
    locked = 0; unplaced = 0
    for k, l in enumerate(lessons):
        cl = []
        for g in l['groups']:
            if g in gclass and p['classes'][gclass[g]]['id'] not in cl:
                cl.append(p['classes'][gclass[g]]['id'])
        les = dict(id=l['rec']['id'], subject=p['subjects'][l['subject']]['id'], teachers=list(dict.fromkeys(p['teachers'][t]['id'] for t in l['teachers'])),
                   classes=cl, groups=[groups[g]['rec']['id'] for g in l['groups'] if groups[g]['rec']['id'] in gids], room='',
                   hours=l['cards'] * l['dur'], duration=l['dur'], days=[0, 1, 2, 3, 4], max_daily=0)
        if not les['teachers'] or not les['hours']:
            continue
        p['lessons'].append(les)
        for day, per, lock in sorted(per_lesson[k], key=lambda x: (x[0] is None, x[0] or 0, x[1] or 0)):
            place = [day, per] if day is not None and per is not None and per + l['dur'] <= nper else None
            unplaced += place is None
            locked += bool(lock and place)
            p['events'].append(dict(id=core.uid(), lesson=les['id'], place=place, locked=bool(lock and place)))

    # ---- διαθεσιμότητα
    unknown = 0; restricted = {'teachers': 0, 'classes': 0, 'subjects': 0}
    for kind, rs in (('teachers', teach_recs), ('subjects', subj_recs), ('classes', [c['rec'] for c in classes])):
        key = core.R.RULE_KEYS[kind]
        for r in rs:
            allowed, unk = _allowed(_grid(d, r, nper), nper)
            unknown += unk
            if allowed is not None and len(allowed) < 5 * nper:
                p[key].setdefault(r['id'], {})['allowed'] = allowed; restricted[kind] += 1
    # Τμήματα χωρίς δηλωμένο παράθυρο: όπως στην εισαγωγή XML, οι ώρες που χρησιμοποιεί το πρόγραμμα
    ls = {l['id']: l for l in p['lessons']}
    for c in p['classes']:
        if 'allowed' in p['class_rules'].get(c['id'], {}):
            continue
        seen = set()
        for e in p['events']:
            l = ls[e['lesson']]
            if c['id'] in l['classes'] and e['place']:
                seen.update(range(e['place'][1], e['place'][1] + l['duration']))
        p['class_rules'][c['id']] = dict(allowed=[[dd, i] for dd in range(5) for i in sorted(seen)] if seen else core.slots(p))
    core.check_structure(p)
    notes = ['Διαθεσιμότητα από το aSc: %d εκπαιδευτικοί, %d μαθήματα, %d τμήματα με περιορισμούς.' % (restricted['teachers'], restricted['subjects'], restricted['classes'])]
    if locked:
        notes.append('%d κλειδωμένες κάρτες μεταφέρθηκαν κλειδωμένες (π.χ. Πρωινή Ζώνη).' % locked)
    if unplaced:
        notes.append('%d κάρτες δεν είχαν θέση και μπαίνουν στις εκκρεμότητες.' % unplaced)
    if unknown:
        notes.append('%d κελιά διαθεσιμότητας με κατάσταση που δεν αναγνωρίστηκε μεταφέρθηκαν ως «επιτρεπτά»· ελέγξτε τους περιορισμούς.' % unknown)
    notes.append('Δεν μεταφέρονται ακόμη από το .roz: όρια ωρών/κενών εκπαιδευτικών, αίθουσες, επιτρεπτές ημέρες αναθέσεων. Ορίστε τα στους Κανόνες.')
    report = dict(kind='roz', counts=dict(periods=nper, teachers=len(p['teachers']), classes=len(p['classes']), subjects=len(p['subjects']),
                                          lessons=len(p['lessons']), events=len(p['events']), placed=sum(1 for e in p['events'] if e['place'])), notes=notes)
    return p, report
