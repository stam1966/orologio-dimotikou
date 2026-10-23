"""Κατασκευή πακέτων εφαρμογής.

  python tools/build_package.py               → dist/Orologio_Dimotikou (πλήρης φάκελος με runtime),
                                                 dist/*_Egkatastasi.zip και dist/Orologio_Enimerosi_*.zip
  python tools/build_package.py --runtime-from <φάκελος runtime>   → χρήση υπάρχοντος runtime αντί για λήψη
  python tools/build_package.py --update-only                       → μόνο το αρχείο ενημέρωσης

Το runtime: Python 3.12 «embeddable» για Windows 64-bit + οι βιβλιοθήκες του requirements-runtime.txt.
Ποτέ δεν μπαίνουν δεδομένα σχολείου (φάκελος data) στα πακέτα.
"""
import io, json, os, re, shutil, subprocess, sys, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
PY_VERSION = '3.12.10'
EMBED_URL = 'https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip' % (PY_VERSION, PY_VERSION)
APP = 'Orologio_Dimotikou'
SRC_FILES = ['core.py', 'rules.py', 'outputs.py', 'server.py', 'updater.py', 'preflight.py', 'asc.py', 'pdfs.py', 'versions.py',
             'backup.py', 'xlimport.py', 'index.html', 'manual.html', 'app.ico', 'demo_school.json']
TOP_FILES = ['START.cmd', 'START_KONSOLA.cmd', 'SYNTOMEFSI.cmd', 'CHECK.cmd', 'ΕΓΚΑΤΑΣΤΑΣΗ.cmd', 'ΑΠΕΓΚΑΤΑΣΤΑΣΗ.cmd', 'README_EL.txt', 'CHANGELOG.txt']


def version():
    return re.search(r"VERSION = '([^']+)'", (ROOT / 'src/core.py').read_text(encoding='utf-8')).group(1)


def app_files():
    files = {}
    for n in SRC_FILES:
        if (ROOT / 'src' / n).exists():
            files['src/' + n] = (ROOT / 'src' / n).read_bytes()
    for p in sorted((ROOT / 'tests').glob('test_*.py')):
        files['tests/' + p.name] = p.read_bytes()
    for n in TOP_FILES:
        if (ROOT / n).exists():
            files[n] = (ROOT / n).read_bytes()
    for p in sorted(ROOT.glob('UPDATE_*.txt')):
        files[p.name] = p.read_bytes()
    return files


def notes(v):
    p = ROOT / ('UPDATE_' + v.split('-')[0] + '.txt')
    return p.read_text(encoding='utf-8') if p.exists() else ''


def build_update(v, files):
    DIST.mkdir(exist_ok=True)
    out = DIST / ('Orologio_Enimerosi_' + v.split('-')[0] + '.zip')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('orologio-update.json', json.dumps({'app': 'orologio-dimotikou', 'version': v, 'notes': notes(v)}, ensure_ascii=False, indent=1))
        for n, b in sorted(files.items()):
            z.writestr(n, b)
    print('update:', out, out.stat().st_size)
    return out


def build_runtime(target):
    """Python embeddable + βιβλιοθήκες (μόνο έτοιμα πακέτα Windows 64-bit, cp312)."""
    target.mkdir(parents=True, exist_ok=True)
    print('download', EMBED_URL)
    raw = urllib.request.urlopen(EMBED_URL, timeout=120).read()
    zipfile.ZipFile(io.BytesIO(raw)).extractall(target)
    (target / ('python%s._pth' % PY_VERSION.replace('.', '')[:3])).write_text('python312.zip\n.\nLib/site-packages\n../src\nimport site\n', encoding='ascii')
    site = target / 'Lib' / 'site-packages'; site.mkdir(parents=True, exist_ok=True)
    pip = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-compile', '--only-binary=:all:',
           '--platform', 'win_amd64', '--python-version', '3.12', '--implementation', 'cp', '--target', str(site),
           '-r', str(ROOT / 'requirements-runtime.txt')]
    subprocess.run(pip, check=True)
    # Τα DLL του Visual C++ (πακέτο msvc-runtime) στη ρίζα του runtime, δίπλα στο python.exe
    for dll in site.rglob('*.dll'):
        if re.match(r'(msvcp140|vcruntime140|concrt140|vcomp140|vcamp140|vccorlib140)', dll.name, re.I) and 'msvc_runtime' in str(dll).replace('\\', '/').lower():
            shutil.copy2(dll, target / dll.name)
    for d in list(site.rglob('__pycache__')):
        shutil.rmtree(d, ignore_errors=True)


def build_full(v, files, runtime_from=None):
    folder = DIST / APP
    if folder.exists():
        shutil.rmtree(folder)
    if runtime_from:
        shutil.copytree(runtime_from, folder / 'runtime', ignore=shutil.ignore_patterns('__pycache__'))
    else:
        build_runtime(folder / 'runtime')
    for n, b in files.items():
        p = folder / n; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
    (folder / 'data').mkdir(exist_ok=True)
    (folder / 'data' / 'README.txt').write_text('Εδώ αποθηκεύονται τα δεδομένα του σχολείου σας (project.json) και τα αντίγραφα ασφαλείας.\n', encoding='utf-8')
    out = DIST / ('Orologio_Dimotikou_' + v.split('-')[0] + '_Egkatastasi.zip')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                z.write(p, APP + '/' + p.relative_to(folder).as_posix())
    print('full:', out, out.stat().st_size)
    return folder


if __name__ == '__main__':
    v = version(); files = app_files()
    build_update(v, files)
    if '--update-only' not in sys.argv:
        rf = sys.argv[sys.argv.index('--runtime-from') + 1] if '--runtime-from' in sys.argv else None
        build_full(v, files, rf)
    DIST.mkdir(exist_ok=True)
    (DIST / 'VERSION.txt').write_text(v, encoding='utf-8')
    (DIST / 'RELEASE_NOTES.md').write_text(
        '**Νέα εγκατάσταση:** κατεβάστε το `Orologio_Dimotikou_Setup.exe` και ανοίξτε το.\n\n'
        'Μόνιμος σύνδεσμος λήψης (πάντα η τελευταία έκδοση): '
        'https://github.com/stam1966/orologio-dimotikou/releases/latest/download/Orologio_Dimotikou_Setup.exe\n\n'
        '**Ενημέρωση υπάρχουσας εγκατάστασης:** μέσα στην εφαρμογή «Σχολείο & ωράριο → Ενημέρωση» '
        '(ή σύρετε το `Orologio_Enimerosi_….zip` στο παράθυρο).\n\n```\n' + notes(v) + '\n```\n', encoding='utf-8')
