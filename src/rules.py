"""Κανόνες ωρολογίου: κατάλογος, έλεγχος υπάρχοντος προγράμματος και μοντέλο CP-SAT.

Κάθε κανόνας αποθηκεύεται ως {"v": τιμή, "w": αυστηρότητα, "on": ενεργός}.
w = 0 υποχρεωτικός· w = 1..5 επιθυμητός με βαρύτητα. Παλιές απλές τιμές
(π.χ. "max_daily": 6) διαβάζονται ως υποχρεωτικοί κανόνες.
Ο έλεγχος σε Python και το μοντέλο του solver μετρούν τις παραβιάσεις με τον
ίδιο τρόπο, ώστε η «ποινή» της λύσης να επαληθεύεται ανεξάρτητα.
"""
from collections import Counter, defaultdict
import itertools

WEIGHTS = {1: 1, 2: 3, 3: 10, 4: 30, 5: 100}
STAY_WEIGHT = 1000  # «μείνε στη θέση σου»: μετακινείται μόνο αν είναι απαραίτητο
STRENGTH = {0: 'Υποχρεωτικός', 5: 'Επιθυμητός · πολύ σημαντικός', 4: 'Επιθυμητός · σημαντικός',
            3: 'Επιθυμητός · μέτριος', 2: 'Επιθυμητός · χαμηλός', 1: 'Επιθυμητός · ελάχιστος'}

# Κατάλογος κανόνων ανά κατηγορία. type: int / period / pattern / flag
CATALOG = {
    'teachers': [
        ('max_daily', 'Μέγιστες ώρες ανά ημέρα', 'int', 0),
        ('min_daily', 'Ελάχιστες ώρες σε ημέρα που έρχεται', 'int', 0),
        ('max_gaps_day', 'Μέγιστα κενά ανά ημέρα', 'int', 0),
        ('max_gaps_week', 'Μέγιστα κενά την εβδομάδα', 'int', 0),
        ('presence', 'Ώρες παρουσίας την εβδομάδα (μαθήματα + κενά)', 'int', 3),
        ('day_pattern', 'Ημέρες με 5 ώρες / ημέρες με 4 ώρες', 'pattern', 5),
        ('max_consecutive', 'Όχι περισσότερες συνεχόμενες ώρες από', 'int', 3),
        ('balance', 'Ισοκατανομή ωρών στις ημέρες διάθεσης', 'flag', 3),
        ('earliest', 'Έναρξη όχι νωρίτερα από', 'period', 0),
    ],
    'classes': [
        ('compact', 'Χωρίς κενά: έναρξη την πρώτη επιτρεπτή ώρα, συνεχόμενα', 'flag', 0),
    ],
    'subjects': [
        ('max_per_day', 'Μέγιστες φορές ανά ημέρα σε κάθε τμήμα (δίωρο = 1)', 'int', 0),
        ('day_end', 'Όποιος το διδάσκει, εκείνη την ημέρα τελειώνει έως', 'period', 0),
    ],
}
RULE_KEYS = {'teachers': 'teacher_rules', 'classes': 'class_rules', 'subjects': 'subject_rules'}
LABEL = {k: {key: label for key, label, *_ in v} for k, v in CATALOG.items()}
TYPES = {k: {key: typ for key, _, typ, _ in v} for k, v in CATALOG.items()}
LEGACY_INT = {'max_daily', 'min_daily', 'max_gaps_day', 'max_gaps_week'}


def norm(raw):
    """Επιστρέφει {'v','w'} για ενεργό κανόνα ή None."""
    if raw is None or raw is False:
        return None
    if isinstance(raw, bool):
        return {'v': True, 'w': 0}
    if isinstance(raw, (int, float)):
        return {'v': int(raw), 'w': 0}
    if isinstance(raw, dict):
        if not raw.get('on', True) or raw.get('v') in (None, '', False):
            return None
        return {'v': raw['v'], 'w': int(raw.get('w', 0) or 0)}
    raise ValueError('Μη έγκυρη μορφή κανόνα.')


