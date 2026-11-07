"""Βοηθός AI: συνομιλία με γλωσσικό μοντέλο που προτείνει αλλαγές στο πρόγραμμα.

Το μοντέλο ΔΕΝ αλλάζει τα δεδομένα. Δουλεύει σε «πρόχειρο» αντίγραφο με εργαλεία
(μετακίνηση, ανταλλαγή, κανόνες, διαθεσιμότητα, επανυπολογισμός) που ελέγχονται από
την ίδια την εφαρμογή, και αποθηκεύει «προτάσεις». Ο χρήστης εφαρμόζει όποια θέλει.

Ανωνυμοποίηση (προεπιλογή): στο μοντέλο στέλνονται κωδικοί εκπαιδευτικών (Τ1, Τ2…)
αντί για ονόματα· η αντιστοίχιση γίνεται μόνο τοπικά.
Πάροχοι: Anthropic (Messages API) και κάθε υπηρεσία συμβατή με OpenAI
(OpenAI, Google Gemini, Ollama, άλλοι) — μόνο με την τυπική βιβλιοθήκη της Python.
"""
import copy, json, re, time, unicodedata, urllib.request, urllib.error
from pathlib import Path
import core
import rules as R

PROVIDERS = {
    'anthropic': {'label': 'Claude (Anthropic)', 'base': 'https://api.anthropic.com/v1', 'model': 'claude-haiku-5-5', 'key': True,
                  'keyurl': 'https://console.anthropic.com/settings/keys'},
    'openai': {'label': 'ChatGPT (OpenAI)', 'base': 'https://api.openai.com/v1', 'model': 'gpt-5-mini', 'key': True,
               'keyurl': 'https://platform.openai.com/api-keys'},
    'gemini': {'label': 'Gemini (Google)', 'base': 'https://generativelanguage.googleapis.com/v1beta/openai', 'model': 'gemini-2.5-flash-lite', 'key': True,
               'keyurl': 'https://aistudio.google.com/apikey'},
    'ollama': {'label': 'Ollama (τοπικό μοντέλο, δωρεάν)', 'base': 'http://127.0.0.1:11434/v1', 'model': 'qwen3:8b', 'key': False,
               'keyurl': 'https://ollama.com/download'},
    'custom': {'label': 'Άλλη υπηρεσία συμβατή με OpenAI', 'base': '', 'model': '', 'key': True, 'keyurl': ''},
}
MAX_STEPS = 12
TIMEOUT = 180


# ---------------------------------------------------------------- ρυθμίσεις (data/ai.json — μόνο σε αυτόν τον υπολογιστή)
def cfg_path(root):
    return Path(root) / 'data' / 'ai.json'


def load_cfg(root):
    try:
        c = json.loads(cfg_path(root).read_text(encoding='utf-8'))
    except Exception:
        c = {}
    c.setdefault('provider', 'anthropic'); c.setdefault('keys', {}); c.setdefault('models', {}); c.setdefault('bases', {})
    c.setdefault('anonymize', True)
    if c['provider'] not in PROVIDERS:
        c['provider'] = 'anthropic'
    return c


def save_cfg(root, upd):
    c = load_cfg(root); pv = upd.get('provider', c['provider'])
    if pv not in PROVIDERS:
        raise ValueError('Άγνωστος πάροχος.')
    c['provider'] = pv
    if 'model' in upd:
        m = str(upd['model'] or '').strip()[:120]
        if m:
            c['models'][pv] = m
        else:
            c['models'].pop(pv, None)
    if 'base' in upd:
        b = str(upd['base'] or '').strip()[:300]
        if b and not re.match(r'^https?://', b):
            raise ValueError('Η διεύθυνση πρέπει να ξεκινά με http:// ή https://')
        if b:
            c['bases'][pv] = b.rstrip('/')
        else:
            c['bases'].pop(pv, None)
    if upd.get('key') is not None:
        k = str(upd['key']).strip()
        if k:
            c['keys'][pv] = k[:400]
        else:
            c['keys'].pop(pv, None)
    if 'anonymize' in upd:
        c['anonymize'] = bool(upd['anonymize'])
    p = cfg_path(root); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding='utf-8')
    return c


def public_cfg(c):
    """Ό,τι βλέπει η διεπαφή: χωρίς το κλειδί (μόνο τα 4 τελευταία ψηφία)."""
    return {'provider': c['provider'], 'anonymize': c['anonymize'],
            'models': {k: c['models'].get(k) or v['model'] for k, v in PROVIDERS.items()},
            'bases': {k: c['bases'].get(k) or v['base'] for k, v in PROVIDERS.items()},
            'keys': {k: ('…' + c['keys'][k][-4:]) if c['keys'].get(k) else '' for k in PROVIDERS},
            'providers': {k: {x: v[x] for x in ('label', 'key', 'keyurl')} for k, v in PROVIDERS.items()}}


