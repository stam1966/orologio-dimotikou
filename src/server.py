"""Τοπική υπηρεσία της εφαρμογής: API, ιστορικό αναίρεσης, παραγωγή, παράθυρο εφαρμογής."""
import json, secrets, threading, webbrowser, sys, copy, time, os, subprocess, shutil
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import base64
import core, outputs, rules, updater, versions

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'project.json'
LOG = ROOT / 'data' / 'app.log'
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()
STATE = {'project': None, 'revision': 0, 'job': {'running': False, 'message': ''}}
UNDO, REDO = [], []          # (ετικέτα, έργο)
HISTORY_MAX = 60
CANCEL = threading.Event()
SUMMARY_CACHE = {}
LAST_SEEN = [time.time()]
BYE = [0.0]


def log(*a):
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + ' '.join(str(x) for x in a) + '\n')
    except OSError:
        pass
    try:
        print(*a)
    except Exception:
        pass


def boot():
    STATE['project'] = core.load(DATA) if DATA.exists() else core.blank()


def commit(p, label='Αλλαγή', history=True):
    if history and STATE['project'] is not None:
        UNDO.append((label, STATE['project']))
        del UNDO[:-HISTORY_MAX]
        REDO.clear()
    core.save(p, DATA); STATE['project'] = p; STATE['revision'] += 1


def summary(p):
    """Σύνοψη ποιότητας (με προσωρινή μνήμη ανά αναθεώρηση)."""
    key = STATE['revision']
    if SUMMARY_CACHE.get('rev') == key:
        return SUMMARY_CACHE['data']
    found = core.findings(p, True)
    hard = [f for f in found if f['hard'] and f['key'][0] != 'unplaced']
    soft = sorted([f for f in found if not f['hard']], key=lambda f: -f['penalty'])
    unplaced = sum(1 for e in p['events'] if not e['place'])
    data = {'errors': [f['text'] for f in hard], 'warnings': [{'text': f['text'], 'penalty': f['penalty']} for f in soft],
            'gaps': rules.gap_total(p, False), 'unplaced': unplaced,
            'score': rules.score(p) if not unplaced else None}
    SUMMARY_CACHE.update(rev=key, data=data)
    return data


def state_json():
    p = STATE['project']
    try:
        summ = summary(p)
    except Exception as ex:  # ένα λάθος στον έλεγχο δεν πρέπει να «κλειδώνει» τη διεπαφή
        summ = {'errors': ['Σφάλμα ελέγχου: ' + str(ex)], 'warnings': [], 'gaps': 0, 'unplaced': 0, 'score': None}
    return json.dumps({**STATE, 'catalog': rules.CATALOG, 'strength': rules.STRENGTH, 'summary': summ,
                       'history': {'undo': UNDO[-1][0] if UNDO else '', 'redo': REDO[-1][0] if REDO else ''}}, ensure_ascii=False)


def prepare(p, mode, entity):
    """Αντίγραφο για τον solver ανάλογα με τον τρόπο παραγωγής."""
    q = copy.deepcopy(p); ls = core.mapping(q, 'lessons')
    for e in q['events']:
        if e['locked']:
            continue
        if mode == 'fill' and e['place']:
            e['stay'] = True                         # μένουν όπου είναι, εκτός αν χρειάζεται για να βγει λύση
        elif mode == 'scratch':
            e['place'] = None                        # από την αρχή, χωρίς υπόδειξη
        elif mode == 'entity' and e['place']:
            kind, eid = entity
            if not outputs.belongs(ls[e['lesson']], kind, eid):
                e['locked'] = True                   # όλα σταθερά εκτός από τον επιλεγμένο
    return q