def check_rule_value(kind, key, raw, nperiods):
    """Έλεγχος μορφής κατά την αποθήκευση."""
    if raw is None:
        return
    if isinstance(raw, dict):
        if set(raw) - {'v', 'w', 'on'}:
            raise ValueError('Άγνωστα πεδία κανόνα: ' + key)
        w = raw.get('w', 0)
        if type(w) != int or w not in STRENGTH:
            raise ValueError('Μη έγκυρη αυστηρότητα κανόνα: ' + key)
        if type(raw.get('on', True)) != bool:
            raise ValueError('Μη έγκυρη ενεργοποίηση κανόνα: ' + key)
        v = raw.get('v')
    else:
        v = raw
    if v is None:
        return
    typ = TYPES[kind].get(key)
    if typ in ('int', 'period'):
        if type(v) != int or v < 0:
            raise ValueError('Μη έγκυρη τιμή κανόνα: ' + LABEL[kind][key])
        if typ == 'period' and v >= nperiods:
            raise ValueError('Μη έγκυρη περίοδος κανόνα: ' + LABEL[kind][key])
    elif typ == 'flag':
        if type(v) != bool:
            raise ValueError('Μη έγκυρη τιμή κανόνα: ' + LABEL[kind][key])
    elif typ == 'pattern':
        if not isinstance(v, list) or any(not isinstance(x, list) or len(x) != 2 or any(type(n) != int or n < 0 for n in x) for x in v):
            raise ValueError('Μη έγκυρο μοτίβο ημερών.')
        if sum(x[1] for x in v) > 5 or len({x[0] for x in v}) != len(v):
            raise ValueError('Το μοτίβο ημερών υπερβαίνει τις 5 ημέρες ή επαναλαμβάνει πλήθος ωρών.')


# ---------------------------------------------------------------- βοηθητικά
def mapping(p, k):
    return {x['id']: x for x in p[k]}


def all_slots(p):
    return {(d, i) for d in range(5) for i in range(len(p['periods']))}


def mask(p, kind, eid):
    r = p.get(RULE_KEYS[kind], {}).get(eid, {})
    return set(map(tuple, r['allowed'])) if 'allowed' in r else all_slots(p)


def avoid(p, kind, eid):
    r = p.get(RULE_KEYS[kind], {}).get(eid, {})
    return set(map(tuple, r.get('avoid', []))), int(r.get('avoid_w', 3) or 3)


def rule(p, kind, eid, key):
    return norm(p.get(RULE_KEYS[kind], {}).get(eid, {}).get(key))


def name_of(p, k, i):
    for x in p[k]:
        if x['id'] == i:
            return x['name']
    return i


def lesson_label(p, l):
    s = name_of(p, 'subjects', l['subject'])
    parts = [s, ', '.join(name_of(p, 'classes', c) for c in l['classes']) or 'χωρίς τμήμα',
             ', '.join(name_of(p, 'teachers', t) for t in l['teachers'])]
    return ' – '.join(parts)


def period_label(p, i):
    per = p['periods'][i]
    return per['name'] + 'η ώρα (' + per['start'] + '–' + per['end'] + ')'


def forbid_keys(p, l, d, i, earliest):
    """Κανόνες που απαγορεύουν να ξεκινήσει η ανάθεση l στη θέση (d,i)."""
    keys = []
    if d not in l['days']:
        keys.append(('days', l['id']))
    cover = [(d, j) for j in range(i, i + l['duration'])]
    ents = [('subjects', l['subject'])] + [('teachers', t) for t in l['teachers']] + [('classes', c) for c in l['classes']]
    for kind, eid in ents:
        m = mask(p, kind, eid)
        if any(c not in m for c in cover):
            keys.append(('avail', kind, eid))
    for t in l['teachers']:
        e = earliest.get(t)
        if e is not None and i < e['v']:
            keys.append(('rule', 'teachers', t, 'earliest'))
    return keys


def earliest_map(p):
    out = {}
    for t in p['teachers']:
        r = rule(p, 'teachers', t['id'], 'earliest')
        if r:
            out[t['id']] = r
    return out


def candidates(p, l):
    """Επιτρεπτές θέσεις έναρξης (υποχρεωτικοί κανόνες θέσης). Το 'earliest' ως επιθυμητό δεν αποκλείει."""
    n = len(p['periods']); em = {t: r for t, r in earliest_map(p).items() if r['w'] == 0}
    return [(d, i) for d in range(5) for i in range(n - l['duration'] + 1) if not forbid_keys(p, l, d, i, em)]


def resources(p, l):
    out = {'t:' + t for t in l['teachers']}
    if l.get('room'):
        out.add('r:' + l['room'])
    groups = mapping(p, 'groups')
    for cid in l['classes']:
        divisions = defaultdict(list)
        for g in groups.values():
            if g['classid'] == cid and g['entireclass'] != '1':
                divisions[g['divisiontag']].append(g['id'])
        if not divisions:
            out.add('c:' + cid); continue
        combos = list(itertools.product(*divisions.values()))
        if len(combos) > 128:
            raise ValueError('Πάρα πολλοί συνδυασμοί ομάδων τμήματος.')
        selected = [groups[g] for g in l['groups'] if groups[g]['classid'] == cid]
        whole = not selected or any(g['entireclass'] == '1' for g in selected)
        for combo in combos:
            if whole or any(g['id'] in combo for g in selected):
                out.add('c:' + cid + ':' + ','.join(combo))
    return out


