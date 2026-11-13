"""Στοιχεία για τη Διεύθυνση και «Διεύθυνση & έντυπα».

Όλα αποθηκεύονται στο έργο, στο p['admin'] (προαιρετικό). Τίποτα από αυτά δεν πιάνει θέση
στο ωρολόγιο πρόγραμμα: Ε.Δ.Υ., βιβλιοθήκη, γραμματειακή/ενισχυτική/παράλληλη μετρούν μόνο στο
ωράριο του εκπαιδευτικού και στα έντυπα της Διεύθυνσης. Το Ολοήμερο και η Πρωινή Ζώνη διαβάζονται
από το πρόγραμμα (είναι τμήματα, όπως στο aSc).
"""
import re, unicodedata
from collections import defaultdict
import core

GRADES6 = ['Α', 'Β', 'Γ', 'Δ', 'Ε', 'ΣΤ']
EXTRA_KINDS = ['ενισχυτική', 'παράλληλη', 'γραμματειακή', 'υπερωριακή', 'άλλο']
# Ειδικά προγράμματα (0.28): πιάνουν τον εκπαιδευτικό (όχι το τμήμα), μετρούν στο ωράριο του, μπαίνουν με το χέρι
# σε ώρες του προγράμματος αφού αυτό βγει, χωρίς να μετακινείται τίποτα (ο solver τα αγνοεί).
SPECIAL_KINDS = {'entaxi': ('Τμήμα Ένταξης', 'ΕΝΤΑΞΗ'), 'zep': ('Τάξη Υποδοχής ΖΕΠ', 'ΖΕΠ'), 'enisx': ('Ενισχυτική διδασκαλία', 'ΕΝΙΣΧΥΤΙΚΗ'),
                 'parall': ('Παράλληλη στήριξη', 'ΠΑΡΑΛΛΗΛΗ'), 'gramm': ('Γραμματειακή υποστήριξη', 'ΓΡΑΜΜΑΤΕΙΑΚΗ')}
SPECIAL_LAST = ('entaxi', 'zep', 'parall')   # όσοι έχουν μόνο αυτά πάνε στο τέλος του εντύπου
# Κλάδοι του «Προϋπολογισμού αναγκών», με τη σειρά του προτύπου. Ο πρώτος κωδικός είναι αυτός του εντύπου.
KLADOI = [('ΠΕ70', 'Δασκάλων', ()), ('ΠΕ08', 'Καλλιτεχνικών', ()), ('ΠΕ79.01', 'Μουσικής', ('ΠΕ16', 'ΠΕ79')),
          ('ΠΕ91.01', 'Θεατρικών Σπουδών', ('ΠΕ32', 'ΠΕ91')), ('ΠΕ11', 'Φυσικής Αγωγής', ()), ('ΠΕ06', 'Αγγλικών', ()),
          ('ΠΕ05', 'Γαλλικών', ()), ('ΠΕ07', 'Γερμανικών', ()), ('ΠΕ86', 'Πληροφορικής', ('ΠΕ19-20', 'ΠΕ19', 'ΠΕ20'))]
TITLES = {'ΠΕ70': 'Δασ.', 'ΠΕ11': 'Φ. Αγ.', 'ΠΕ06': 'Αγγ.', 'ΠΕ86': 'ΤΠΕ', 'ΠΕ05': 'Γαλ.', 'ΠΕ07': 'Γερ.',
          'ΠΕ08': 'Εικαστ.', 'ΠΕ79.01': 'Μουσ.', 'ΠΕ91.01': 'Θεατρ.', 'ΠΕ60': 'Νηπ.'}
SPEC_ORDER = ['ΠΕ70', 'ΠΕ11', 'ΠΕ06', 'ΠΕ86', 'ΠΕ05', 'ΠΕ07', 'ΠΕ08', 'ΠΕ79.01', 'ΠΕ91.01']
# Πρότυπο ωρών ανά τάξη και κλάδο (όπως στο κοινό αρχείο «Προϋπολογισμός αναγκών»· επεξεργάσιμο)
NEEDS_HOURS = {'ΠΕ70': [21, 21, 20, 20, 20, 20], 'ΠΕ08': [2, 2, 1, 1, 1, 1], 'ΠΕ79.01': [1, 1, 1, 1, 1, 1], 'ΠΕ91.01': [1, 1, 1, 1, 0, 0],
               'ΠΕ11': [3, 3, 3, 3, 2, 2], 'ΠΕ06': [2, 2, 3, 3, 3, 3], 'ΠΕ05': [0, 0, 0, 0, 2, 2], 'ΠΕ07': [0, 0, 0, 0, 2, 2],
               'ΠΕ86': [1, 1, 1, 1, 1, 1]}
DEFAULTS = {'ministry': 'ΥΠΟΥΡΓΕΙΟ ΠΑΙΔΕΙΑΣ, ΘΡΗΣΚΕΥΜΑΤΩΝ & ΑΘΛΗΤΙΣΜΟΥ', 'region': '', 'directorate': '', 'city': '', 'date': '',
            'approver': 'Η Προϊσταμένη Εκπαιδευτικών Θεμάτων', 'director_title': 'Ο ΔΙΕΥΘΥΝΤΗΣ ΤΟΥ ΣΧΟΛΕΙΟΥ', 'school_form': '',
            'edy': 1}
