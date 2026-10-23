"""Ρυθμίσεις εφαρμογής, ημερήσιο αντίγραφο σε φάκελο επιλογής, σημεία επαναφοράς, καθάρισμα.
Οι ρυθμίσεις αφορούν τον υπολογιστή (data/settings.json), όχι το έργο."""
import json, os, re, shutil, string, sys, time
from datetime import datetime, timedelta
from pathlib import Path

DEFAULTS = {'backup_dir': '', 'check_updates': None, 'tour_done': False, 'last_backup': '', 'last_update_check': ''}


def settings_path(root):
    return Path(root) / 'data' / 'settings.json'


def load_settings(root):
    try:
        s = json.loads(settings_path(root).read_text(encoding='utf-8'))
    except Exception:
        s = {}
    return {**DEFAULTS, **{k: v for k, v in s.items() if k in DEFAULTS}}


def save_settings(root, s):
    p = settings_path(root); p.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: s.get(k, DEFAULTS[k]) for k in DEFAULTS}
    tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding='utf-8'); os.replace(tmp, p)
    return clean


def check_folder(path):
    """Ελέγχει ότι ο φάκελος υπάρχει και επιτρέπει εγγραφή."""
    if not path:
        return ''
    p = Path(path).expanduser()
    if not p.is_dir():
        raise ValueError('Ο φάκελος δεν υπάρχει: ' + str(p))
    test = p / '.orologio_test'
    try:
        test.write_text('ok', encoding='utf-8'); test.unlink()
    except OSError:
        raise ValueError('Δεν επιτρέπεται εγγραφή στον φάκελο: ' + str(p))
    return str(p)


def suggestions():
    """Προτεινόμενοι φάκελοι: Έγγραφα, OneDrive, αφαιρούμενοι δίσκοι (USB)."""
    out = []
    home = Path.home()
    for label, p in (('Έγγραφα', home / 'Documents'), ('OneDrive', Path(os.environ['OneDrive']) if os.environ.get('OneDrive') else None)):
        if p and p.is_dir():
            out.append({'label': label, 'path': str(p / 'Ωρολόγιο - αντίγραφα')})
    if sys.platform == 'win32':
        try:
            import ctypes
            for letter in string.ascii_uppercase[3:]:
                root = letter + ':\\'
                if ctypes.windll.kernel32.GetDriveTypeW(root) == 2:  # DRIVE_REMOVABLE
                    out.append({'label': 'USB ' + letter + ':', 'path': root + 'Ωρολόγιο - αντίγραφα'})
        except Exception:
            pass
    return out


def ensure_folder(path):
    p = Path(path)
    if not p.exists():
        parent = p.parent
        if not parent.is_dir():
            raise ValueError('Δεν βρέθηκε ο φάκελος: ' + str(parent))
        p.mkdir()
    return check_folder(str(p))


def write_backup(root, project_path, folder, keep=60):
    """Αντίγραφο του έργου στον φάκελο, ένα ανά ημέρα (αντικαθίσταται μέσα στην ίδια ημέρα)."""
    folder = Path(folder)
    if not Path(project_path).exists():
        return None
    name = 'Orologio_' + datetime.now().strftime('%Y-%m-%d') + '.json'
    tmp = folder / (name + '.tmp')
    shutil.copy2(project_path, tmp); os.replace(tmp, folder / name)
    olds = sorted(folder.glob('Orologio_????-??-??.json'))
    for f in olds[:-keep]:
        try:
            f.unlink()
        except OSError:
            pass
    return str(folder / name)


def daily(root, project_path, force=False):
    """Καλείται κατά την εκκίνηση και ανά ώρα· γράφει αντίγραφο αν δεν έχει γραφτεί σήμερα."""
    s = load_settings(root)
    if not s['backup_dir']:
        return None
    today = datetime.now().strftime('%Y-%m-%d')
    if s['last_backup'] == today and not force:
        return None
    path = write_backup(root, project_path, check_folder(s['backup_dir']))
    s['last_backup'] = today; save_settings(root, s)
    return path


STAMP = re.compile(r'project_(\d{8})_(\d{6})')


def points(root):
    """Σημεία επαναφοράς από data/backups (τα αντίγραφα πριν από κάθε αποθήκευση)."""
    out = []
    for f in sorted((Path(root) / 'data' / 'backups').glob('project_*.json'), reverse=True):
        m = STAMP.search(f.name)
        if not m:
            continue
        try:
            t = datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
        except ValueError:
            continue
        out.append({'name': f.name, 'when': t.strftime('%d/%m/%Y %H:%M:%S'), 'day': t.strftime('%d/%m/%Y'), 'size': f.stat().st_size})
    return out