def teacher_hours(p):
    h = Counter()
    for l in p['lessons']:
        for t in l['teachers']:
            h[t] += l['hours']
    return h


def available_days(p, t):
    m = mask(p, 'teachers', t)
    return sorted({d for d, _ in m})


def subject_limit(p, s):
    return rule(p, 'subjects', s, 'max_per_day')


# ---------------------------------------------------------------- περιγραφές
def describe(p, key):
    """Ελληνική περιγραφή κλειδιού κανόνα (για διάγνωση και αναφορές)."""
    tag = key[0]
    if tag == 'days':
        l = mapping(p, 'lessons').get(key[1])
        return 'Επιτρεπόμενες ημέρες της ανάθεσης «' + (lesson_label(p, l) if l else key[1]) + '»'
    if tag == 'avail':
        what = {'teachers': 'εκπαιδευτικού', 'classes': 'τμήματος', 'subjects': 'μαθήματος'}[key[1]]
        return 'Διαθεσιμότητα ' + what + ' «' + name_of(p, key[1], key[2]) + '»'
    if tag == 'locked':
        e = next((e for e in p['events'] if e['id'] == key[1]), None)
        l = mapping(p, 'lessons').get(e['lesson']) if e else None
        where = (p['days'][e['place'][0]] + ' ' + period_label(p, e['place'][1])) if e and e['place'] else ''
        return 'Κλειδωμένη θέση: ' + (lesson_label(p, l) if l else key[1]) + (' · ' + where if where else '')
    if tag == 'lesson_max':
        l = mapping(p, 'lessons').get(key[1])
        return 'Μέγιστες ώρες/ημέρα της ανάθεσης «' + (lesson_label(p, l) if l else key[1]) + '»'
    if tag == 'start_counts':
        return name_of(p, 'teachers', key[1]) + ': ακριβής αριθμός ημερών έναρξης'
    if tag == 'rule':
        kind, eid, rk = key[1], key[2], key[3]
        r = norm(p.get(RULE_KEYS[kind], {}).get(eid, {}).get(rk))
        val = ''
        if r:
            typ = TYPES[kind][rk]
            if typ == 'period':
                val = ' ' + p['periods'][r['v']]['start' if rk == 'earliest' else 'end'] if r['v'] < len(p['periods']) else ''
            elif typ == 'pattern':
                val = ' ' + ', '.join(str(x) + ' ημ. με ' + str(n) + ' ώρες' for n, x in r['v'])
            elif typ == 'int':
                val = ' ' + str(r['v'])
        return name_of(p, kind, eid) + ': ' + LABEL[kind][rk] + val
    if tag == 'collision':
        return 'Σύγκρουση εκπαιδευτικού/τμήματος'
    return str(key)


