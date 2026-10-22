"""Έλεγχος λειτουργίας σε Windows με το πραγματικό runtime (εκτελείται στο GitHub Actions).
Χρησιμοποιεί το δοκιμαστικό σχολείο: παραγωγή με τον πραγματικό solver, εκτυπώσεις, Excel,
εξαγωγή aSc, PDF μέσω Edge, και εκκίνηση της τοπικής υπηρεσίας."""
import json, sys, time, threading, urllib.request, copy, zipfile, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import core, rules, outputs, asc

def step(name):
    print('==>', name, flush=True)

p = core.check_structure(json.loads((ROOT / 'src' / 'demo_school.json').read_text(encoding='utf-8')))
step('validation'); assert core.validation(p, True) == [], core.validation(p, True)

step('solve: improve (60s, real CP-SAT)')
t = time.time(); r = core.solve(p, 60)
print(r['status'], r.get('message'), round(time.time() - t, 1), 's')
assert r['status'] in ('optimal', 'feasible'), r
q = r['project']; assert core.validation(q, True) == []
if r['status'] == 'optimal':
    assert r['objective'] == rules.score(q), (r['objective'], rules.score(q))

step('solve: from scratch (120s)')
s = copy.deepcopy(p)
for e in s['events']: e['place'] = None
r2 = core.solve(s, 120); print(r2['status'], r2.get('message'))
assert r2['status'] in ('optimal', 'feasible'), r2

step('diagnosis of impossible rules')
bad = copy.deepcopy(p); t0 = bad['teachers'][0]['id']
bad['teacher_rules'][t0] = {'max_daily': {'v': 1, 'w': 0, 'on': True}}
r3 = core.solve(bad, 30); print(r3['status'], r3.get('reasons'))
assert r3['status'] == 'infeasible' and r3.get('reasons'), r3

step('reports, xlsx, asc')
for kind in outputs.LABELS:
    for mode in outputs.MODES:
        outputs.report(q, dict(kind=kind, mode=mode)); outputs.export_xlsx(q, dict(kind=kind, mode=mode))
outputs.export_xlsx(q)
back = core.import_xml(asc.export_asc(q)); assert len(back['events']) == len(q['events'])

step('pdf via Edge')
import pdfs
print('browser:', pdfs.find_browser())
data, n = pdfs.make_zip(q, 'teachers', {}); z = zipfile.ZipFile(io.BytesIO(data))
print(n, 'pdfs', z.namelist()[:2]); assert n == len(z.namelist()) and n > 5

step('server start')
import subprocess, os
(ROOT / 'data').mkdir(exist_ok=True)
proc = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'src' / 'server.py'), '--no-browser', '--stay'], cwd=str(ROOT))
try:
    url = None
    for _ in range(60):
        time.sleep(0.5)
        f = ROOT / 'data' / 'app.url'
        if f.exists():
            url = f.read_text(encoding='utf-8').strip(); break
    assert url, 'server did not start'
    page = urllib.request.urlopen(url, timeout=10).read().decode('utf-8')
    assert 'Ωρολόγιο Δημοτικού' in page and core.VERSION in page
    print('server OK', url)
finally:
    proc.terminate()
print('SMOKE OK')