def prune(root, keep_recent=150, days_daily=180):
    """Κρατά τα 150 πιο πρόσφατα και, για τα παλαιότερα, ένα ανά ημέρα (έως 180 ημέρες)."""
    files = []
    for f in (Path(root) / 'data' / 'backups').glob('project_*.json'):
        m = STAMP.search(f.name)
        if m:
            files.append((m.group(1) + m.group(2), f))
    files.sort(reverse=True)
    seen_days = set(); limit = (datetime.now() - timedelta(days=days_daily)).strftime('%Y%m%d')
    removed = 0
    for k, (stamp, f) in enumerate(files):
        if k < keep_recent:
            seen_days.add(stamp[:8]); continue
        day = stamp[:8]
        if day in seen_days or day < limit:
            try:
                f.unlink(); removed += 1
            except OSError:
                pass
        else:
            seen_days.add(day)
    return removed


def _drives():
    out = []
    if sys.platform == 'win32':
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            kinds = {2: 'Αφαιρούμενος δίσκος (USB)', 3: 'Τοπικός δίσκος', 4: 'Δίσκος δικτύου', 5: 'CD/DVD'}
            for i, letter in enumerate(string.ascii_uppercase):
                if mask & (1 << i):
                    root = letter + ':\\'
                    t = ctypes.windll.kernel32.GetDriveTypeW(root)
                    if t == 5:
                        continue
                    out.append({'label': letter + ': ' + kinds.get(t, 'Δίσκος'), 'path': root, 'usb': t == 2})
        except Exception:
            pass
    else:
        out.append({'label': '/', 'path': '/', 'usb': False})
    return out


def browse(path=''):
    """Πλοήγηση φακέλων για την επιλογή φακέλου αντιγράφων.
    Χωρίς διαδρομή: γνωστοί φάκελοι και δίσκοι. Με διαδρομή: οι υποφάκελοί της."""
    if not path:
        home = Path.home()
        places = []
        for label, p in (('Έγγραφα', home / 'Documents'), ('Επιφάνεια εργασίας', home / 'Desktop'),
                         ('OneDrive', Path(os.environ['OneDrive']) if os.environ.get('OneDrive') else None),
                         ('Λήψεις', home / 'Downloads'), ('Προσωπικός φάκελος', home)):
            if p and p.is_dir():
                places.append({'label': label, 'path': str(p)})
        return {'path': '', 'parent': None, 'places': places, 'drives': _drives(), 'dirs': [], 'crumbs': [], 'writable': False}
    p = Path(path).expanduser()
    if not p.is_dir():
        raise ValueError('Ο φάκελος δεν υπάρχει: ' + str(p))
    dirs = []
    try:
        for c in p.iterdir():
            try:
                if c.is_dir() and not c.name.startswith(('.', '$')) and c.name not in ('System Volume Information', '__pycache__'):
                    dirs.append(c.name)
            except OSError:
                continue
    except PermissionError:
        raise ValueError('Δεν επιτρέπεται η πρόσβαση στον φάκελο: ' + str(p))
    dirs.sort(key=str.casefold)
    parent = str(p.parent) if p.parent != p else ''
    try:
        check_folder(str(p)); writable = True
    except ValueError:
        writable = False
    crumbs = [{'label': (q.name or str(q)).rstrip('\\/') or str(q), 'path': str(q)} for q in reversed([p, *p.parents])]
    return {'path': str(p), 'parent': parent, 'places': [], 'drives': [], 'crumbs': crumbs,
            'dirs': [{'name': d, 'path': str(p / d)} for d in dirs[:500]], 'writable': writable}


BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def make_dir(parent, name):
    name = (name or '').strip().rstrip('.')
    if not name or BAD_NAME.search(name) or name in ('.', '..'):
        raise ValueError('Μη έγκυρο όνομα φακέλου (δεν επιτρέπονται οι χαρακτήρες < > : " / \\ | ? *).')
    p = Path(parent)
    if not p.is_dir():
        raise ValueError('Ο φάκελος δεν υπάρχει: ' + str(p))
    q = p / name
    try:
        q.mkdir(exist_ok=True)
    except OSError as ex:
        raise ValueError('Δεν ήταν δυνατή η δημιουργία του φακέλου: ' + str(ex))
    return str(q)