# ---------------------------------------------------------------- έλεγχος (Python)
def evaluate(p, complete=False):
    """Επιστρέφει λίστα ευρημάτων {key, hard, amount, penalty, text}.
    Οι κανόνες «ίσο/τουλάχιστον» ελέγχονται μόνο όταν complete=True."""
    ls = mapping(p, 'lessons'); n = len(p['periods'])
    found = []

    def add(key, r, amount, text):
        if amount <= 0:
            return
        hard = r is None or r['w'] == 0
        found.append(dict(key=key, hard=hard, amount=amount,
                          penalty=0 if hard else WEIGHTS[r['w']] * amount, text=text))

    domains = {k: set(candidates(p, l)) for k, l in ls.items()}
    res = {k: resources(p, l) for k, l in ls.items()}
    occ = {}
    tocc = defaultdict(set); cocc = defaultdict(set)
    lesson_daily = Counter(); subj_daily = Counter(); subj_teacher_day = set()
    avoid_amount = Counter()
    avoids = {}
    for kind, items in (('teachers', p['teachers']), ('classes', p['classes']), ('subjects', p['subjects'])):
        for x in items:
            a, w = avoid(p, kind, x['id'])
            if a:
                avoids[kind, x['id']] = (a, w)
    em = earliest_map(p)
    for e in p['events']:
        l = ls[e['lesson']]; pos = e['place']
        if pos is None:
            if complete:
                add(('unplaced', e['id']), None, 1, 'Ατοποθέτητη διδασκαλία: ' + lesson_label(p, l))
            continue
        d, i = pos
        if tuple(pos) not in domains[l['id']]:
            keys = forbid_keys(p, l, d, i, {t: r for t, r in em.items() if r['w'] == 0})
            add(('outside', e['id']), None, 1, 'Εκτός επιτρεπτών θέσεων: ' + lesson_label(p, l) + ' · ' +
                p['days'][d] + ' ' + p['periods'][i]['name'] + 'η ώρα' + (' (' + '; '.join(describe(p, k) for k in keys) + ')' if keys else ''))
        for j in range(i, i + l['duration']):
            for resource in res[l['id']]:
                kk = (resource, d, j)
                if kk in occ:
                    other = ls[next(x for x in p['events'] if x['id'] == occ[kk])['lesson']]
                    add(('collision', tuple(sorted((e['id'], occ[kk])))), None, 1,
                        'Σύγκρουση: ' + lesson_label(p, l) + ' / ' + lesson_label(p, other) + ' · ' + p['days'][d] + ' ' + p['periods'][j]['name'] + 'η ώρα')
                occ[kk] = e['id']
            for t in l['teachers']:
                tocc[t, d].add(j)
                if ('teachers', t) in avoids and (d, j) in avoids['teachers', t][0]:
                    avoid_amount['teachers', t] += 1
            for c in l['classes']:
                cocc[c, d].add(j)
                if ('classes', c) in avoids and (d, j) in avoids['classes', c][0]:
                    avoid_amount['classes', c] += 1
            if ('subjects', l['subject']) in avoids and (d, j) in avoids['subjects', l['subject']][0]:
                avoid_amount['subjects', l['subject']] += 1
        lesson_daily[l['id'], d] += l['duration']
        if not l.get('exempt_subject_limit'):
            for c in l['classes']:
                subj_daily[l['subject'], c, d] += 1
        for t in l['teachers']:
            subj_teacher_day.add((l['subject'], t, d))

    for (kind, eid), amount in avoid_amount.items():
        w = avoids[kind, eid][1]
        add(('avoid', kind, eid), {'w': w}, amount, name_of(p, kind, eid) + ': ' + str(amount) + ' ώρες σε θέσεις «υπό όρους» (?)')

    for l in ls.values():
        if l.get('max_daily'):
            for d in range(5):
                over = lesson_daily[l['id'], d] - l['max_daily']
                add(('lesson_max', l['id']), None, over, 'Υπέρβαση ημερήσιου ορίου ανάθεσης: ' + lesson_label(p, l) + ' · ' + p['days'][d])

    hours_total = teacher_hours(p)
    for t in p['teachers']:
        tid = t['id']; tn = t['name']
        R = {k: rule(p, 'teachers', tid, k) for k in LABEL['teachers']}
        hs, gs = [], []
        for d in range(5):
            used = tocc[tid, d]; h = len(used)
            g = (max(used) - min(used) + 1 - h) if used else 0
            hs.append(h); gs.append(g)
        key = lambda k: ('rule', 'teachers', tid, k)
        if R['max_daily']:
            add(key('max_daily'), R['max_daily'], sum(max(0, h - R['max_daily']['v']) for h in hs), tn + ': υπέρβαση μέγιστων ωρών ανά ημέρα (' + str(R['max_daily']['v']) + ')')
        if R['max_gaps_day']:
            add(key('max_gaps_day'), R['max_gaps_day'], sum(max(0, g - R['max_gaps_day']['v']) for g in gs), tn + ': υπέρβαση κενών ανά ημέρα (' + str(R['max_gaps_day']['v']) + ')')
        if R['max_gaps_week']:
            add(key('max_gaps_week'), R['max_gaps_week'], max(0, sum(gs) - R['max_gaps_week']['v']), tn + ': υπέρβαση κενών εβδομάδας (' + str(R['max_gaps_week']['v']) + ')')
        if R['max_consecutive']:
            v = R['max_consecutive']['v']; amount = 0
            for d in range(5):
                used = tocc[tid, d]
                for s in range(0, n - v):
                    amount += max(0, sum(1 for i in range(s, s + v + 1) if i in used) - v)
            add(key('max_consecutive'), R['max_consecutive'], amount, tn + ': περισσότερες από ' + str(v) + ' συνεχόμενες ώρες')
        if complete:
            if R['min_daily']:
                add(key('min_daily'), R['min_daily'], sum(max(0, R['min_daily']['v'] - h) for h in hs if h), tn + ': ημέρα με λιγότερες από ' + str(R['min_daily']['v']) + ' ώρες')
            if R['presence']:
                target = R['presence']['v'] - hours_total[tid]
                add(key('presence'), R['presence'], abs(sum(gs) - target),
                    tn + ': παρουσία ' + str(sum(hs) + sum(gs)) + ' ώρες αντί για ' + str(R['presence']['v']))
            if R['day_pattern']:
                amount = sum(abs(sum(1 for h in hs if h == nh) - x) for nh, x in R['day_pattern']['v'])
                add(key('day_pattern'), R['day_pattern'], amount, tn + ': το μοτίβο ' + ', '.join(str(x) + '×' + str(nh) + 'ωρο' for nh, x in R['day_pattern']['v']) + ' δεν τηρείται (ημέρες: ' + '-'.join(map(str, hs)) + ')')
            if R['balance']:
                D = available_days(p, tid) or list(range(5)); H = hours_total[tid]
                lo, hi = H // len(D), -(-H // len(D))
                amount = sum(max(0, lo - hs[d]) + max(0, hs[d] - hi) for d in D)
                add(key('balance'), R['balance'], amount, tn + ': άνιση κατανομή ωρών στις ημέρες (' + '-'.join(map(str, hs)) + ')')
            rr = p.get('teacher_rules', {}).get(tid, {})
            starts = Counter(min(tocc[tid, d]) for d in range(5) if tocc[tid, d])
            for i, count in rr.get('start_counts', {}).items():
                add(('start_counts', tid), None, abs(starts[int(i)] - count), tn + ': μη τήρηση αριθμού ημερών έναρξης')
        if R['earliest'] and R['earliest']['w']:
            amount = sum(1 for d in range(5) for i in tocc[tid, d] if i < R['earliest']['v'])
            add(key('earliest'), R['earliest'], amount, tn + ': ώρες πριν από ' + p['periods'][R['earliest']['v']]['start'])

    for c in p['classes']:
        r = rule(p, 'classes', c['id'], 'compact')
        if r:
            m = mask(p, 'classes', c['id']); amount = 0
            for d in range(5):
                A = sorted(i for dd, i in m if dd == d); used = cocc[c['id'], d]
                amount += sum(max(0, (A[k + 1] in used) - (A[k] in used)) for k in range(len(A) - 1))
            add(('rule', 'classes', c['id'], 'compact'), r, amount, c['name'] + ': κενό ή καθυστερημένη έναρξη στο πρόγραμμα του τμήματος')

    for s in p['subjects']:
        r = subject_limit(p, s['id'])
        if r:
            for c in p['classes']:
                for d in range(5):
                    over = subj_daily[s['id'], c['id'], d] - r['v']
                    add(('rule', 'subjects', s['id'], 'max_per_day'), r, over,
                        s['name'] + ': ' + str(subj_daily[s['id'], c['id'], d]) + ' φορές ' + p['days'][d] + ' στο τμήμα ' + c['name'] + ' (μέγιστο ' + str(r['v']) + ')')
        r = rule(p, 'subjects', s['id'], 'day_end')
        if r:
            for t in p['teachers']:
                for d in range(5):
                    if (s['id'], t['id'], d) in subj_teacher_day:
                        late = sum(1 for i in tocc[t['id'], d] if i > r['v'])
                        add(('rule', 'subjects', s['id'], 'day_end'), r, late,
                            t['name'] + ': έχει ' + s['name'] + ' ' + p['days'][d] + ' αλλά διδάσκει μετά τις ' + p['periods'][r['v']]['end'])

    # Συγχώνευση ευρημάτων ίδιου κλειδιού (π.χ. ίδιο μάθημα σε πολλές ημέρες)
    merged = {}
    for f in found:
        k = (f['key'], f['text']) if f['key'][0] == 'rule' and f['key'][1] == 'subjects' else f['key']
        if k in merged:
            merged[k]['amount'] += f['amount']; merged[k]['penalty'] += f['penalty']
        else:
            merged[k] = dict(f)
    return list(merged.values())


