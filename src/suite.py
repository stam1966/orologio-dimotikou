"""Σουίτα «Σχολικές Εφαρμογές» (Ωρολόγιο + Εφημερίες): φάκελος δεδομένων, κοινή χρήση από δύο υπολογιστές,
ρόλος υπολογιστή με PIN, κλείδωμα του βασικού προγράμματος, αρχεία ανταλλαγής για τις Εφημερίες.

Ρυθμίσεις του υπολογιστή: %APPDATA%\\SchoolApps\\suite.json (κοινές για τις δύο εφαρμογές· τις γράφει και το Setup)
  {"root": "<φάκελος σουίτας ή κενό>", "role": "director"|"deputy", "confirmed": true|false}
Φάκελος σουίτας (π.χ. κοινόχρηστος):
  Ωρολόγιο\\project.json          το βασικό πρόγραμμα (το αλλάζει ένας υπολογιστής τη φορά — editor.lock)
  Ωρολόγιο\\anaplirwseis.json     οι αναπληρώσεις (απουσίες, καλύψεις) — γράφονται από όλους, συγχώνευση ανά ημέρα
  Εφημερίες\\                     τα δεδομένα των Εφημεριών
  Κοινά\\suite.json               PIN της Διεύθυνσης (hash), σχολείο
  Κοινά\\orologio.json            στιγμιότυπο για τις Εφημερίες (εκπαιδευτικοί, ώρες, παρουσία)
  Κοινά\\apousies.json            απουσίες από τις Αναπληρώσεις για τις Εφημερίες
Χωρίς φάκελο σουίτας όλα μένουν όπως πριν (data\\ της εφαρμογής) και τα αρχεία ανταλλαγής πάνε στο %APPDATA%\\SchoolApps\\Κοινά."""
import json, os, socket, time, hashlib, secrets, tempfile, getpass
from pathlib import Path

APP_DIR, EF_DIR, COMMON = 'Ωρολόγιο', 'Εφημερίες', 'Κοινά'
ROLES = {'director': 'Διεύθυνση', 'deputy': 'Υποδιευθυντής'}
STALE = 150          # δευτερόλεπτα χωρίς «σήμα ζωής» → το κλείδωμα θεωρείται εγκαταλελειμμένο
SUBS_FILE = 'anaplirwseis.json'


def config_path():
    if os.environ.get('SCHOOLAPPS_CONFIG'):
        return Path(os.environ['SCHOOLAPPS_CONFIG'])
    base = os.environ.get('APPDATA') or str(Path.home() / '.config')
    return Path(base) / 'SchoolApps' / 'suite.json'


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except Exception:
        return default


