"""Αρχεία ανταλλαγής για τις «Εφημερίες Εκπαιδευτικών» (μονόδρομα: τα γράφει μόνο το Ωρολόγιο).

orologio.json — στιγμιότυπο του προγράμματος: εκπαιδευτικοί και σε ποιες ώρες κάθε ημέρας διδάσκουν (ή έχουν ειδικό
                πρόγραμμα)· οι Εφημερίες βγάζουν από αυτό ποιος είναι στο σχολείο σε κάθε διάλειμμα.
apousies.json — οι απουσίες που δηλώθηκαν στις Αναπληρώσεις (ημερομηνία, εκπαιδευτικός, ώρες)."""
import time
from pathlib import Path
import core, admin, suite

FORMAT = 1


def snapshot(p):
    L = core.mapping(p, 'lessons'); nd, nper = len(p['days']), len(p['periods'])
    busy = {t['id']: [[False] * nper for _ in range(nd)] for t in p['teachers']}
    for e in p['events']:
        l = L.get(e['lesson'])
        if not l or not e.get('place'):
            continue
        d, j = e['place']
        for t in l['teachers']:
            for k in range(j, min(nper, j + l['duration'])):
                if t in busy and 0 <= d < nd:
                    busy[t][d][k] = True
    for x in admin.specials(p):
        for d, j in x.get('slots', []):
            if x.get('teacher') in busy and 0 <= d < nd and 0 <= j < nper:
                busy[x['teacher']][d][j] = True
    teachers = []
    for t in p['teachers']:
        if t.get('hypothetical'):
            continue
        teachers.append({'id': t['id'], 'name': t['name'], 'short': t.get('short', ''), 'klados': admin.klados_code(t.get('spec', '')) or '', 'role': t.get('role', ''),
                         'active': t.get('active', True) is not False,
                         'periods': [[k for k in range(nper) if busy[t['id']][d][k]] for d in range(nd)]})
    return {'format': 'orologio-snapshot', 'version': FORMAT, 'app_version': core.VERSION, 'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            'school': p.get('school', ''), 'year': p.get('year', ''), 'level': core.level(p), 'days': p['days'],
            'periods': [{'index': i, 'name': x['name'], 'start': x.get('start', ''), 'end': x.get('end', '')} for i, x in enumerate(p['periods'])],
            'teachers': teachers}


def absences(p):
    T = core.mapping(p, 'teachers'); out = []
    for r in p.get('substitutions') or []:
        for a in r.get('absent', []):
            t = T.get(a.get('teacher'))
            if t:
                out.append({'date': r['date'], 'teacher': t['id'], 'name': t['name'], 'periods': a.get('periods'), 'reason': a.get('reason', '')})
    return {'format': 'orologio-absences', 'version': FORMAT, 'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'year': p.get('year', ''), 'absences': out}


def write(p, schedule=True):
    """Γράφει τα αρχεία στον φάκελο «Κοινά». Δεν σταματά ποτέ την αποθήκευση (τα λάθη επιστρέφονται)."""
    folder = suite.common_dir()
    try:
        if schedule:
            suite._write(folder / 'orologio.json', snapshot(p))
        suite._write(folder / 'apousies.json', absences(p))
        return None
    except Exception as ex:
        return str(ex)