def gap_total(p, exclude_presence=True):
    """Σύνολο κενών εκπαιδευτικών (μέρος του γενικού στόχου)."""
    ls = mapping(p, 'lessons'); tocc = defaultdict(set)
    for e in p['events']:
        if e['place']:
            l = ls[e['lesson']]
            for t in l['teachers']:
                for j in range(e['place'][1], e['place'][1] + l['duration']):
                    tocc[t, e['place'][0]].add(j)
    total = 0
    for t in p['teachers']:
        if exclude_presence and rule(p, 'teachers', t['id'], 'presence'):
            continue
        for d in range(5):
            u = tocc[t['id'], d]
            if u:
                total += max(u) - min(u) + 1 - len(u)
    return total


def gap_weight(p):
    g = p.get('global_rules', {}).get('min_gaps', {'w': 1, 'on': True})
    if not g.get('on', True):
        return 0
    return WEIGHTS.get(int(g.get('w', 1) or 1), 1)


def score(p):
    """Συνολική ποινή πλήρους προγράμματος (ίδια με τον στόχο του solver)."""
    found = evaluate(p, True)
    return sum(f['penalty'] for f in found if not f['hard']) + gap_weight(p) * gap_total(p)


# ---------------------------------------------------------------- μοντέλο CP-SAT
def build(p, cp_model, diag=False):
    """Χτίζει το μοντέλο. Με diag=True κάθε υποχρεωτικός κανόνας ελέγχεται από
    λογική μεταβλητή-υπόθεση, ώστε να εντοπιστούν οι κανόνες που συγκρούονται."""
    model = cp_model.CpModel(); ls = mapping(p, 'lessons'); n = len(p['periods'])
    lits = {}
    terms = []  # (συντελεστής, μεταβλητή) στόχου

    def gate(key):
        if key not in lits:
            lits[key] = model.NewBoolVar('A%d' % len(lits))
        return lits[key]

    def hard(key, ct):
        if diag:
            ct.OnlyEnforceIf(gate(key))
        return ct

    def soft(weight, lo_expr, ub, name='viol'):
        """Προσθέτει viol >= lo_expr, viol >= 0 στον στόχο με βάρος."""
        v = model.NewIntVar(0, max(0, ub), name)
        model.Add(v >= lo_expr)
        terms.append((weight, v))
        return v

    def apply(key, r, expr_le, bound, ub):
        """expr_le <= bound, υποχρεωτικό ή επιθυμητό."""
        if r['w'] == 0:
            hard(key, model.Add(expr_le <= bound))
        else:
            soft(WEIGHTS[r['w']], expr_le - bound, ub)

    em = earliest_map(p)
    hard_em = {t: r for t, r in em.items() if r['w'] == 0}
    res = {k: resources(p, l) for k, l in ls.items()}
    avoids = {}
    for kind, items in (('teachers', p['teachers']), ('classes', p['classes']), ('subjects', p['subjects'])):
        for x in items:
            a, w = avoid(p, kind, x['id'])
            if a:
                avoids[kind, x['id']] = (a, WEIGHTS[w])
    choices = {}; occupancy = defaultdict(list); lesson_days = defaultdict(list)
    subj_day = defaultdict(list); subj_teacher_day = defaultdict(list); class_slot = defaultdict(list)
    for e in p['events']:
        l = ls[e['lesson']]; options = []
        for d in range(5):
            for i in range(n - l['duration'] + 1):
                keys = forbid_keys(p, l, d, i, hard_em)
                if e['locked'] and [d, i] != e['place']:
                    keys = keys + [('locked', e['id'])]
                if keys and not diag:
                    continue
                v = model.NewBoolVar('x')
                for k in keys:
                    hard(k, model.Add(v == 0))
                options.append((d, i, v))
                if e['place'] == [d, i]:
                    model.AddHint(v, 1)
                cost = STAY_WEIGHT if e.get('stay') and e['place'] and e['place'] != [d, i] else 0
                for j in range(i, i + l['duration']):
                    for resource in res[l['id']]:
                        occupancy[resource, d, j].append(v)
                    for t in l['teachers']:
                        if ('teachers', t) in avoids and (d, j) in avoids['teachers', t][0]:
                            cost += avoids['teachers', t][1]
                    for c in l['classes']:
                        class_slot[c, d, j].append(v)
                        if ('classes', c) in avoids and (d, j) in avoids['classes', c][0]:
                            cost += avoids['classes', c][1]
                    if ('subjects', l['subject']) in avoids and (d, j) in avoids['subjects', l['subject']][0]:
                        cost += avoids['subjects', l['subject']][1]
                if cost:
                    terms.append((cost, v))
                lesson_days[l['id'], d].append(v)
                if not l.get('exempt_subject_limit'):
                    for c in l['classes']:
                        subj_day[l['subject'], c, d].append(v)
                for t in l['teachers']:
                    subj_teacher_day[l['subject'], t, d].append(v)
        if not options:
            return dict(empty=e, lesson=l)
        choices[e['id']] = options
        model.AddExactlyOne([v for _, _, v in options])
    for vs in occupancy.values():
        if len(vs) > 1:
            model.AddAtMostOne(vs)
    for l in ls.values():
        if l.get('max_daily'):
            for d in range(5):
                vs = lesson_days[l['id'], d]
                if len(vs) * l['duration'] > l['max_daily']:
                    hard(('lesson_max', l['id']), model.Add(sum(l['duration'] * v for v in vs) <= l['max_daily']))

    # ---- εκπαιδευτικοί
    hours_total = teacher_hours(p); gw = gap_weight(p)
    tocc = {}
    for t in p['teachers']:
        tid = t['id']
        R = {k: rule(p, 'teachers', tid, k) for k in LABEL['teachers']}
        key = lambda k: ('rule', 'teachers', tid, k)
        rr = p.get('teacher_rules', {}).get(tid, {})
        weekgaps = []; firsts = defaultdict(list); hs = []; occs = []
        for d in range(5):
            occ = []
            for i in range(n):
                vs = occupancy['t:' + tid, d, i]
                v = model.NewBoolVar('occ')
                if vs:
                    model.Add(v == sum(vs))
                else:
                    model.Add(v == 0)
                occ.append(v)
            occs.append(occ); tocc[tid, d] = occ
            active = model.NewBoolVar('active'); model.AddMaxEquality(active, occ)
            h = sum(occ); hs.append((h, active))
            dg = []
            for i in range(n):
                before = model.NewBoolVar('before'); after = model.NewBoolVar('after')
                if i:
                    model.AddMaxEquality(before, occ[:i])
                else:
                    model.Add(before == 0)
                if i < n - 1:
                    model.AddMaxEquality(after, occ[i + 1:])
                else:
                    model.Add(after == 0)
                gap = model.NewBoolVar('gap')
                model.Add(gap <= before); model.Add(gap <= after); model.Add(gap + occ[i] <= 1)
                model.Add(gap >= before + after - occ[i] - 1); dg.append(gap)
                if rr.get('start_counts'):
                    first = model.NewBoolVar('first'); model.Add(first <= occ[i]); model.Add(first + before <= 1)
                    model.Add(first >= occ[i] - before); firsts[i].append(first)
            if R['max_daily']:
                apply(key('max_daily'), R['max_daily'], h, R['max_daily']['v'], n)
            if R['min_daily']:
                v = R['min_daily']['v']
                if R['min_daily']['w'] == 0:
                    hard(key('min_daily'), model.Add(h >= v * active))
                else:
                    soft(WEIGHTS[R['min_daily']['w']], v * active - h, v)
            if R['max_gaps_day']:
                apply(key('max_gaps_day'), R['max_gaps_day'], sum(dg), R['max_gaps_day']['v'], n)
            if R['max_consecutive']:
                v = R['max_consecutive']['v']
                for s in range(0, n - v):
                    apply(key('max_consecutive'), R['max_consecutive'], sum(occ[s:s + v + 1]), v, 1)
            weekgaps.extend(dg)
        if R['max_gaps_week']:
            apply(key('max_gaps_week'), R['max_gaps_week'], sum(weekgaps), R['max_gaps_week']['v'], 5 * n)
        for i, count in rr.get('start_counts', {}).items():
            hard(('start_counts', tid), model.Add(sum(firsts[int(i)]) == count))
        if R['presence']:
            target = R['presence']['v'] - hours_total[tid]
            if R['presence']['w'] == 0:
                hard(key('presence'), model.Add(sum(weekgaps) == target))
            else:
                w = WEIGHTS[R['presence']['w']]
                soft(w, sum(weekgaps) - target, 5 * n + abs(target))
                soft(w, target - sum(weekgaps), 5 * n + abs(target))
        elif gw:
            for g in weekgaps:
                terms.append((gw, g))
        if R['day_pattern']:
            for nh, x in R['day_pattern']['v']:
                bs = []
                for h, _ in hs:
                    b = model.NewBoolVar('pat'); lt = model.NewBoolVar('lt')
                    model.Add(h == nh).OnlyEnforceIf(b)
                    model.Add(h <= nh - 1).OnlyEnforceIf([b.Not(), lt])
                    model.Add(h >= nh + 1).OnlyEnforceIf([b.Not(), lt.Not()])
                    bs.append(b)
                if R['day_pattern']['w'] == 0:
                    hard(key('day_pattern'), model.Add(sum(bs) == x))
                else:
                    w = WEIGHTS[R['day_pattern']['w']]
                    soft(w, sum(bs) - x, 5); soft(w, x - sum(bs), 5)
        if R['balance']:
            D = available_days(p, tid) or list(range(5)); H = hours_total[tid]
            lo, hi = H // len(D), -(-H // len(D))
            for d in D:
                h = hs[d][0]
                if R['balance']['w'] == 0:
                    hard(key('balance'), model.Add(h >= lo)); hard(key('balance'), model.Add(h <= hi))
                else:
                    w = WEIGHTS[R['balance']['w']]
                    soft(w, lo - h, n); soft(w, h - hi, n)
        if R['earliest'] and R['earliest']['w']:
            w = WEIGHTS[R['earliest']['w']]
            for d in range(5):
                for i in range(R['earliest']['v']):
                    terms.append((w, occs[d][i]))

    # ---- τμήματα
    for c in p['classes']:
        r = rule(p, 'classes', c['id'], 'compact')
        if not r:
            continue
        m = mask(p, 'classes', c['id'])
        for d in range(5):
            A = sorted(i for dd, i in m if dd == d); cv = {}
            for i in A:
                vs = class_slot[c['id'], d, i]; b = model.NewBoolVar('cocc')
                if vs:
                    model.AddMaxEquality(b, vs)
                else:
                    model.Add(b == 0)
                cv[i] = b
            for k in range(len(A) - 1):
                apply(('rule', 'classes', c['id'], 'compact'), r, cv[A[k + 1]] - cv[A[k]], 0, 1)

    # ---- μαθήματα
    for s in p['subjects']:
        r = subject_limit(p, s['id'])
        if r:
            for c in p['classes']:
                for d in range(5):
                    vs = subj_day[s['id'], c['id'], d]
                    if len(vs) > r['v']:
                        apply(('rule', 'subjects', s['id'], 'max_per_day'), r, sum(vs), r['v'], len(vs))
        r = rule(p, 'subjects', s['id'], 'day_end')
        if r:
            for t in p['teachers']:
                for d in range(5):
                    vs = subj_teacher_day[s['id'], t['id'], d]
                    if not vs:
                        continue
                    z = model.NewBoolVar('z'); model.AddMaxEquality(z, vs)
                    for i in range(r['v'] + 1, n):
                        apply(('rule', 'subjects', s['id'], 'day_end'), r, tocc[t['id'], d][i] + z, 1, 1)
    if terms:
        model.Minimize(sum(c * v for c, v in terms))
    return dict(model=model, choices=choices, lits=lits)