def _write(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def machine():
    c = _read(config_path(), {})
    if not isinstance(c, dict):
        c = {}
    role = c.get('role') if c.get('role') in ROLES else 'director'
    return {'root': str(c.get('root') or ''), 'role': role, 'confirmed': bool(c.get('confirmed', role == 'deputy'))}


def save_machine(c):
    cur = _read(config_path(), {})
    cur = cur if isinstance(cur, dict) else {}
    cur.update({k: c[k] for k in ('root', 'role', 'confirmed') if k in c})
    _write(config_path(), cur)
    return machine()


def shared():
    return bool(machine()['root'])


def data_dir(app_root):
    """Φάκελος του έργου του Ωρολογίου."""
    r = machine()['root']
    return Path(r) / APP_DIR if r else Path(app_root) / 'data'


def common_dir():
    r = machine()['root']
    return Path(r) / COMMON if r else config_path().parent / COMMON


def effective_role():
    """Ρόλος που ισχύει: σε κοινή χρήση, «Διεύθυνση» μόνο αφού επιβεβαιωθεί με το PIN· αλλιώς πάντα Διεύθυνση."""
    m = machine()
    if not m['root']:
        return 'director'
    return 'director' if m['role'] == 'director' and m['confirmed'] else 'deputy'


# ---------- PIN της Διεύθυνσης (στο Κοινά\suite.json, ώστε να ισχύει σε όλους τους υπολογιστές) ----------
def _school_file():
    return common_dir() / 'suite.json'


def has_pin():
    return bool(_read(_school_file(), {}).get('pin'))


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac('sha256', str(pin).encode('utf-8'), bytes.fromhex(salt), 120000).hex()


def set_pin(new, old=None):
    new = str(new or '').strip()
    if not (4 <= len(new) <= 12 and new.isdigit()):
        raise ValueError('Το PIN πρέπει να έχει 4 έως 12 ψηφία.')
    if has_pin() and not check_pin(old):
        raise ValueError('Λάθος τρέχον PIN.')
    d = _read(_school_file(), {}); salt = secrets.token_hex(16)
    d.update(pin={'salt': salt, 'hash': _hash(new, salt)}, pin_changed=time.strftime('%Y-%m-%d %H:%M'))
    _write(_school_file(), d)


def check_pin(pin):
    d = _read(_school_file(), {}).get('pin') or {}
    if not d.get('salt'):
        return False
    return secrets.compare_digest(_hash(str(pin or '').strip(), d['salt']), d.get('hash', ''))


def set_role(role, pin=None):
    """Αλλαγή ρόλου του υπολογιστή. Για «Διεύθυνση» χρειάζεται το PIN (ή ορισμός PIN αν δεν υπάρχει)."""
    if role not in ROLES:
        raise ValueError('Άγνωστος ρόλος.')
    if role == 'director':
        if not has_pin():
            set_pin(pin)
        elif not check_pin(pin):
            raise ValueError('Λάθος PIN.')
    elif machine()['role'] == 'director' and has_pin() and not check_pin(pin):
        raise ValueError('Για αλλαγή ρόλου χρειάζεται το PIN της Διεύθυνσης.')
    return save_machine({'role': role, 'confirmed': True})


# ---------- Κλείδωμα του βασικού προγράμματος (ένας υπολογιστής αλλάζει το πρόγραμμα τη φορά) ----------
def me():
    try:
        user = getpass.getuser()
    except Exception:
        user = ''
    return {'pc': socket.gethostname(), 'user': user, 'pid': os.getpid()}


def _same(a, b):
    return a.get('pc') == b.get('pc') and a.get('pid') == b.get('pid')


def lock_info(folder):
    d = _read(Path(folder) / 'editor.lock', None)
    if not isinstance(d, dict):
        return None
    d['stale'] = time.time() - float(d.get('beat') or 0) > STALE
    return d


def acquire(folder, force=False):
    """Παίρνει (ή ανανεώνει) το κλείδωμα. Επιστρέφει (True, None) ή (False, πληροφορίες κατόχου)."""
    cur = lock_info(folder); mine = me()
    if cur and not cur['stale'] and not _same(cur, mine) and not force:
        return False, cur
    since = cur['since'] if cur and _same(cur, mine) else time.time()
    _write(Path(folder) / 'editor.lock', {**mine, 'since': since, 'beat': time.time()})
    again = lock_info(folder)   # δύο υπολογιστές ταυτόχρονα: κερδίζει όποιος γράφτηκε τελευταίος
    return (True, None) if again and _same(again, mine) else (False, again)


def release(folder):
    cur = lock_info(folder)
    if cur and _same(cur, me()):
        try:
            (Path(folder) / 'editor.lock').unlink()
        except OSError:
            pass


# ---------- Αναπληρώσεις σε ξεχωριστό κοινό αρχείο, συγχώνευση ανά ημέρα ----------
def load_subs(folder):
    d = _read(Path(folder) / SUBS_FILE, None)
    return d.get('records') if isinstance(d, dict) and isinstance(d.get('records'), list) else None


def merge_subs(folder, before, after):
    """Γράφει στο κοινό αρχείο μόνο τις ημέρες που άλλαξαν σε αυτόν τον υπολογιστή· κρατά ό,τι έγραψαν οι άλλοι.
    Επιστρέφει τη συγχωνευμένη λίστα."""
    key = lambda r: r.get('date')
    b = {key(r): r for r in before or []}; a = {key(r): r for r in after or []}
    changed = {d for d in set(a) | set(b) if a.get(d) != b.get(d)}
    path = Path(folder) / SUBS_FILE; lk = Path(folder) / (SUBS_FILE + '.lock')
    for _ in range(50):     # σύντομο κλείδωμα αρχείου για την ανάγνωση-εγγραφή
        try:
            fd = os.open(lk, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd); break
        except FileExistsError:
            try:
                if time.time() - lk.stat().st_mtime > 20:
                    lk.unlink(); continue
            except OSError:
                pass
            time.sleep(0.1)
    try:
        cur = {key(r): r for r in (load_subs(folder) or [])}
        if not path.exists():           # πρώτη φορά: ό,τι υπάρχει στο έργο
            cur = dict(a); changed = set()
        for d in changed:
            if d in a:
                cur[d] = a[d]
            else:
                cur.pop(d, None)
        out = [cur[d] for d in sorted(cur)]
        _write(path, {'records': out, 'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'by': me()['pc']})
        return out
    finally:
        try:
            lk.unlink()
        except OSError:
            pass


def mtime(path):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def cloud_folder(path):
    """Φάκελος που συγχρονίζεται από OneDrive / Google Drive / Dropbox (προειδοποίηση)."""
    s = str(path).lower()
    for k in ('onedrive', 'google drive', 'googledrive', 'dropbox', 'icloud'):
        if k in s:
            return k
    for env in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        v = os.environ.get(env)
        if v and s.startswith(v.lower()):
            return 'onedrive'
    return ''


def efimeries_exe():
    """Το «Εφημερίες Εκπαιδευτικών» αν είναι εγκατεστημένο σε αυτόν τον υπολογιστή (για μετάβαση από τη μία εφαρμογή στην άλλη)."""
    base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'Programs' / 'EfimeriesEkpaideftikon'
    for n in ('EfimeriesPortable_x64.exe', 'EfimeriesPortable_x86.exe'):
        if (base / n).exists():
            return base / n
    return None