def endpoint(c):
    pv = c['provider']; d = PROVIDERS[pv]
    base = c['bases'].get(pv) or d['base']; model = c['models'].get(pv) or d['model']; key = c['keys'].get(pv, '')
    if not base:
        raise ValueError('Συμπληρώστε τη διεύθυνση της υπηρεσίας στις ρυθμίσεις του βοηθού.')
    if not model:
        raise ValueError('Συμπληρώστε το μοντέλο στις ρυθμίσεις του βοηθού.')
    if d['key'] and not key:
        raise ValueError('Δεν έχει δηλωθεί κλειδί API για ' + d['label'] + '. Ανοίξτε «Ρυθμίσεις» στο παράθυρο του βοηθού.')
    return pv, base, model, key


# ---------------------------------------------------------------- HTTP
def _post(url, body, headers, timeout=TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers={'Content-Type': 'application/json', **headers}, method='POST')
    return _open(req, timeout)


def _get(url, headers, timeout=30):
    return _open(urllib.request.Request(url, headers=headers), timeout)


class ServiceError(ValueError):
    def __init__(self, msg, code=0):
        super().__init__(msg); self.code = code


def _detail(ex):
    """Το μήνυμα λάθους της υπηρεσίας (Anthropic/OpenAI: {error:{message}}, Gemini: [{error:{message}}])."""
    try:
        raw = ex.read().decode('utf-8', 'replace')
    except Exception:
        return ''
    try:
        d = json.loads(raw)
        if isinstance(d, list) and d:
            d = d[0]
        e = d.get('error', d) if isinstance(d, dict) else d
        if isinstance(e, dict):
            return str(e.get('message') or e.get('status') or e)
        return str(e)
    except Exception:
        return ' '.join(raw.split())[:300]