def solve(p, seconds=30, cancel=None, diagnose=True):
    from ortools.sat.python import cp_model
    import threading, copy
    p = copy.deepcopy(p)
    built = build(p, cp_model)
    if 'empty' in built:
        msg = 'Καμία επιτρεπτή θέση για: ' + lesson_label(p, built['lesson']) + '.'
        reasons = diagnose_rules(p, cp_model, 20, cancel) if diagnose else []
        return dict(status='infeasible', message=msg, reasons=reasons)
    model = built['model']; choices = built['choices']
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = seconds; solver.parameters.num_search_workers = 4
    done = threading.Event()

    def watch():
        while not done.wait(.1):
            if cancel and cancel.is_set():
                solver.StopSearch(); return
    threading.Thread(target=watch, daemon=True).start()
    try:
        status = solver.Solve(model)
    finally:
        done.set()
    if cancel and cancel.is_set():
        return dict(status='cancelled', message='Η παραγωγή ακυρώθηκε. Το προηγούμενο πρόγραμμα διατηρήθηκε.')
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.INFEASIBLE:
            reasons = diagnose_rules(p, cp_model, min(60, max(20, seconds)), cancel) if diagnose else []
            return dict(status='infeasible', message='Αποδείχθηκε ότι οι υποχρεωτικοί κανόνες δεν επιτρέπουν λύση.', reasons=reasons)
        return dict(status='unknown', message='Δεν βρέθηκε λύση στον διαθέσιμο χρόνο. Αυτό δεν αποδεικνύει αδυναμία λύσης. Δοκιμάστε μεγαλύτερο χρόνο ή μετατρέψτε κάποιους κανόνες σε επιθυμητούς.')
    for e in p['events']:
        e['place'] = next([d, i] for d, i, v in choices[e['id']] if solver.Value(v))
    return dict(status='optimal' if status == cp_model.OPTIMAL else 'feasible', project=p,
                objective=round(solver.ObjectiveValue()))