TEXT_KEYS = ('ministry', 'region', 'directorate', 'city', 'date', 'approver', 'director_title', 'school_form')


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).upper()
    return re.sub(r'\s+', ' ', ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')).strip()


def upper(s):
    """Κεφαλαία χωρίς τόνους (όπως στα έντυπα)."""
    return norm(s)


def klados_code(raw):
    """Κανονικός κωδικός κλάδου του εντύπου από ό,τι έχει γραφτεί (π.χ. «ΠΕ 86» → «ΠΕ86», «ΠΕ16» → «ΠΕ79.01»)."""
    t = norm(raw).replace(' ', '').replace('PE', 'ΠΕ')
    m = re.match(r'ΠΕ(\d+)(?:[.,](\d+))?(?:-(\d+))?', t)
    if not m:
        return ''
    base = 'ΠΕ' + m.group(1).zfill(2)
    code = base + ('.' + m.group(2) if m.group(2) else '') + ('-' + m.group(3) if m.group(3) else '')
    for main, _, alias in KLADOI:
        if code == main or base == main or code in alias or base in alias:
            return main
    return code


def guess_klados(p, t):
    """Κλάδος από την ειδικότητα, αλλιώς από τα μαθήματα που διδάσκει (γενικά μαθήματα τάξης → ΠΕ70)."""
    k = klados_code(t.get('spec', ''))
    if k:
        return k
    subj = core.mapping(p, 'subjects'); C = core.mapping(p, 'classes'); cnt = defaultdict(int)
    for l in p['lessons']:
        if t['id'] in l['teachers'] and l['subject'] in subj:
            k = subject_klados(subj[l['subject']]['name'])
            if not k and any(c in C and core.grade_of(C[c]) for c in l['classes']):
                k = 'ΠΕ70'
            if not k and any(c in C and not core.grade_of(C[c]) for c in l['classes']):
                k = 'ΠΕ70?'
            if k:
                cnt[k] += l['hours']
    if any(c.get('teacher') == t['id'] for c in p['classes']) or (t.get('role') in ('director', 'deputy') and not cnt and core.level(p) == 'Δημοτικό'):
        return 'ΠΕ70'
    cnt.pop('ΠΕ70?', None) if len(cnt) > 1 else None
    best = max(cnt, key=cnt.get) if cnt else ''
    return 'ΠΕ70' if best == 'ΠΕ70?' else best


def subject_klados(name):
    n = norm(name)
    if 'ΑΓΓΛ' in n: return 'ΠΕ06'
    if 'ΓΑΛΛ' in n: return 'ΠΕ05'
    if 'ΓΕΡΜ' in n: return 'ΠΕ07'
    if 'ΕΙΚΑΣΤ' in n: return 'ΠΕ08'
    if 'ΜΟΥΣ' in n: return 'ΠΕ79.01'
    if 'ΘΕΑΤΡ' in n: return 'ΠΕ91.01'
    if re.search(r'ΦΥΣ\w*\.? ?ΑΓ|^Φ\.? ?ΑΓ|ΓΥΜΝ', n): return 'ΠΕ11'
    if re.search(r'Τ\.?Π\.?Ε|ΠΛΗΡΟΦ', n): return 'ΠΕ86'
    return ''


def get(p):
    """Τα αποθηκευμένα στοιχεία με τις προεπιλογές συμπληρωμένες (αντίγραφο)."""
    a = dict(DEFAULTS); a.update({k: v for k, v in (p.get('admin') or {}).items()})
    a['teachers'] = {k: dict(v) for k, v in (a.get('teachers') or {}).items()}
    a['library'] = dict(a.get('library') or {'teacher': '', 'hours': 3})
    a['students'] = dict(a.get('students') or {})
    a['allday'] = dict(a.get('allday') or {})
    a['needs'] = dict(a.get('needs') or {})
    if not a.get('school_form'):
        a['school_form'] = upper(p.get('school', ''))
    return a


def validate(p, ids):
    a = p.get('admin')
    if a is None:
        return
    if not isinstance(a, dict):
        raise ValueError('Μη έγκυρα στοιχεία Διεύθυνσης.')
    for k in TEXT_KEYS:
        if k in a and (not isinstance(a[k], str) or len(a[k]) > 200):
            raise ValueError('Μη έγκυρο κείμενο στα στοιχεία Διεύθυνσης.')
    if 'edy' in a and (type(a['edy']) != int or not 0 <= a['edy'] <= 10):
        raise ValueError('Μη έγκυρες ώρες Ε.Δ.Υ.')
    el = a.get('edy_list', [])
    if not isinstance(el, list) or any(not isinstance(x, dict) or (x.get('teacher') and x['teacher'] not in ids['teachers']) or type(x.get('hours', 0)) != int or not 0 <= x.get('hours', 0) <= 10 for x in el):
        raise ValueError('Μη έγκυρες ώρες Ε.Δ.Υ.')
    ll = a.get('library_list', [])
    if not isinstance(ll, list) or len(ll) > 50 or any(not isinstance(x, dict) or (x.get('teacher') and x['teacher'] not in ids['teachers']) or type(x.get('hours', 0)) != int or not 0 <= x.get('hours', 0) <= 20 for x in ll):
        raise ValueError('Μη έγκυρα στοιχεία βιβλιοθήκης.')
    lib = a.get('library')
    if lib is not None:
        if not isinstance(lib, dict) or (lib.get('teacher') and lib['teacher'] not in ids['teachers']) or type(lib.get('hours', 0)) != int or not 0 <= lib.get('hours', 0) <= 20:
            raise ValueError('Μη έγκυρα στοιχεία βιβλιοθήκης.')
    for tid, d in (a.get('teachers') or {}).items():
        if tid not in ids['teachers'] or not isinstance(d, dict):
            raise ValueError('Στοιχεία Διεύθυνσης για άγνωστο εκπαιδευτικό.')
        for k in ('klados', 'title', 'note'):
            if k in d and (not isinstance(d[k], str) or len(d[k]) > (200 if k == 'note' else 20)):
                raise ValueError('Μη έγκυρο πεδίο εκπαιδευτικού (' + k + ').')
        if 'duty' in d and d['duty'] not in (None, '', 0, 1, 2, 3, 4):
            raise ValueError('Μη έγκυρη ημέρα εφημερίας.')
        if 'other' in d and (type(d['other']) != int or not 0 <= d['other'] <= 40):
            raise ValueError('Μη έγκυρες ώρες σε άλλο σχολείο.')
        for x in d.get('extras') or []:
            if not isinstance(x, dict) or x.get('kind') not in EXTRA_KINDS or type(x.get('hours')) != int or not 0 <= x['hours'] <= 40 or len(str(x.get('text', ''))) > 80:
                raise ValueError('Μη έγκυρη πρόσθετη απασχόληση.')
    for cid, n in (a.get('students') or {}).items():
        if cid not in ids['classes'] or type(n) != int or not 0 <= n <= 99:
            raise ValueError('Μη έγκυρος αριθμός μαθητών.')
    ad = a.get('allday') or {}
    if not isinstance(ad, dict):
        raise ValueError('Μη έγκυρα στοιχεία Ολοήμερου.')
    if ad.get('responsible') and ad['responsible'] not in ids['teachers']:
        raise ValueError('Άγνωστος υπεύθυνος Ολοήμερου.')
    for s in ad.get('sections') or []:
        if not isinstance(s, dict) or s.get('class') not in ids['classes'] or s.get('kind', 'allday') not in ('allday', 'morning'):
            raise ValueError('Μη έγκυρο τμήμα Ολοήμερου / Πρωινής Ζώνης.')
        for k in ('label', 'grades', 'subject'):
            if len(str(s.get(k, ''))) > 60:
                raise ValueError('Πολύ μεγάλο κείμενο τμήματος Ολοήμερου.')
        if not isinstance(s.get('by_period', {}), dict):
            raise ValueError('Μη έγκυρες τάξεις ανά ώρα.')
    for row in ad.get('student_rows') or []:
        if not isinstance(row, dict) or not isinstance(row.get('counts', {}), dict) or any(type(v) != int or not 0 <= v <= 999 for v in row.get('counts', {}).values()):
            raise ValueError('Μη έγκυρος αριθμός μαθητών Ολοήμερου.')
    nd = a.get('needs') or {}
    if not isinstance(nd, dict):
        raise ValueError('Μη έγκυρος προϋπολογισμός αναγκών.')
    for k, v in (nd.get('hours') or {}).items():
        if not isinstance(v, list) or len(v) != 6 or any(type(x) != int or not 0 <= x <= 40 for x in v):
            raise ValueError('Μη έγκυρο πρότυπο ωρών.')
    for k, v in (nd.get('sections') or {}).items():
        if type(v) != int or not 0 <= v <= 20:
            raise ValueError('Μη έγκυρος αριθμός τμημάτων.')
    for k, v in (nd.get('extra') or {}).items():
        if type(v) != int or not 0 <= v <= 400:
            raise ValueError('Μη έγκυρες πρόσθετες ώρες.')
    if nd.get('year', 'current') not in ('current', 'next'):
        raise ValueError('Μη έγκυρο έτος προϋπολογισμού.')
    for k, lo, hi in (('new_students', 0, 999), ('max_students', 1, 40), ('allday_sections', 0, 30), ('morning_sections', 0, 30)):
        if k in nd and nd[k] is not None and (type(nd[k]) != int or not lo <= nd[k] <= hi):
            raise ValueError('Μη έγκυρη τιμή στον προϋπολογισμό (' + k + ').')
    if not isinstance(nd.get('leaving', []), list) or any(t not in ids['teachers'] for t in nd.get('leaving', [])):
        raise ValueError('Μη έγκυροι εκπαιδευτικοί που αποχωρούν.')
    pr = a.get('programs') or {}
    if not isinstance(pr, dict) or any(k not in SPECIAL_KINDS or type(v) != bool for k, v in pr.items()):
        raise ValueError('Μη έγκυρες ρυθμίσεις ειδικών προγραμμάτων.')
    if not isinstance(a.get('specials', []), list):
        raise ValueError('Μη έγκυρα ειδικά προγράμματα.')
    seen = set(); n = len(p['periods'])
    for x in a.get('specials', []):
        if not isinstance(x, dict) or not isinstance(x.get('id'), str) or not 0 < len(x['id']) <= 40 or x['id'] in seen:
            raise ValueError('Μη έγκυρο ειδικό πρόγραμμα.')
        seen.add(x['id'])
        if x.get('kind') not in SPECIAL_KINDS or x.get('teacher') not in ids['teachers']:
            raise ValueError('Ειδικό πρόγραμμα χωρίς είδος ή εκπαιδευτικό.')
        if not isinstance(x.get('classes', []), list) or any(c not in ids['classes'] for c in x.get('classes', [])):
            raise ValueError('Άγνωστο τμήμα σε ειδικό πρόγραμμα.')
        if type(x.get('hours')) != int or not 1 <= x['hours'] <= 30 or len(str(x.get('note', ''))) > 80:
            raise ValueError('Μη έγκυρες ώρες ειδικού προγράμματος.')
        sl = x.get('slots', [])
        if not isinstance(sl, list) or len(sl) > x['hours'] or len({tuple(v) for v in sl if isinstance(v, list)}) != len(sl) or \
                any(not isinstance(v, list) or len(v) != 2 or type(v[0]) != int or type(v[1]) != int or not 0 <= v[0] <= 4 or not 0 <= v[1] < n for v in sl):
            raise ValueError('Μη έγκυρες θέσεις ειδικού προγράμματος.')


# ------------------------------------------------------------------ υπολογισμοί
def counted_hours(p):
    """Ώρες εκτός προγράμματος που καλύπτουν ωράριο: {teacher_id: (ώρες, περιγραφή)} — Ε.Δ.Υ. (διευθυντής) και βιβλιοθήκη."""
    a = p.get('admin') or {}; out = {}
    for tid, h in edy_map(p).items():
        out[tid] = (h, str(h) + ' Ε.Δ.Υ.')
    for tid, lh in lib_map(p).items():
        h, txt = out.get(tid, (0, ''))
        out[tid] = (h + lh, (txt + ' + ' if txt else '') + str(lh) + ' βιβλιοθήκη')
    for x in specials(p):
        h, txt = out.get(x['teacher'], (0, ''))
        out[x['teacher']] = (h + x['hours'], (txt + ' + ' if txt else '') + str(x['hours']) + ' ' + SPECIAL_KINDS[x['kind']][0].lower())
    return out


def lib_map(p):
    """Ώρες σχολικής βιβλιοθήκης ανά εκπαιδευτικό. Λίστα admin['library_list'] [{teacher, hours}] (ένας ή περισσότεροι)·
    αλλιώς το παλιό admin['library'] {teacher, hours} (ένας)."""
    a = p.get('admin') or {}; out = defaultdict(int); ids = {t['id'] for t in p['teachers']}
    if 'library_list' in a:
        L = a['library_list'] or []
    else:
        L = [a['library']] if isinstance(a.get('library'), dict) else []
    for x in L:
        if x.get('teacher') in ids and x.get('hours'):
            out[x['teacher']] += x['hours']
    return dict(out)


def lib_hours(p):
    """Σύνολο ωρών βιβλιοθήκης (για τον προϋπολογισμό· χωρίς λίστα: οι ώρες της ρύθμισης, προεπιλογή 3)."""
    a = p.get('admin') or {}
    if 'library_list' in a:
        return sum(x.get('hours') or 0 for x in a['library_list'] or [])
    return get(p)['library'].get('hours') or 0


def edy_map(p):
    """Ώρες Ε.Δ.Υ. ανά εκπαιδευτικό (μόνο Δημοτικό). Με τη λίστα admin['edy_list'] [{teacher, hours}] μπορούν να
    είναι περισσότεροι (π.χ. διευθυντής και εκπαιδευτικός Τμήματος Ένταξης)· αλλιώς ο διευθυντής παίρνει admin['edy'] (προεπιλογή 1)."""
    if ((p.get('framework') or {}).get('level') or 'Δημοτικό') != 'Δημοτικό':
        return {}
    a = p.get('admin') or {}; out = defaultdict(int); ids = {t['id'] for t in p['teachers']}
    if 'edy_list' in a:
        for x in a['edy_list'] or []:
            if x.get('teacher') in ids and x.get('hours'):
                out[x['teacher']] += x['hours']
    else:
        edy = a.get('edy', DEFAULTS['edy']) or 0
        for t in p['teachers']:
            if edy and t.get('role') == 'director':
                out[t['id']] += edy
    return dict(out)


def specials(p):
    """Τα ειδικά προγράμματα των ενεργών ειδών (Ναι στις ρυθμίσεις)."""
    a = p.get('admin') or {}; on = a.get('programs') or {}
    return [x for x in a.get('specials') or [] if on.get(x.get('kind'))]


def special_text(p, x):
    C = core.mapping(p, 'classes')
    cls = ', '.join((C[c].get('short') or C[c]['name']) for c in x.get('classes', []) if c in C)
    return SPECIAL_KINDS[x['kind']][0] + (' (' + cls + ')' if cls else '') + (' — ' + x['note'] if x.get('note') else '')


def special_conflicts(p):
    """Θέσεις ειδικών προγραμμάτων που συμπίπτουν με μάθημα ή άλλο ειδικό πρόγραμμα του ίδιου εκπαιδευτικού."""
    L = core.mapping(p, 'lessons'); busy = defaultdict(list); out = []
    for e in p['events']:
        l = L.get(e['lesson'])
        if l and e.get('place'):
            for t in l['teachers']:
                for j in range(e['place'][1], e['place'][1] + l['duration']):
                    busy[(t, e['place'][0], j)].append('lesson')
    for x in specials(p):
        for d, i in x.get('slots', []):
            if busy[(x['teacher'], d, i)]:
                out.append({'id': x['id'], 'teacher': x['teacher'], 'slot': [d, i],
                            'text': core.mapping(p, 'teachers')[x['teacher']]['name'] + ': ' + p['days'][d] + ' ' + p['periods'][i]['name'] + 'η ώρα — ' + SPECIAL_KINDS[x['kind']][0] + ' συμπίπτει με ' + ('μάθημα' if 'lesson' in busy[(x['teacher'], d, i)] else 'άλλο ειδικό πρόγραμμα')})
            busy[(x['teacher'], d, i)].append('special')
    return out


def with_specials(p):
    """Αντίγραφο του έργου με τα τοποθετημένα ειδικά προγράμματα ως κλειδωμένες «διδασκαλίες» (μόνο για εκτυπώσεις
    εκπαιδευτικών· δεν αποθηκεύεται και δεν το βλέπει ο solver)."""
    sp = [x for x in specials(p) if x.get('slots')]
    if not sp:
        return p
    q = dict(p); q['subjects'] = list(p['subjects']); q['lessons'] = list(p['lessons']); q['events'] = list(p['events'])
    for k, (label, short) in SPECIAL_KINDS.items():
        q['subjects'].append({'id': '__sp_' + k, 'name': short, 'short': short[:5]})
    for x in sp:
        lid = '__spl_' + x['id']
        q['lessons'].append({'id': lid, 'subject': '__sp_' + x['kind'], 'teachers': [x['teacher']], 'classes': list(x.get('classes', [])), 'groups': [],
                             'room': '', 'hours': len(x['slots']), 'duration': 1, 'days': [0, 1, 2, 3, 4], 'max_daily': 0, 'special': True})
        for k, (d, i) in enumerate(x['slots']):
            q['events'].append({'id': lid + '_' + str(k), 'lesson': lid, 'place': [d, i], 'locked': True})
    return q


def grade_classes(p):
    order = {g: i for i, g in enumerate(core.GRADES)}
    cs = [c for c in p['classes'] if core.grade_of(c)]
    return sorted(cs, key=lambda c: (order.get(core.grade_of(c), 99), c.get('short') or c['name']))


def section_classes(p):
    """Τμήματα χωρίς τάξη: Ολοήμερο / Πρωινή Ζώνη (με αυτόματη αναγνώριση από το όνομα)."""
    out = []
    for c in p['classes']:
        if core.grade_of(c):
            continue
        n = norm(c['name'] + ' ' + (c.get('short') or ''))
        kind = 'morning' if ('ΠΡΩΙΝ' in n or re.search(r'\bΠ\.?Ζ', n)) else ('allday' if ('ΟΛ' in n or 'ΑΠΟΓ' in n) else '')
        if kind:
            out.append((c, kind))
    return out


def sections(p):
    """Τμήματα Ολοήμερου/Πρωινής Ζώνης με τη σειρά των εντύπων: αποθηκευμένα + όσα βρέθηκαν αυτόματα."""
    a = get(p); C = core.mapping(p, 'classes'); saved = [dict(s) for s in a['allday'].get('sections') or [] if s.get('class') in C]
    have = {s['class'] for s in saved}
    for c, kind in sorted(section_classes(p), key=lambda x: (x[1] != 'allday', x[0]['name'])):
        if c['id'] not in have:
            saved.append({'class': c['id'], 'kind': kind, 'label': '', 'grades': '', 'by_period': {}, 'subject': ''})
    k = 0
    for s in saved:
        s.setdefault('kind', 'allday'); s.setdefault('by_period', {}); s.setdefault('grades', ''); s.setdefault('subject', '')
        if s['kind'] == 'allday':
            k += 1
        if not s.get('label'):
            s['label'] = 'ΤΜΗΜΑ ' + str(k) if s['kind'] == 'allday' else 'ΤΜΗΜΑ ΠΡ. ΖΩΝΗΣ'
        s['name'] = C[s['class']]['name']
    return saved


def teacher_order(p, rows):
    """Διευθυντής, υποδιευθυντής, δάσκαλοι τάξεων (με τη σειρά των τάξεων), λοιποί ΠΕ70, ειδικότητες."""
    def key(r):
        t = r['t']; role = t.get('role', '')
        if role == 'director': return (0, 0, '')
        if role == 'deputy': return (1, 0, '')
        if r['homeroom_idx'] is not None: return (2, r['homeroom_idx'], '')
        k = r['klados']
        if r.get('special_only'): return (5, SPEC_ORDER.index(k) if k in SPEC_ORDER else 99, norm(t['name']))
        return (3 if k == 'ΠΕ70' else 4, SPEC_ORDER.index(k) if k in SPEC_ORDER else 99, norm(t['name']))
    return sorted(rows, key=key)


def teacher_rows(p):
    """Μία γραμμή ανά ενεργό εκπαιδευτικό με όλα τα στοιχεία του εντύπου «Ω.Π. και διδακτικό ωράριο»."""
    a = get(p); S = core.mapping(p, 'subjects'); C = core.mapping(p, 'classes'); gcs = grade_classes(p); gids = {c['id'] for c in gcs}
    secs = sections(p); sec_ids = {s['class']: s for s in secs}
    homeroom = {}
    for i, c in enumerate(gcs):
        if c.get('teacher') and c['teacher'] not in homeroom:
            homeroom[c['teacher']] = (i, c)
    libs = lib_map(p); rows = []; sps = specials(p); edys = edy_map(p)
    for t in p['teachers']:
        if t.get('active') is False or t.get('hypothetical'):
            continue
        d = a['teachers'].get(t['id'], {}); role = t.get('role', '')
        by_class = defaultdict(int); allday = morning = 0; noclass = defaultdict(int); lab = defaultdict(int)
        for l in p['lessons']:
            if t['id'] not in l['teachers']:
                continue
            sname = S[l['subject']]['name'] if l['subject'] in S else ''
            g = [c for c in l['classes'] if c in gids]
            if g:
                by_class[g[0]] += l['hours']
                if 'ΕΡΓΑΣΤ' in norm(sname):
                    lab[g[0]] += l['hours']
            elif any(c in sec_ids for c in l['classes']):
                s = next(sec_ids[c] for c in l['classes'] if c in sec_ids)
                if s['kind'] == 'morning': morning += l['hours']
                else: allday += l['hours']
            elif not l['classes']:
                noclass[sname] += l['hours']
        kl = klados_code(d['klados']) or d['klados'] if d.get('klados') else guess_klados(p, t)
        title = d.get('title') or ('Δ/ντης' if role == 'director' else 'Υποδ/ντης' if role == 'deputy' else TITLES.get(kl, t.get('spec', '') or ''))
        extras = [x for x in d.get('extras') or [] if x.get('hours')]
        extra_hours = sum(x['hours'] for x in extras) + sum(noclass.values())
        notes = []
        if lab and kl != 'ΠΕ70' and role != 'director':
            notes.append(str(sum(lab.values())) + ' Εργ Δεξ (' + ', '.join(str(h) + '-' + (C[c].get('short') or C[c]['name']) for c, h in lab.items()) + ')')
        for x in extras:
            notes.append(str(x['hours']) + ' ' + (x.get('text') or x['kind']))
        for sname, h in noclass.items():
            notes.append(str(h) + ' ' + sname.lower())
        mysp = [x for x in sps if x['teacher'] == t['id']]
        for x in mysp:
            notes.append(str(x['hours']) + ' ' + special_text(p, x))
        extra_hours += sum(x['hours'] for x in mysp)
        if d.get('note'):
            notes.append(d['note'])
        hr = homeroom.get(t['id'])
        duty = d.get('duty')
        rows.append({'t': t, 'id': t['id'], 'name': t['name'], 'title': title, 'klados': kl, 'duty': core.DAYS[duty] if isinstance(duty, int) and 0 <= duty <= 4 else '',
                     'homeroom': (hr[1].get('short') or hr[1]['name']) if hr else '', 'homeroom_idx': hr[0] if hr else None,
                     'students': a['students'].get(hr[1]['id']) if hr else None, 'years': t.get('years'), 'required': core.required_hours(p, t),
                     'by_class': dict(by_class), 'allday': allday + morning, 'other': 0,
                     'library': libs.get(t['id'], 0),
                     'edy': edys.get(t['id'], 0), 'extra': extra_hours, 'notes': ', '.join(n for n in notes if n),
                     'special_only': bool(not by_class and not allday and not morning and hr is None and role not in ('director', 'deputy')
                                         and any(x['kind'] in SPECIAL_LAST for x in mysp))})
    return teacher_order(p, rows)


def allday_matrix(p):
    """Ολοήμερο/Πρωινή Ζώνη από το πρόγραμμα: για κάθε τμήμα, ημέρα και ώρα, ποιοι διδάσκουν ποιο μάθημα."""
    secs = sections(p); L = core.mapping(p, 'lessons'); T = core.mapping(p, 'teachers'); S = core.mapping(p, 'subjects')
    idx = {s['class']: i for i, s in enumerate(secs)}
    cells = defaultdict(list)   # (sec_index, day, period) -> [(teacher_ids, subject_name)]
    hours = defaultdict(lambda: defaultdict(int))   # teacher -> sec_index -> hours
    for l in p['lessons']:
        mine = [c for c in l['classes'] if c in idx]
        if not mine:
            continue
        si = idx[mine[0]]
        for tid in l['teachers']:
            hours[tid][si] += l['hours']
        for e in p['events']:
            if e['lesson'] == l['id'] and e['place']:
                d, i = e['place']
                for j in range(i, i + l['duration']):
                    cells[(si, d, j)].append((l['teachers'], S[l['subject']]['name'] if l['subject'] in S else ''))
    periods = sorted({k[2] for k in cells if secs[k[0]]['kind'] == 'allday'})
    mperiods = sorted({k[2] for k in cells if secs[k[0]]['kind'] == 'morning'})
    return {'sections': secs, 'cells': cells, 'hours': {t: dict(v) for t, v in hours.items()}, 'periods': periods, 'morning_periods': mperiods, 'T': T}


def next_year(y):
    m = re.match(r'\s*(\d{4})\s*[-–/]\s*(\d{2,4})', str(y or ''))
    if not m:
        return 'επόμενο σχολικό έτος'
    a = int(m.group(1)) + 1
    return str(a) + '-' + str(a + 1)


def needs(p):
    """Προϋπολογισμός αναγκών: απαιτούμενες και διαθέσιμες ώρες ανά κλάδο, έλλειμμα (−) / πλεόνασμα (+).
    Με nd['year'] == 'next' γίνεται εκτίμηση για το επόμενο σχολικό έτος: οι μαθητές κάθε τάξης «ανεβαίνουν»
    (νέα Α΄ = εγγραφές), τα τμήματα βγαίνουν από το όριο μαθητών, τα έτη υπηρεσίας +1 και όσοι αποχωρούν δεν μετρούν."""
    a = get(p); nd = a['needs']; nxt = nd.get('year') == 'next'
    cur = {g: 0 for g in GRADES6}; stud = {g: None for g in GRADES6}
    for c in grade_classes(p):
        g = core.grade_of(c)
        if g in cur:
            cur[g] += 1
            n = a['students'].get(c['id'])
            if n is not None:
                stud[g] = (stud[g] or 0) + n
    maxs = nd.get('max_students') or 25
    sec = dict(cur); stud_next = {g: None for g in GRADES6}
    if nxt:
        for k, g in enumerate(GRADES6):
            n = nd.get('new_students') if k == 0 else stud[GRADES6[k - 1]]
            stud_next[g] = n
            if n is not None:
                sec[g] = -(-n // maxs) if n else 0
            else:
                sec[g] = cur['Α'] if k == 0 else cur[GRADES6[k - 1]]
    auto_sec = dict(sec)
    sec.update({k: v for k, v in (nd.get('sections') or {}).items() if k in sec})
    hours = {k: list(v) for k, v in NEEDS_HOURS.items()}
    for k, v in (nd.get('hours') or {}).items():   # και παλιοί κωδικοί (ΠΕ16, ΠΕ32, ΠΕ19-20)
        k = klados_code(k) or k
        if k in hours:
            hours[k] = list(v)
    # Γαλλικά/Γερμανικά Ε΄ και ΣΤ΄: τμήματα ανά γλώσσα (προεπιλογή από τις αναθέσεις του έργου)
    lang = {'fr5': 0, 'de5': 0, 'fr6': 0, 'de6': 0}
    S = core.mapping(p, 'subjects'); C = core.mapping(p, 'classes')
    for l in p['lessons']:
        k = subject_klados(S[l['subject']]['name']) if l['subject'] in S else ''
        for c in l['classes']:
            g = core.grade_of(C[c]) if c in C else ''
            if k in ('ΠΕ05', 'ΠΕ07') and g in ('Ε', 'ΣΤ'):
                lang[('fr' if k == 'ΠΕ05' else 'de') + ('5' if g == 'Ε' else '6')] += 1
    if nxt:   # η κατανομή γλωσσών της Δ΄/Ε΄ περνά στην επόμενη τάξη· νέα Ε΄ ίδια αναλογία με τα τμήματα
        lang = {'fr6': lang['fr5'], 'de6': lang['de5'], 'fr5': min(lang['fr5'], sec['Ε']) if lang['fr5'] else 0, 'de5': min(lang['de5'], sec['Ε']) if lang['de5'] else 0}
    lang.update({k: v for k, v in (nd.get('sections') or {}).items() if k in lang})
    # Ολοήμερο / Πρωινή Ζώνη: από το πρόγραμμα, κλιμακωμένα με τον αριθμό τμημάτων του σεναρίου
    m = allday_matrix(p); rows = {r['id']: r for r in teacher_rows(p)}
    ac = sum(1 for s_ in m['sections'] if s_['kind'] == 'allday'); mc = sum(1 for s_ in m['sections'] if s_['kind'] == 'morning')
    an = nd.get('allday_sections'); an = ac if an is None else an
    mn = nd.get('morning_sections'); mn = mc if mn is None else mn
    morning = allday70 = meal = 0; spec = defaultdict(int)
    meal_p = m['periods'][0] if m['periods'] else None
    for tid, per in m['hours'].items():
        kl = rows.get(tid, {}).get('klados') or 'ΠΕ70'
        for si, h in per.items():
            if m['sections'][si]['kind'] == 'morning':
                morning += h
            elif kl != 'ΠΕ70':
                spec[kl] += h
            else:
                allday70 += h
    if meal_p is not None:
        meal = sum(len(tids) for k, v in m['cells'].items() if k[2] == meal_p and m['sections'][k[0]]['kind'] == 'allday' for tids, _ in v)
    meal = min(meal, allday70); study = max(0, allday70 - meal)
    fa = (an / ac) if ac else None; fm = (mn / mc) if mc else None
    sc = lambda h, f, per_new: round(h * f) if f is not None else per_new
    extra = {'morning': sc(morning, fm, 5 * mn), 'meal': sc(meal, fa, 5 * an), 'study': sc(study, fa, 10 * an), 'library': lib_hours(p)}
    spec = {k: (round(v * fa) if fa is not None else 0) for k, v in spec.items()}
    extra.update({k: v for k, v in (nd.get('extra') or {}).items() if k in extra})
    req = {}; base = {}; addon = defaultdict(int)
    for code, _, _ in KLADOI:
        h = hours[code]
        if code == 'ΠΕ05':
            base[code] = h[4] * lang['fr5'] + h[5] * lang['fr6']
        elif code == 'ΠΕ07':
            base[code] = h[4] * lang['de5'] + h[5] * lang['de6']
        else:
            base[code] = sum(h[i] * sec[g] for i, g in enumerate(GRADES6))
    addon['ΠΕ70'] = extra['morning'] + extra['meal'] + extra['study'] + extra['library']
    for k, v in spec.items():
        addon[k] += v
    for code in base:
        req[code] = base[code] + addon[code]
    # Διαθέσιμες ώρες: υποχρεωτικό ωράριο (στο επόμενο έτος: έτη +1, χωρίς όσους αποχωρούν)
    leaving = set(nd.get('leaving') or []) if nxt else set()
    have = defaultdict(int); staff = defaultdict(list)
    for r in rows.values():
        if r['id'] in leaving or not r['klados']:
            continue
        t = r['t']
        if nxt and t.get('years') is not None:
            t = dict(t, years=t['years'] + 1)
        rq = core.required_hours(p, t)
        if rq is not None:   # το υποχρεωτικό ωράριο είναι ήδη οι ώρες στο σχολείο
            have[r['klados']] += rq; staff[r['klados']].append(r['name'])
    other_addon = sorted(k for k in addon if k not in base)
    out = [{'code': code, 'label': label, 'base': base[code], 'addon': addon.get(code, 0), 'required': req[code], 'available': have.get(code, 0),
            'balance': have.get(code, 0) - req[code], 'staff': staff.get(code, [])} for code, label, _ in KLADOI]
    for k in other_addon:   # κλάδοι εκτός προτύπου που διδάσκουν στο Ολοήμερο
        out.append({'code': k, 'label': '', 'base': 0, 'addon': addon[k], 'required': addon[k], 'available': have.get(k, 0), 'balance': have.get(k, 0) - addon[k], 'staff': staff.get(k, [])})
    known = {x['code'] for x in out}
    other = sorted(k for k in have if k not in known)
    total_req = sum(x['required'] for x in out)
    return {'year': 'next' if nxt else 'current', 'year_label': next_year(p.get('year')) if nxt else (p.get('year') or 'τρέχον σχολικό έτος'),
            'sections': sec, 'auto_sections': auto_sec, 'current_sections': cur, 'students': stud, 'students_next': stud_next,
            'max_students': maxs, 'new_students': nd.get('new_students'), 'leaving': sorted(leaving),
            'allday_sections': an, 'morning_sections': mn, 'current_allday': ac, 'current_morning': mc,
            'lang': lang, 'hours': hours, 'extra': extra, 'spec': spec, 'rows': out,
            'other': [{'code': k, 'available': have[k], 'staff': staff[k]} for k in other],
            'total_required': total_req, 'total_available': sum(have.values()), 'total_balance': sum(have.values()) - total_req}


def info(p):
    """Όλα όσα χρειάζεται η οθόνη «Διεύθυνση & έντυπα»."""
    rows = teacher_rows(p); a = get(p)
    pub = [{k: v for k, v in r.items() if k != 't'} for r in rows]
    return {'admin': {k: v for k, v in a.items()}, 'teachers': pub, 'sections': sections(p), 'needs': needs(p),
            'classes': [{'id': c['id'], 'name': c['name'], 'short': c.get('short') or c['name'], 'grade': core.grade_of(c)} for c in grade_classes(p)],
            'kinds': EXTRA_KINDS, 'kladoi': [k for k, _, _ in KLADOI], 'periods_allday': allday_matrix(p)['periods'],
            'special_kinds': [[k, v[0], v[1]] for k, v in SPECIAL_KINDS.items()], 'conflicts': special_conflicts(p)}


# ------------------------------------------------------------------ σύνδεση με «Εφημερίες»
def efimeries_days(db_path):
    """Ημέρα εφημερίας ανά εκπαιδευτικό από βάση της εφαρμογής «Εφημερίες» (μόνο ανάγνωση).
    Κύρια ημέρα αν έχει οριστεί, αλλιώς η πιο συχνή ημέρα στις ημερήσιες εφημερίες."""
    import sqlite3
    from datetime import date
    con = sqlite3.connect('file:' + str(db_path) + '?mode=ro', uri=True)
    try:
        cols = {r[1] for r in con.execute('PRAGMA table_info(teachers)')}
        if 'name' not in cols:
            raise ValueError('Το αρχείο δεν είναι βάση της εφαρμογής «Εφημερίες».')
        out = {}
        prim = 'primary_day' in cols
        for row in con.execute('SELECT id, name' + (', primary_day' if prim else '') + ' FROM teachers'):
            out[row[0]] = {'name': row[1], 'day': row[2] if prim and row[2] is not None and 0 <= row[2] <= 4 else None, 'source': 'κύρια ημέρα'}
        try:
            cnt = defaultdict(lambda: defaultdict(int))
            for tid, d in con.execute("SELECT teacher_id, d FROM assignments WHERE mode='daily'"):
                try:
                    wd = date.fromisoformat(d).weekday()
                except Exception:
                    continue
                if wd < 5:
                    cnt[tid][wd] += 1
            for tid, c in cnt.items():
                if tid in out and out[tid]['day'] is None:
                    out[tid]['day'] = max(c, key=c.get); out[tid]['source'] = 'πρόγραμμα εφημεριών'
        except sqlite3.Error:
            pass
        return [v for v in out.values() if v['day'] is not None]
    finally:
        con.close()


def match_names(p, found):
    """Αντιστοίχιση ονομάτων (χωρίς τόνους/κεφαλαία, με οποιαδήποτε σειρά επωνύμου/ονόματος)."""
    key = lambda s: ' '.join(sorted(norm(s).replace('.', ' ').split()))
    idx = {key(t['name']): t for t in p['teachers']}
    sur = defaultdict(list)
    for t in p['teachers']:
        w = norm(t['name']).split()
        if w:
            sur[w[0]].append(t)
    out = []
    for f in found:
        t = idx.get(key(f['name']))
        if not t:
            w = norm(f['name']).split()
            cand = [x for x in sur.get(w[0] if w else '', [])] or [x for ws in w for x in sur.get(ws, [])]
            t = cand[0] if len(cand) == 1 else None
        out.append({'name': f['name'], 'day': f['day'], 'source': f['source'], 'teacher': t['id'] if t else '', 'teacher_name': t['name'] if t else ''})
    return out


def efimeries_default_dbs(year):
    """Πιθανές βάσεις «Εφημερίες» στον υπολογιστή (προεπιλεγμένος φάκελος στα Έγγραφα)."""
    import sys
    from pathlib import Path
    docs = None
    if sys.platform.startswith('win'):
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
                docs = Path(buf.value)
        except Exception:
            docs = None
    root = (docs or (Path.home() / 'Documents')) / 'Εφημερίες Εκπαιδευτικών' / 'data'
    out = []
    y = re.sub(r'\s', '', year or '')
    if (root / 'years').exists():
        files = sorted((root / 'years').glob('efimeries_*.db'), key=lambda f: f.stat().st_mtime, reverse=True)
        files.sort(key=lambda f: y not in f.stem)
        out += files
    if (root / 'efimeries.db').exists():
        out.append(root / 'efimeries.db')
    return out