def _open(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as ex:
        detail = _detail(ex)
        msg = {401: 'Το κλειδί API δεν έγινε δεκτό (λάθος ή ανενεργό κλειδί).', 403: 'Η υπηρεσία αρνήθηκε την πρόσβαση με αυτό το κλειδί.',
               404: 'Η υπηρεσία δεν βρήκε το μοντέλο ή τη διεύθυνση· ελέγξτε το όνομα του μοντέλου.',
               429: 'Η υπηρεσία απάντησε «πάρα πολλά αιτήματα» ή «τέλος υπολοίπου». Περιμένετε λίγο ή ελέγξτε τον λογαριασμό σας.',
               529: 'Η υπηρεσία είναι προσωρινά υπερφορτωμένη· δοκιμάστε σε λίγο.'}.get(ex.code, 'Σφάλμα υπηρεσίας AI (' + str(ex.code) + ').')
        raise ServiceError(msg + (' Λεπτομέρειες: ' + str(detail)[:300] if detail else ''), ex.code)
    except urllib.error.URLError as ex:
        raise ValueError('Δεν υπάρχει σύνδεση με την υπηρεσία AI (' + str(ex.reason)[:120] + '). '
                         'Ελέγξτε το Internet' + (' ή ότι το Ollama είναι ανοικτό.' if '11434' in req.full_url else '.'))
    except TimeoutError:
        raise ValueError('Η υπηρεσία AI δεν απάντησε εγκαίρως.')


def list_models(c):
    pv, base, model, key = endpoint({**c, 'models': {**c['models'], c['provider']: c['models'].get(c['provider']) or 'x'}})
    if pv == 'anthropic':
        r = _get(base + '/models?limit=100', {'x-api-key': key, 'anthropic-version': '2023-06-01'})
    else:
        r = _get(base + '/models', {'Authorization': 'Bearer ' + key} if key else {})
    ids = [m.get('id') or m.get('name') for m in r.get('data', r.get('models', []))]
    return sorted({str(i).replace('models/', '') for i in ids if i})


# ---------------------------------------------------------------- ανωνυμοποίηση
def _n(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').upper()


class Codec:
    def __init__(self, p, anonymize=True):
        self.anon = anonymize
        self.tcode = {t['id']: 'Τ' + str(i + 1) for i, t in enumerate(p['teachers'])}
        self.tname = {t['id']: t['name'] for t in p['teachers']}
        self.ecode = {e['id']: 'E' + str(i + 1) for i, e in enumerate(p['events'])}
        self.eid = {v: k for k, v in self.ecode.items()}
        self.lcode = {l['id']: 'L' + str(i + 1) for i, l in enumerate(p['lessons'])}
        self.lid = {v: k for k, v in self.lcode.items()}
        # λέξεις ονομάτων → εκπαιδευτικοί (για την αντικατάσταση στο κείμενο του χρήστη)
        self.words = {}
        for t in p['teachers']:
            for w in re.findall(r'\w+', t['name']):
                if len(w) >= 3:
                    self.words.setdefault(_n(w), set()).add(t['id'])

    def view(self, p):
        """Αντίγραφο του έργου με κωδικούς στη θέση των ονομάτων εκπαιδευτικών."""
        q = copy.deepcopy(p)
        if self.anon:
            for t in q['teachers']:
                t['name'] = self.tcode[t['id']]; t['short'] = self.tcode[t['id']]
            q.pop('school', None); q['title'] = 'Σχολείο'
        return q

    def restore(self, q, original):
        """Επαναφέρει τα πραγματικά ονόματα πριν από την αποθήκευση πρότασης."""
        q = copy.deepcopy(q); orig = {t['id']: t for t in original['teachers']}
        for t in q['teachers']:
            if t['id'] in orig:
                t['name'] = orig[t['id']]['name']; t['short'] = orig[t['id']].get('short', '')
        for k in ('school', 'title'):
            if k in original:
                q[k] = original[k]
            else:
                q.pop(k, None)
        return q

    def encode_text(self, s):
        if not self.anon:
            return s

        def sub(m):
            w = m.group(0); nw = _n(w)
            hits = set()
            for stem, ids in self.words.items():
                if len(stem) <= 4:
                    ok = nw == stem or (nw.startswith(stem) and len(nw) - len(stem) <= 2)
                else:
                    k = max(4, len(stem) - 2)
                    ok = nw[:k] == stem[:k] and abs(len(nw) - len(stem)) <= 3
                if ok:
                    hits |= ids
            if not hits:
                return w
            codes = sorted(self.tcode[i] for i in hits)
            return codes[0] if len(codes) == 1 else '(' + ' ή '.join(codes) + ')'
        return re.sub(r'\w{3,}', sub, s)

    def decode_text(self, s):
        if not self.anon:
            return s
        rev = {v: self.tname[k] for k, v in self.tcode.items()}
        return re.sub(r'(?<!\w)[ΤT](\d+)(?!\w)', lambda m: rev.get('Τ' + m.group(1), m.group(0)), s)


# ---------------------------------------------------------------- περιγραφή σχολείου για το μοντέλο
def _day(p, d):
    return p['days'][d][:3]


def _per(p, i):
    return str(p['periods'][i]['name'])


def _rules_text(p, kind, eid):
    r = p.get(R.RULE_KEYS[kind], {}).get(eid, {}); out = []
    for key, label, typ, _ in R.CATALOG[kind]:
        v = R.norm(r.get(key))
        if not v:
            continue
        val = ('ώρα ' + _per(p, v['v'])) if typ == 'period' and isinstance(v['v'], int) and v['v'] < len(p['periods']) else ('' if typ == 'flag' else str(v['v']))
        out.append(key + '=' + val + ' (' + ('υποχρεωτικός' if v['w'] == 0 else 'επιθυμητός w' + str(v['w'])) + ') «' + label + '»')
    if 'allowed' in r:
        al = set(map(tuple, r['allowed']))
        no = [(d, i) for d in range(5) for i in range(len(p['periods'])) if (d, i) not in al]
        if no:
            out.append('ΜΗ ΔΙΑΘΕΣΙΜΟΣ: ' + _slots_text(p, no))
    if r.get('avoid'):
        out.append('καλύτερα όχι (w' + str(r.get('avoid_w', 3)) + '): ' + _slots_text(p, [tuple(x) for x in r['avoid']]))
    return out


def _slots_text(p, slots):
    by = {}
    for d, i in sorted(slots):
        by.setdefault(d, []).append(_per(p, i))
    return '; '.join(_day(p, d) + ' ' + ','.join(v) for d, v in by.items())


def grid(p, cx, kind, eid):
    ls = core.mapping(p, 'lessons'); cell = {}
    for e in p['events']:
        if not e['place']:
            continue
        l = ls[e['lesson']]
        if kind == 'classes' and eid not in l['classes']:
            continue
        if kind == 'teachers' and eid not in l['teachers']:
            continue
        d, i = e['place']
        for k in range(l.get('duration', 1)):
            s = R.name_of(p, 'subjects', l['subject'])
            if kind == 'classes':
                s += '/' + ','.join(R.name_of(p, 'teachers', t) for t in l['teachers'])
            else:
                s += '/' + (','.join(R.name_of(p, 'classes', c) for c in l['classes']) or 'χωρίς τμήμα')
            s += ' ' + cx.ecode[e['id']] + ('🔒' if e['locked'] else '')
            cell.setdefault((d, i + k), []).append(s)
    rows = []
    for d in range(5):
        rows.append('  ' + _day(p, d) + ': ' + ' | '.join(_per(p, i) + ':' + (' + '.join(cell[(d, i)]) if (d, i) in cell else '—') for i in range(len(p['periods']))))
    return '\n'.join(rows)


def context(p, cx):
    """Το «σχολείο» σε συμπαγές κείμενο. p = ανωνυμοποιημένη όψη."""
    L = []
    L.append('Βαθμίδα: ' + core.level(p) + '. Ημέρες: ' + ', '.join(str(i + 1) + '=' + d for i, d in enumerate(p['days'])) + '.')
    L.append('Ώρες: ' + ', '.join(_per(p, i) + ' (' + x['start'] + '–' + x['end'] + ')' for i, x in enumerate(p['periods'])) + '.')
    th = core.teacher_hours_check(p)
    L.append('\n## Εκπαιδευτικοί')
    for t in p['teachers']:
        extra = []
        if t.get('spec'):
            extra.append(t['spec'])
        if t.get('active') is False:
            extra.append('ΔΕΝ συμμετέχει')
        h = sum(l['hours'] for l in p['lessons'] if t['id'] in l['teachers'])
        req = th.get(t['id'], {}).get('required')
        extra.append(str(h) + ' ώρες' + ('/υποχρ. ' + str(req) if req is not None else ''))
        L.append('- ' + t['name'] + ' (' + ', '.join(extra) + ')' + ''.join('\n    ' + x for x in _rules_text(p, 'teachers', t['id'])))
    L.append('\n## Μαθήματα (κανόνες)')
    for s in p['subjects']:
        rt = _rules_text(p, 'subjects', s['id'])
        if rt:
            L.append('- ' + s['name'] + ''.join('\n    ' + x for x in rt))
    L.append('\n## Αναθέσεις (κωδικός: μάθημα – τμήματα – εκπαιδευτικοί · ώρες/εβδ · διάρκεια · διδασκαλίες)')
    for l in p['lessons']:
        evs = [cx.ecode[e['id']] + '@' + (_day(p, e['place'][0]) + _per(p, e['place'][1]) if e['place'] else 'ΧΩΡΙΣ ΘΕΣΗ') + ('🔒' if e['locked'] else '')
               for e in p['events'] if e['lesson'] == l['id']]
        L.append('- ' + cx.lcode[l['id']] + ': ' + R.lesson_label(p, l) + ' · ' + str(l['hours']) + 'ώ' + (' · δίωρο' if l.get('duration', 1) > 1 else '') + ' · ' + ' '.join(evs))
    L.append('\n## Πρόγραμμα ανά τμήμα (ώρα:μάθημα/εκπαιδευτικοί κωδικός διδασκαλίας)')
    for c in p['classes']:
        L.append(c['name'] + ':' + ''.join('\n' + x for x in _rules_text(p, 'classes', c['id'])))
        L.append(grid(p, cx, 'classes', c['id']))
    L.append('\n## Τρέχων έλεγχος')
    L.append(findings_text(p))
    return '\n'.join(L)


def findings_text(p, limit=40):
    f = core.findings(p, True)
    hard = [x for x in f if x['hard']]; soft = sorted([x for x in f if not x['hard']], key=lambda x: -x['penalty'])
    out = ['Υποχρεωτικοί κανόνες που παραβιάζονται: ' + (str(len(hard)) if hard else 'κανένας')]
    out += ['  ✗ ' + x['text'] for x in hard[:limit]]
    out.append('Επιθυμητοί που δεν τηρούνται: ' + (str(len(soft)) if soft else 'κανένας') + ' · συνολική ποινή ' + str(_score(p)))
    out += ['  · ' + x['text'] + ' (ποινή ' + str(x['penalty']) + ')' for x in soft[:limit]]
    return '\n'.join(out)


def _score(p):
    try:
        return R.score(p) if all(e['place'] for e in R.active_view(p)['events']) else '—'
    except Exception:
        return '—'


SYSTEM = """Είσαι ο βοηθός της εφαρμογής «Ωρολόγιο» για ελληνικά σχολεία. Ο χρήστης (διευθυντής/υποδιευθυντής) ζητά αλλαγές στο εβδομαδιαίο πρόγραμμα με απλά λόγια.

Πώς δουλεύεις:
- ΔΕΝ αλλάζεις τα δεδομένα του χρήστη. Δουλεύεις σε ΠΡΟΧΕΙΡΟ αντίγραφο με τα εργαλεία· η εφαρμογή ελέγχει κάθε βήμα και απορρίπτει ό,τι παραβιάζει υποχρεωτικό κανόνα.
- Όταν φτάσεις σε λύση, κάλεσε save_proposal. Αν υπάρχουν διαφορετικοί δρόμοι (π.χ. «μετακίνηση 2 μαθημάτων» ή «νέος κανόνας και επανυπολογισμός»), φτιάξε έως 3 προτάσεις: μετά από κάθε save_proposal κάλεσε reset για να ξεκινήσεις την επόμενη από το αρχικό πρόγραμμα.
- Για κανόνες ή διαθεσιμότητα: άλλαξε τον κανόνα, μετά resolve (ο επανυπολογισμός μετακινεί όσο το δυνατόν λιγότερα).
- Για μικρές αλλαγές θέσης: move ή swap, και check για να δεις την επίπτωση.
- Πριν από save_proposal, κάλεσε check. Μην προτείνεις λύση με περισσότερες παραβιάσεις υποχρεωτικών κανόνων από το αρχικό.
- Αν κάτι δεν γίνεται, εξήγησε γιατί (ποιος κανόνας εμποδίζει) και πρότεινε τι θα μπορούσε να χαλαρώσει.
- Οι εκπαιδευτικοί αναφέρονται με κωδικούς (Τ1, Τ2…)· γράφε τους ακριβώς έτσι, η εφαρμογή τους μετατρέπει σε ονόματα. Αν ο χρήστης αναφέρει όνομα που δεν αντιστοιχεί, ρώτησέ τον.
- Μη δείχνεις στον χρήστη κωδικούς διδασκαλιών (E…) ή αναθέσεων (L…)· περιέγραψε «Μαθηματικά Β1, Τρίτη 3η ώρα».
- Απάντα σύντομα, στα ελληνικά, με τις προτάσεις και το κόστος τους (π.χ. «+1 κενό στον Τ4»). Ο χρήστης εφαρμόζει μια πρόταση με κουμπί.

Ημέρες στα εργαλεία: 1–5 (Δευτέρα–Παρασκευή). Ώρες: το όνομα της ώρας όπως φαίνεται στη λίστα «Ώρες».
"""


def tools_spec(p):
    pnames = [str(x['name']) for x in p['periods']]
    keys = {k: [x[0] for x in v if x[2] not in ('pattern', 'endpattern')] for k, v in R.CATALOG.items()}
    T = [
        ('teacher_schedule', 'Το εβδομαδιαίο πρόγραμμα ενός εκπαιδευτικού στο πρόχειρο.', {'teacher': {'type': 'string', 'description': 'κωδικός, π.χ. Τ3'}}, ['teacher']),
        ('class_schedule', 'Το εβδομαδιαίο πρόγραμμα ενός τμήματος στο πρόχειρο.', {'class_name': {'type': 'string'}}, ['class_name']),
        ('free_slots', 'Πού μπορεί να πάει μια διδασκαλία χωρίς σύγκρουση και χωρίς παραβίαση υποχρεωτικού κανόνα.', {'event': {'type': 'string', 'description': 'κωδικός E…'}}, ['event']),
        ('move', 'Μετακίνηση διδασκαλίας σε άλλη ημέρα/ώρα στο πρόχειρο.', {'event': {'type': 'string'}, 'day': {'type': 'integer', 'minimum': 1, 'maximum': 5},
                                                                          'period': {'type': 'string', 'enum': pnames}}, ['event', 'day', 'period']),
        ('swap', 'Ανταλλαγή θέσης δύο διδασκαλιών στο πρόχειρο.', {'event_a': {'type': 'string'}, 'event_b': {'type': 'string'}}, ['event_a', 'event_b']),
        ('set_rule', 'Ορίζει/αλλάζει/αφαιρεί κανόνα. Τιμές: int = αριθμός, period = όνομα ώρας, flag = true. value=null αφαιρεί. weight 0 = υποχρεωτικός, 1–5 = επιθυμητός (5 πολύ σημαντικός).',
         {'target_type': {'type': 'string', 'enum': ['teacher', 'class', 'subject']}, 'target': {'type': 'string', 'description': 'κωδικός εκπαιδευτικού ή όνομα τμήματος/μαθήματος'},
          'rule': {'type': 'string', 'enum': sorted(set(sum(keys.values(), [])))}, 'value': {'type': ['integer', 'string', 'boolean', 'null']},
          'weight': {'type': 'integer', 'minimum': 0, 'maximum': 5}}, ['target_type', 'target', 'rule', 'value']),
        ('set_availability', 'Διαθεσιμότητα: unavailable = δεν μπορεί (υποχρεωτικό), available = ξανά διαθέσιμος, avoid = καλύτερα όχι (επιθυμητό), clear_avoid.',
         {'target_type': {'type': 'string', 'enum': ['teacher', 'class', 'subject']}, 'target': {'type': 'string'}, 'day': {'type': 'integer', 'minimum': 1, 'maximum': 5},
          'periods': {'type': 'array', 'items': {'type': 'string', 'enum': pnames}, 'description': 'κενό = όλη η ημέρα'},
          'mode': {'type': 'string', 'enum': ['unavailable', 'available', 'avoid', 'clear_avoid']}}, ['target_type', 'target', 'day', 'mode']),
        ('resolve', 'Επανυπολογισμός του προχείρου με τον solver: κρατά τις θέσεις όσο γίνεται και μετακινεί ό,τι χρειάζεται για να τηρηθούν οι κανόνες.', {}, []),
        ('check', 'Έλεγχος του προχείρου: παραβιάσεις, ποινή και διαφορές από το αρχικό.', {}, []),
        ('save_proposal', 'Αποθηκεύει το τρέχον πρόχειρο ως πρόταση για τον χρήστη.', {'title': {'type': 'string', 'description': 'σύντομος τίτλος'},
                                                                                     'explanation': {'type': 'string', 'description': '1–3 προτάσεις: τι αλλάζει και τι κοστίζει'}}, ['title', 'explanation']),
        ('reset', 'Το πρόχειρο επιστρέφει στο αρχικό πρόγραμμα (για να φτιάξεις άλλη πρόταση).', {}, []),
    ]
    return [{'name': n, 'description': d, 'schema': {'type': 'object', 'properties': props, 'required': req}} for n, d, props, req in T]


# ---------------------------------------------------------------- εκτέλεση εργαλείων
class Session:
    """Μία «σειρά» του χρήστη: πρόχειρο, προτάσεις, εκτέλεση εργαλείων."""

    def __init__(self, base, cx, solver=None):
        self.base = base; self.cx = cx; self.draft = copy.deepcopy(base); self.proposals = []; self.solver = solver

    def _kind(self, t):
        return {'teacher': 'teachers', 'class': 'classes', 'subject': 'subjects'}[t]

    def _find(self, kind, ref):
        ref = str(ref).strip()
        if kind == 'teachers':
            for tid, code in self.cx.tcode.items():
                if code == ref.replace('T', 'Τ'):
                    return tid
        for x in self.draft[kind]:
            if _n(x['name']) == _n(ref) or _n(x.get('short', '')) == _n(ref):
                return x['id']
        raise ValueError('Δεν βρέθηκε: ' + ref)

    def _ev(self, code):
        eid = self.cx.eid.get(str(code).strip().upper())
        if not eid:
            raise ValueError('Άγνωστη διδασκαλία: ' + str(code))
        return eid

    def _slot(self, day, period):
        d = int(day) - 1
        names = [str(x['name']) for x in self.draft['periods']]
        if not 0 <= d < 5 or str(period) not in names:
            raise ValueError('Μη έγκυρη ημέρα/ώρα.')
        return [d, names.index(str(period))]

    def run(self, name, a):
        try:
            return getattr(self, 't_' + name)(**(a or {}))
        except (ValueError, KeyError, TypeError, StopIteration) as ex:
            return 'ΣΦΑΛΜΑ: ' + (str(ex) or ex.__class__.__name__)

    def t_teacher_schedule(self, teacher):
        tid = self._find('teachers', teacher)
        return grid(self.draft, self.cx, 'teachers', tid) + '\nΚανόνες: ' + ('; '.join(_rules_text(self.draft, 'teachers', tid)) or '—')

    def t_class_schedule(self, class_name):
        return grid(self.draft, self.cx, 'classes', self._find('classes', class_name))

    def t_free_slots(self, event):
        eid = self._ev(event); ok = []
        e = next(x for x in self.draft['events'] if x['id'] == eid)
        for d in range(5):
            for i in range(len(self.draft['periods'])):
                if e['place'] == [d, i]:
                    continue
                try:
                    core.move_event(self.draft, eid, [d, i])
                    ok.append((d, i))
                except ValueError:
                    pass
        return 'Δυνατές θέσεις: ' + (_slots_text(self.draft, ok) if ok else 'καμία (χρειάζεται ανταλλαγή ή επανυπολογισμός)')

    def t_move(self, event, day, period):
        eid = self._ev(event)
        self.draft = core.move_event(self.draft, eid, self._slot(day, period))
        return 'Έγινε. ' + self._brief()

    def t_swap(self, event_a, event_b):
        self.draft = core.move_event(self.draft, self._ev(event_a), None, self._ev(event_b))
        return 'Έγινε. ' + self._brief()

    def t_set_rule(self, target_type, target, rule, value=None, weight=None):
        kind = self._kind(target_type); eid = self._find(kind, target)
        typ = R.TYPES[kind].get(rule)
        if not typ or typ in ('pattern', 'endpattern'):
            raise ValueError('Ο κανόνας «' + str(rule) + '» δεν υπάρχει για ' + target_type)
        q = copy.deepcopy(self.draft); rr = q.setdefault(R.RULE_KEYS[kind], {}).setdefault(eid, {})
        if value is None or value == '':
            rr.pop(rule, None)
        else:
            if typ == 'period':
                value = self._slot(1, value)[1]
            elif typ == 'flag':
                value = True
            else:
                value = int(value)
            w = int(weight if weight is not None else [x for x in R.CATALOG[kind] if x[0] == rule][0][3])
            R.check_rule_value(kind, rule, {'v': value, 'w': w}, len(q['periods']))
            rr[rule] = {'v': value, 'w': w}
        self.draft = core.check_structure(q)
        return 'Ο κανόνας ενημερώθηκε. ' + self._brief() + ' (Για να αλλάξει το πρόγραμμα: resolve.)'

    def t_set_availability(self, target_type, target, day, mode, periods=None):
        kind = self._kind(target_type); eid = self._find(kind, target)
        n = len(self.draft['periods']); d = int(day) - 1
        if not 0 <= d < 5:
            raise ValueError('Μη έγκυρη ημέρα.')
        idx = [self._slot(day, x)[1] for x in periods] if periods else list(range(n))
        q = copy.deepcopy(self.draft); rr = q.setdefault(R.RULE_KEYS[kind], {}).setdefault(eid, {})
        sl = {(d, i) for i in idx}
        if mode in ('unavailable', 'available'):
            al = set(map(tuple, rr.get('allowed', [[a, b] for a in range(5) for b in range(n)])))
            al = (al - sl) if mode == 'unavailable' else (al | sl)
            if len(al) == 5 * n:
                rr.pop('allowed', None)
            else:
                rr['allowed'] = sorted([list(x) for x in al])
        else:
            av = set(map(tuple, rr.get('avoid', [])))
            av = (av | sl) if mode == 'avoid' else (av - sl)
            if av:
                rr['avoid'] = sorted([list(x) for x in av]); rr.setdefault('avoid_w', 3)
            else:
                rr.pop('avoid', None)
        self.draft = core.check_structure(q)
        return 'Η διαθεσιμότητα ενημερώθηκε. ' + self._brief() + ' (Για να αλλάξει το πρόγραμμα: resolve.)'

    def t_resolve(self):
        if not self.solver:
            return 'ΣΦΑΛΜΑ: ο επανυπολογισμός δεν είναι διαθέσιμος εδώ.'
        q = copy.deepcopy(self.draft)
        for e in q['events']:
            if e['place'] and not e['locked']:
                e['stay'] = True
        r = self.solver(q)
        if 'project' not in r:
            return 'Δεν βρέθηκε λύση: ' + str(r.get('message', ''))[:600]
        places = {e['id']: e['place'] for e in r['project']['events']}
        for e in self.draft['events']:
            e['place'] = places.get(e['id'], e['place'])
        return 'Επανυπολογίστηκε. ' + self._brief(True)

    def t_check(self):
        return findings_text(self.draft, 25) + '\nΔιαφορές από το αρχικό:\n' + '\n'.join(diff(self.base, self.draft, self.cx)['lines'] or ['καμία'])

    def t_save_proposal(self, title, explanation=''):
        if len(self.proposals) >= 3:
            return 'ΣΦΑΛΜΑ: έως 3 προτάσεις.'
        df = diff(self.base, self.draft, self.cx)
        if not df['lines']:
            return 'ΣΦΑΛΜΑ: το πρόχειρο δεν διαφέρει από το αρχικό.'
        self.proposals.append({'title': str(title)[:120], 'explanation': str(explanation)[:800], 'project': copy.deepcopy(self.draft), **df})
        return 'Αποθηκεύτηκε ως πρόταση ' + str(len(self.proposals)) + '.'

    def t_reset(self):
        self.draft = copy.deepcopy(self.base)
        return 'Το πρόχειρο επανήλθε στο αρχικό.'

    def _brief(self, full=False):
        f = core.findings(self.draft, True)
        h0 = sum(1 for x in core.findings(self.base, True) if x['hard'])
        h = sum(1 for x in f if x['hard'])
        s = 'Υποχρεωτικές παραβιάσεις: ' + str(h) + ' (αρχικά ' + str(h0) + '), ποινή ' + str(_score(self.draft)) + ' (αρχικά ' + str(_score(self.base)) + ')'
        if full:
            s += ', μετακινήσεις: ' + str(diff(self.base, self.draft, self.cx)['moves'])
        return s + '.'


def diff(a, b, cx):
    ls = core.mapping(b, 'lessons'); pa = {e['id']: e['place'] for e in a['events']}; lines = []; moves = 0
    for e in b['events']:
        if pa.get(e['id']) != e['place']:
            moves += 1
            w = lambda pl: (b['days'][pl[0]] + ' ' + _per(b, pl[1]) + 'η') if pl else 'χωρίς θέση'
            lines.append('Μετακίνηση: ' + R.lesson_label(b, ls[e['lesson']]) + ': ' + w(pa.get(e['id'])) + ' → ' + w(e['place']))
    for kind, key in R.RULE_KEYS.items():
        ra, rb = a.get(key, {}), b.get(key, {})
        for eid in sorted(set(ra) | set(rb)):
            if ra.get(eid, {}) != rb.get(eid, {}):
                lines.append('Κανόνες «' + R.name_of(b, kind, eid) + '»: ' + ('; '.join(_rules_text(b, kind, eid)) or 'χωρίς κανόνες'))
    ha = sum(1 for x in core.findings(a, True) if x['hard']); hb = sum(1 for x in core.findings(b, True) if x['hard'])
    return {'lines': lines, 'moves': moves, 'hard_before': ha, 'hard_after': hb, 'score_before': _score(a), 'score_after': _score(b)}


# ---------------------------------------------------------------- συνομιλία με τον πάροχο
def _call(pv, base, model, key, system, msgs, tools):
    if pv == 'anthropic':
        body = {'model': model, 'max_tokens': 4096, 'system': [{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
                'tools': [{'name': t['name'], 'description': t['description'], 'input_schema': t['schema']} for t in tools], 'messages': msgs}
        r = _post(base + '/messages', body, {'x-api-key': key, 'anthropic-version': '2023-06-01'})
        calls = [(b['id'], b['name'], b.get('input') or {}) for b in r.get('content', []) if b.get('type') == 'tool_use']
        text = '\n'.join(b.get('text', '') for b in r.get('content', []) if b.get('type') == 'text')
        u = r.get('usage', {})
        return r.get('content', []), calls, text, (u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0), u.get('output_tokens', 0))
    body = {'model': model, 'messages': [{'role': 'system', 'content': system}] + msgs,
            'tools': [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['schema']}} for t in tools]}
    r = _post(base + '/chat/completions', body, {'Authorization': 'Bearer ' + key} if key else {})
    m = (r.get('choices') or [{}])[0].get('message') or {}
    calls = []
    for c in m.get('tool_calls') or []:
        try:
            args = json.loads(c['function'].get('arguments') or '{}')
        except Exception:
            args = {}
        calls.append((c.get('id') or c['function']['name'], c['function']['name'], args))
    u = r.get('usage') or {}
    return m, calls, m.get('content') or '', (u.get('prompt_tokens', 0), u.get('completion_tokens', 0))


def _suggest(cfg, model):
    """Σε «δεν βρέθηκε μοντέλο»: δείχνει ποια μοντέλα του λογαριασμού ταιριάζουν."""
    try:
        ms = list_models(cfg)
    except Exception:
        return ''
    if model in ms:
        return ''
    bad = ('embed', 'image', 'tts', 'audio', 'live', 'vision', 'whisper', 'dall', 'moderation', 'search', 'realtime', 'transcribe', 'veo', 'imagen', 'aqa', 'robotics', 'computer')
    good = [m for m in ms if not any(b in m.lower() for b in bad)]
    pref = [m for m in good if any(k in m.lower() for k in ('flash-lite', 'flash', 'haiku', 'mini', 'nano', 'luna'))] or good
    if not pref:
        return ''
    return ('\nΤο μοντέλο «' + model + '» δεν είναι διαθέσιμο στον λογαριασμό σας. Διαθέσιμα (ενδεικτικά): ' + ', '.join(pref[:8]) +
            '. Ανοίξτε «Ρυθμίσεις», πατήστε «Λίστα διαθέσιμων» και διαλέξτε ένα από αυτά.')


def chat(project, history, message, cfg, solver=None, log=None):
    """Μία σειρά συνομιλίας. history: [{'role','text'}] (κείμενα σε κωδικούς).
    Επιστρέφει {'reply', 'reply_coded', 'proposals', 'usage', 'steps'}."""
    pv, base, model, key = endpoint(cfg)
    cx = Codec(project, cfg.get('anonymize', True))
    view = cx.view(project)
    sess = Session(view, cx, solver)
    tools = tools_spec(view)
    system = SYSTEM + '\n\n# Το σχολείο (τρέχουσα κατάσταση)\n' + context(view, cx)
    user = cx.encode_text(message)
    if pv == 'anthropic':
        msgs = [{'role': h['role'], 'content': h['text']} for h in history] + [{'role': 'user', 'content': user}]
    else:
        msgs = [{'role': h['role'], 'content': h['text']} for h in history] + [{'role': 'user', 'content': user}]
    tin = tout = 0; steps = []; text = ''
    for _ in range(MAX_STEPS):
        try:
            raw, calls, text, (i, o) = _call(pv, base, model, key, system, msgs, tools)
        except ServiceError as ex:
            if ex.code in (400, 404) and not steps:
                raise ValueError(str(ex) + _suggest(cfg, model))
            raise
        tin += i; tout += o
        if not calls:
            break
        if pv == 'anthropic':
            msgs.append({'role': 'assistant', 'content': raw})
            res = []
            for cid, name, args in calls:
                out = sess.run(name, args); steps.append(name)
                res.append({'type': 'tool_result', 'tool_use_id': cid, 'content': out[:12000]})
            msgs.append({'role': 'user', 'content': res})
        else:
            msgs.append({k: v for k, v in raw.items() if k in ('content', 'tool_calls') and v is not None} | {'role': 'assistant'})
            for cid, name, args in calls:
                out = sess.run(name, args); steps.append(name)
                msgs.append({'role': 'tool', 'tool_call_id': cid, 'content': out[:12000]})
    else:
        text = (text + '\n' if text else '') + '(Ο βοηθός σταμάτησε μετά από πολλά βήματα· δείτε τις προτάσεις που πρόλαβε να ετοιμάσει.)'
    props = []
    for pr in sess.proposals:
        props.append({**{k: v for k, v in pr.items() if k != 'project'},
                      'title': cx.decode_text(pr['title']), 'explanation': cx.decode_text(pr['explanation']),
                      'lines': [cx.decode_text(x) for x in pr['lines']], 'project': cx.restore(pr['project'], project)})
    return {'reply': cx.decode_text(text.strip()) or '(Χωρίς απάντηση.)', 'reply_coded': text.strip(), 'user_coded': user,
            'proposals': props, 'usage': {'input': tin, 'output': tout, 'model': model, 'provider': pv}, 'steps': steps}


def apply(current, proposal_project):
    """Εφαρμογή πρότασης: θέσεις διδασκαλιών και κανόνες· τα υπόλοιπα από το τρέχον."""
    q = copy.deepcopy(current); pr = proposal_project
    places = {e['id']: e['place'] for e in pr['events']}
    if set(places) != {e['id'] for e in q['events']}:
        raise ValueError('Το πρόγραμμα άλλαξε από τότε που έγινε η πρόταση· ζητήστε τη ξανά.')
    for e in q['events']:
        e['place'] = places[e['id']]
    for key in R.RULE_KEYS.values():
        if key in pr:
            q[key] = copy.deepcopy(pr[key])
    return core.check_structure(q)