def diagnose_rules(p, cp_model, seconds=30, cancel=None):
    """Εντοπίζει ένα μικρό σύνολο υποχρεωτικών κανόνων που μαζί δεν επιτρέπουν λύση."""
    import time
    t0 = time.time()
    built = build(p, cp_model, diag=True)
    model = built['model']; lits = built['lits']
    if not lits:
        return []
    keys = list(lits)
    by_index = {lits[k].Index(): k for k in keys}

    def infeasible(active, limit):
        model.ClearAssumptions(); model.AddAssumptions([lits[k] for k in active])
        s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = max(1.0, limit); s.parameters.num_search_workers = 1
        st = s.Solve(model)
        return st, s
    st, s = infeasible(keys, seconds / 2)
    if st != cp_model.INFEASIBLE:
        return []
    core = [by_index[i] for i in s.SufficientAssumptionsForInfeasibility() if i in by_index] or keys
    # Ελαχιστοποίηση με αφαίρεση, εντός χρονικού ορίου
    if len(core) <= 40:
        for k in list(core):
            if time.time() - t0 > seconds or (cancel and cancel.is_set()):
                break
            trial = [x for x in core if x != k]
            st2, _ = infeasible(trial, 5)
            if st2 == cp_model.INFEASIBLE:
                core = trial
    return [describe(p, k) for k in core]