def generation(p, seconds, mode, entity, before):
    try:
        result = core.solve(prepare(p, mode, entity), seconds, CANCEL)
        with LOCK:
            if 'project' in result:
                q = result.pop('project')
                out = copy.deepcopy(STATE['project'])
                places = {e['id']: e['place'] for e in q['events']}
                for e in out['events']:
                    e['place'] = places[e['id']]
                label = {'fill': 'Συμπλήρωση εκκρεμοτήτων', 'improve': 'Βελτίωση προγράμματος', 'scratch': 'Παραγωγή από την αρχή', 'entity': 'Ανασχεδιασμός'}[mode]
                commit(out, label)
                after = summary(out)
                result['before'] = {k: before[k] for k in ('gaps', 'unplaced', 'score')} if before else None
                result['before_errors'] = len(before['errors']) if before else None
                result['after'] = {k: after[k] for k in ('gaps', 'unplaced', 'score')}
            STATE['job'] = {**result, 'running': False, 'finished': time.time()}
    except Exception as ex:
        log('generation error', repr(ex))
        with LOCK:
            STATE['job'] = {'running': False, 'status': 'error', 'message': str(ex), 'finished': time.time()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, status, data, ctype='application/json; charset=utf-8', download=None):
        b = data.encode('utf-8') if isinstance(data, str) else data
        self.send_response(status); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff'); self.send_header('X-Frame-Options', 'SAMEORIGIN')
        if download:
            self.send_header('Content-Disposition', 'attachment; filename="' + download + '"')
        self.end_headers(); self.wfile.write(b)

    def valid_host(self):
        return self.headers.get('Host') == '127.0.0.1:' + str(self.server.server_port)

    def authorized(self):
        if self.headers.get('X-App-Token') == TOKEN:
            LAST_SEEN[0] = time.time(); BYE[0] = 0.0
            return True
        return False

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, '{}')
        path = urlparse(self.path).path
        if path == '/':
            LAST_SEEN[0] = time.time(); BYE[0] = 0.0
            return self.send(200, (ROOT / 'src' / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN).replace('__VERSION__', core.VERSION), 'text/html; charset=utf-8')
        if not self.authorized():
            return self.send(403, '{}')
        with LOCK:
            if path == '/api/state':
                return self.send(200, state_json())
            if path == '/api/export':
                return self.send(200, json.dumps(STATE['project'], ensure_ascii=False, indent=2), download='timetable.json')
            if path == '/api/export/asc':
                import asc
                return self.send(200, asc.export_asc(STATE['project']), 'application/xml; charset=windows-1253', download='orologio_gia_aSc.xml')
            if path == '/api/export/xml':
                return self.send(200, outputs.export_xml(STATE['project']), 'application/xml; charset=utf-8', download='timetable.xml')
            if path == '/api/export/xlsx':
                return self.send(200, outputs.export_xlsx(STATE['project']), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', download='orologio.xlsx')
            if path == '/api/print':
                return self.send(200, outputs.report(STATE['project'], {'kind': 'classes'}), 'text/html; charset=utf-8')
        self.send(404, '{}')

    def do_POST(self):
        if not self.valid_host():
            return self.send(403, '{}')
        u = urlparse(self.path)
        if u.path == '/api/bye':  # κλείσιμο παραθύρου (sendBeacon δεν στέλνει κεφαλίδες)
            if parse_qs(u.query).get('t', [''])[0] == TOKEN:
                BYE[0] = time.time()
            return self.send(200, '{}')
        if not self.authorized():
            return self.send(403, '{}')
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 15_000_000:
                raise ValueError('Μη αποδεκτό μέγεθος αιτήματος.')
            req = json.loads(self.rfile.read(length)); action = u.path
            if action == '/api/export/pdfs':  # μακρά εργασία: εκτός κλειδώματος, σε αντίγραφο
                import pdfs
                with LOCK:
                    snap = copy.deepcopy(STATE['project'])
                kind = req.get('kind', 'teachers')
                if kind not in ('teachers', 'classes'):
                    raise ValueError('Μη έγκυρη επιλογή.')
                data, n = pdfs.make_zip(snap, kind, req.get('options', {}))
                return self.send(200, data, 'application/zip', download=('orologia_ekpaideftikon.zip' if kind == 'teachers' else 'orologia_tmimaton.zip'))
            with LOCK:
                p = STATE['project']
                if action == '/api/ping':
                    return self.send(200, '{}')
                if action == '/api/report':
                    return self.send(200, outputs.report(p, req.get('options', {})), 'text/html; charset=utf-8')
                if action == '/api/cancel':
                    CANCEL.set(); return self.send(200, '{}')
                if action == '/api/check':
                    return self.send(200, json.dumps(summary(p), ensure_ascii=False))
                if action == '/api/slots':
                    return self.send(200, json.dumps(core.slot_status(p, req['id']), ensure_ascii=False))
                if action == '/api/export/xlsx':
                    return self.send(200, outputs.export_xlsx(p, req.get('options', {})), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', download='orologio.xlsx')
                if action == '/api/versions/list':
                    return self.send(200, json.dumps(versions.listing(ROOT), ensure_ascii=False))
                if action == '/api/versions/save':
                    vid = versions.save(ROOT, p, req.get('name', ''))
                    return self.send(200, json.dumps({'id': vid}, ensure_ascii=False))
                if action == '/api/versions/delete':
                    versions.delete(ROOT, req['id']); return self.send(200, '{}')
                if action == '/api/versions/compare':
                    d = versions.load(ROOT, req['id'])
                    return self.send(200, json.dumps({'name': d['name'], 'teachers': versions.diff(d['project'], p, 'teachers'), 'classes': versions.diff(d['project'], p, 'classes')}, ensure_ascii=False))
                if action == '/api/versions/report':
                    d = versions.load(ROOT, req['id'])
                    return self.send(200, versions.changes_report(d['project'], p, d['name'], req.get('kind', 'teachers'), req.get('options')), 'text/html; charset=utf-8')
                if action == '/api/update/backups':
                    return self.send(200, json.dumps({'current': core.VERSION, 'backups': updater.list_backups(ROOT)}, ensure_ascii=False))
                if action == '/api/update/check':
                    man, files = updater.read(base64.b64decode(req['data']))
                    return self.send(200, json.dumps({'current': core.VERSION, 'version': man['version'], 'notes': man.get('notes', ''),
                                                      'newer': updater.vtuple(man['version']) > updater.vtuple(core.VERSION),
                                                      'same': updater.vtuple(man['version']) == updater.vtuple(core.VERSION)}, ensure_ascii=False))
                if STATE['job']['running']:
                    raise ValueError('Περιμένετε να τελειώσει η παραγωγή ή πατήστε «Διακοπή».')
                if action in ('/api/update/apply', '/api/update/rollback'):
                    if action == '/api/update/apply':
                        raw = base64.b64decode(req['data'])
                    else:
                        name = req['name']
                        if not any(b['name'] == name for b in updater.list_backups(ROOT)):
                            raise ValueError('Άγνωστο αντίγραφο έκδοσης.')
                        raw = (ROOT / 'data' / 'backups' / name).read_bytes()
                    man, files = updater.read(raw)
                    updater.verify(files)
                    saved = updater.backup(ROOT, core.VERSION)
                    updater.install(ROOT, files)
                    log('updated', core.VERSION, '->', man['version'], 'backup', saved.name)
                    self.send(200, json.dumps({'ok': True, 'version': man['version']}, ensure_ascii=False))
                    def later(srv=self.server):
                        time.sleep(0.6); updater.restart(ROOT, srv.server_port); srv.shutdown()
                    threading.Thread(target=later, daemon=True).start()
                    return
                if req.get('revision') != STATE['revision']:
                    raise ValueError('Τα δεδομένα άλλαξαν σε άλλο παράθυρο. Η σελίδα θα ανανεωθεί.')
                if action == '/api/import':
                    q = core.import_xml(req['text']) if req['kind'] == 'xml' else core.check_structure(json.loads(req['text']))
                    commit(q, 'Εισαγωγή αρχείου')
                elif action == '/api/save':
                    q = req['project']; core.check_structure(q); commit(q, req.get('label') or 'Αλλαγή')
                elif action == '/api/move':
                    q = core.move_event(p, req['id'], req['place'], req.get('swap'))
                    commit(q, 'Ανταλλαγή' if req.get('swap') else ('Αφαίρεση θέσης' if req['place'] is None else 'Μετακίνηση'))
                elif action == '/api/versions/restore':
                    d = versions.load(ROOT, req['id']); commit(d['project'], 'Επαναφορά εκδοχής «' + d['name'] + '»')
                elif action == '/api/lock':
                    q = copy.deepcopy(p); ids = set(req['ids']); n = 0
                    for e in q['events']:
                        if e['id'] in ids and (e['place'] or not req['locked']):
                            e['locked'] = bool(req['locked']); n += 1
                    if not n:
                        raise ValueError('Δεν υπάρχουν τοποθετημένες διδασκαλίες για κλείδωμα.')
                    commit(q, 'Κλείδωμα' if req['locked'] else 'Ξεκλείδωμα')
                elif action == '/api/unplace':
                    q = copy.deepcopy(p); ids = set(req['ids'])
                    for e in q['events']:
                        if e['id'] in ids and not e['locked']:
                            e['place'] = None
                    commit(q, 'Αφαίρεση θέσεων')
                elif action in ('/api/undo', '/api/redo'):
                    src, dst = (UNDO, REDO) if action == '/api/undo' else (REDO, UNDO)
                    if not src:
                        raise ValueError('Δεν υπάρχει άλλη ' + ('αναίρεση.' if action == '/api/undo' else 'επανάληψη.'))
                    label, q = src.pop(); dst.append((label, p))
                    commit(q, history=False)
                elif action == '/api/generate':
                    q = STATE['project']; seconds = max(5, min(600, int(req.get('seconds', 30))))
                    mode = req.get('mode', 'improve')
                    if mode not in ('fill', 'improve', 'scratch', 'entity'):
                        raise ValueError('Άγνωστος τρόπος παραγωγής.')
                    entity = tuple(req.get('entity') or ()) if mode == 'entity' else None
                    if mode == 'entity' and (len(entity) != 2 or entity[0] not in ('teachers', 'classes')):
                        raise ValueError('Επιλέξτε εκπαιδευτικό ή τμήμα.')
                    CANCEL.clear(); STATE['job'] = {'running': True, 'message': 'Αναζήτηση προγράμματος…', 'started': time.time(), 'seconds': seconds}
                    before = summary(q)
                    threading.Thread(target=generation, args=(q, seconds, mode, entity, before), daemon=True).start()
                elif action == '/api/shutdown':
                    self.send(200, '{}'); threading.Thread(target=self.server.shutdown, daemon=True).start(); return
                else:
                    raise ValueError('Άγνωστη ενέργεια.')
                self.send(200, state_json())
        except Exception as ex:
            log('request error', self.path, repr(ex))
            self.send(400, json.dumps({'error': str(ex)}, ensure_ascii=False))


# ---------------------------------------------------------------- παράθυρο εφαρμογής
def find_browser():
    """Edge ή Chrome για άνοιγμα σε δικό του παράθυρο (λειτουργία εφαρμογής)."""
    if sys.platform != 'win32':
        return None
    cands = []
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if base:
            cands += [Path(base) / 'Microsoft/Edge/Application/msedge.exe', Path(base) / 'Google/Chrome/Application/chrome.exe']
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which('msedge') or shutil.which('chrome')


def open_window(url):
    if '--no-browser' in sys.argv:
        return
    exe = find_browser()
    if exe:
        profile = Path(os.environ.get('LOCALAPPDATA', str(ROOT / 'data'))) / 'OrologioDimotikou' / 'window'
        try:
            profile.mkdir(parents=True, exist_ok=True)
            subprocess.Popen([exe, '--app=' + url, '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check',
                              '--window-size=1440,900', '--disable-features=Translate'], close_fds=True)
            return
        except OSError as ex:
            log('app window failed', repr(ex))
    webbrowser.open(url)


def watchdog(server):
    """Κλείνει την εφαρμογή λίγο μετά το κλείσιμο του παραθύρου (όχι σε ανανέωση σελίδας)."""
    while True:
        time.sleep(2)
        if BYE[0] and time.time() - BYE[0] > 25 and LAST_SEEN[0] < BYE[0] and not STATE['job']['running']:
            log('window closed: exiting'); server.shutdown(); return
        if time.time() - LAST_SEEN[0] > 900 and not STATE['job']['running']:  # κανένα παράθυρο για 15 λεπτά
            log('no window for 15 minutes: exiting'); server.shutdown(); return


def message_box(text):
    log(text)
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, 'Ωρολόγιο Δημοτικού', 0x10)
            return
        except Exception:
            pass
    try:
        input(text + '\nEnter για έξοδο.')
    except Exception:
        pass


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default


def main():
    urlfile = ROOT / 'data' / 'app.url'
    restarted = '--restarted' in sys.argv
    (ROOT / 'data').mkdir(exist_ok=True)
    handle = open(ROOT / 'data' / 'app.lock', 'a+b'); handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
    deadline = time.time() + (30 if restarted else 0)
    while True:
        try:
            if sys.platform == 'win32':
                import msvcrt; msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl; fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() < deadline:  # μετά από ενημέρωση: περιμένουμε να κλείσει η παλιά διεργασία
                time.sleep(0.3); continue
            # Ήδη ανοικτή: ανοίγουμε ξανά το παράθυρό της αντί για μήνυμα σφάλματος.
            try:
                open_window(urlfile.read_text(encoding='utf-8').strip())
            except OSError:
                message_box('Η εφαρμογή είναι ήδη ανοικτή.')
            return
    try:
        boot()
    except Exception as ex:
        handle.close()
        message_box('Δεν ήταν δυνατό να φορτωθούν τα δεδομένα. Δεν έγινε καμία αντικατάσταση.\n\n' + str(ex)); return
    port = int(arg('--port', 0) or 0)
    for attempt in range(60):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), Handler); break
        except OSError:
            if not port or attempt == 59:
                port = 0
                if attempt == 59:
                    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); break
            time.sleep(0.5)
    url = 'http://127.0.0.1:' + str(server.server_port) + '/'
    try:
        urlfile.write_text(url, encoding='utf-8')
    except OSError:
        pass
    log('Ωρολόγιο Δημοτικού ' + core.VERSION + ' ' + url + (' (μετά από ενημέρωση)' if restarted else ''))
    if not restarted or server.server_port != int(arg('--port', 0) or 0):
        open_window(url)
    LAST_SEEN[0] = time.time()
    if '--stay' not in sys.argv and '--no-browser' not in sys.argv:
        threading.Thread(target=watchdog, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        CANCEL.set(); server.server_close()
        try:  # πριν απελευθερωθεί το κλείδωμα, ώστε να μη σβηστεί το αρχείο της νέας διεργασίας
            urlfile.unlink()
        except OSError:
            pass
        handle.close()


if __name__ == '__main__':
    main()
