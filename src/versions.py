"""Εκδοχές προγράμματος: αποθήκευση με όνομα, σύγκριση, σημείωμα αλλαγών ανά εκπαιδευτικό."""
import json, os, re, tempfile, time, uuid, html
from collections import Counter
from pathlib import Path
import core, outputs


def folder(root):
    f = Path(root) / 'data' / 'versions'; f.mkdir(parents=True, exist_ok=True); return f


def save(root, p, name):
    name = (name or '').strip()[:80] or time.strftime('Εκδοχή %d/%m/%Y %H:%M')
    vid = time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6]
    data = {'id': vid, 'name': name, 'created': time.strftime('%d/%m/%Y %H:%M'), 'project': p}
    path = folder(root) / (vid + '.json')
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return vid


def _path(root, vid):
    if not re.fullmatch(r'[0-9_a-f]+', vid or ''):
        raise ValueError('Μη έγκυρη εκδοχή.')
    p = folder(root) / (vid + '.json')
    if not p.exists():
        raise ValueError('Η εκδοχή δεν βρέθηκε.')
    return p


def load(root, vid):
    d = json.loads(_path(root, vid).read_text(encoding='utf-8'))
    core.check_structure(d['project'])
    return d


def delete(root, vid):
    _path(root, vid).unlink()


def listing(root):
    out = []
    for f in sorted(folder(root).glob('*.json'), reverse=True):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            p = d['project']
            out.append({'id': d['id'], 'name': d['name'], 'created': d['created'],
                        'placed': sum(1 for e in p['events'] if e['place']), 'events': len(p['events'])})
        except Exception:
            continue
    return out


def _slots(p, tid, kind='teachers'):
    """Διδασκαλίες εγγραφής ως πολυσύνολο (περιγραφή, ημέρα, ώρα έναρξης, διάρκεια)."""
    ls = core.mapping(p, 'lessons'); S = core.mapping(p, 'subjects'); C = core.mapping(p, 'classes'); T = core.mapping(p, 'teachers')
    out = Counter()
    for e in p['events']:
        l = ls[e['lesson']]
        if not e['place'] or not outputs.belongs(l, kind, tid):
            continue
        other = ', '.join(C[c]['name'] for c in l['classes'] if c in C) if kind == 'teachers' else ', '.join(T[t]['name'] for t in l['teachers'] if t in T)
        label = S[l['subject']]['name'] + (' — ' + other if other else '')
        out[(label, e['place'][0], e['place'][1], l['duration'])] += 1
    return out


def diff(old, new, kind='teachers'):
    """Αλλαγές ανά εγγραφή: [{'id','name','changes':[κείμενα]}] μόνο για όσους άλλαξαν."""
    names = {x['id']: x['name'] for x in old[kind]}
    names.update({x['id']: x['name'] for x in new[kind]})
    days = new['days']; per = new['periods']
    when = lambda d, i, dur: days[d] + ' ' + per[i]['name'] + 'η' + ('–' + per[i + dur - 1]['name'] + 'η' if dur > 1 and i + dur - 1 < len(per) else '') + ' ώρα'
    res = []
    for eid in names:
        a = _slots(old, eid, kind) if any(x['id'] == eid for x in old[kind]) else Counter()
        b = _slots(new, eid, kind) if any(x['id'] == eid for x in new[kind]) else Counter()
        removed = list((a - b).elements()); added = list((b - a).elements())
        changes = []
        for r in list(removed):  # ίδιο μάθημα που απλώς άλλαξε θέση
            m = next((x for x in added if x[0] == r[0]), None)
            if m:
                changes.append(r[0] + ': από ' + when(r[1], r[2], r[3]) + ' → ' + when(m[1], m[2], m[3]))
                added.remove(m); removed.remove(r)
        changes += [x[0] + ': αφαιρείται η ' + when(x[1], x[2], x[3]) for x in removed]
        changes += [x[0] + ': νέα ώρα ' + when(x[1], x[2], x[3]) for x in added]
        if changes:
            res.append({'id': eid, 'name': names[eid], 'changes': changes})
    order = {x['id']: k for k, x in enumerate(new[kind])}
    return sorted(res, key=lambda r: order.get(r['id'], 999))


def changes_report(old, new, title, kind='teachers', opts=None):
    """Εκτύπωση: για κάθε εκπαιδευτικό που επηρεάζεται, οι αλλαγές και το νέο του ωρολόγιο."""
    opts = dict(opts or {}); esc = lambda s: html.escape(str(s))
    d = diff(old, new, kind)
    if not d:
        return '<!doctype html><meta charset="utf-8"><p style="font:16px Arial;padding:30px">Δεν υπάρχουν αλλαγές.</p>'
    base = outputs.report(new, dict(opts, kind=kind, mode='individual', entity=d[0]['id'], pdf=opts.get('pdf', False)))
    head, _, _ = base.partition('<section')
    body = []
    for r in d:
        page = outputs.report(new, dict(opts, kind=kind, mode='individual', entity=r['id'], pdf=True))
        sec = page[page.index('<section'):page.rindex('</section>') + len('</section>')]
        note = ('<div class="changes"><h3>Αλλαγές σε σχέση με «' + esc(title) + '»</h3><ul>' + ''.join('<li>' + esc(c) + '</li>' for c in r['changes']) + '</ul></div>')
        body.append(sec.replace('<table class="week">', note + '<table class="week">', 1))
    extra = '<style>.changes{border:1px solid #c9a227;background:#fdf6dc;padding:.4em .9em;margin:.4em 0 .7em;font-size:1.05em}.changes h3{margin:.2em 0;font-size:1.1em}.changes ul{margin:.2em 0 .3em 1.2em;padding:0}</style>'
    return head.replace('</style>', '</style>' + extra, 1) + ''.join(body) + '</html>'
