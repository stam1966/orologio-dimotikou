"""Ένα PDF ανά εκπαιδευτικό ή τμήμα, σε ένα .zip (για αποστολή με email).
Η μετατροπή γίνεται με τον Edge/Chrome του υπολογιστή σε λειτουργία χωρίς παράθυρο."""
import io, os, re, shutil, subprocess, sys, tempfile, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import outputs


def find_browser():
    env = os.environ.get('OROLOGIO_BROWSER')
    if env and Path(env).exists():
        return env
    cands = []
    if sys.platform == 'win32':
        for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
            if base:
                cands += [Path(base) / 'Microsoft/Edge/Application/msedge.exe', Path(base) / 'Google/Chrome/Application/chrome.exe']
    for c in cands:
        if c.exists():
            return str(c)
    for name in ('msedge', 'chrome', 'chromium', 'chromium-browser', 'google-chrome'):
        w = shutil.which(name)
        if w:
            return w
    return None


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]+', ' ', s).strip()
    return s[:80] or 'ektiposi'


def to_pdf(exe, html_path, pdf_path, profile):
    args = [exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + str(profile),
            '--no-pdf-header-footer', '--print-to-pdf-no-header', '--print-to-pdf=' + str(pdf_path), Path(html_path).resolve().as_uri()]
    if sys.platform != 'win32' and hasattr(os, 'geteuid') and os.geteuid() == 0:
        args.insert(1, '--no-sandbox')  # μόνο σε Linux ως root (έλεγχοι)
    kw = {'creationflags': 0x08000000} if sys.platform == 'win32' else {}
    subprocess.run(args, capture_output=True, timeout=90, **kw)
    if not Path(pdf_path).exists() or Path(pdf_path).stat().st_size < 500:
        raise ValueError('Η δημιουργία PDF απέτυχε για: ' + Path(pdf_path).stem)


def make_zip(p, kind, opts):
    exe = find_browser()
    if not exe:
        raise ValueError('Δεν βρέθηκε Edge ή Chrome για τη δημιουργία PDF. Χρησιμοποιήστε «Εκτύπωση / PDF».')
    ents = [x for x in p[kind] if any(outputs.belongs(l, kind, x['id']) for l in p['lessons'])]
    if not ents:
        raise ValueError('Δεν υπάρχουν εγγραφές με διδασκαλίες.')
    tmp = Path(tempfile.mkdtemp(prefix='orologio_pdf_'))
    try:
        jobs = []
        for k, x in enumerate(ents):
            o = dict(opts, kind=kind, mode=opts.get('mode') if opts.get('mode') in ('individual', 'withtable') else 'individual', entity=x['id'], pdf=True)
            h = tmp / ('%03d.html' % k); h.write_text(outputs.report(p, o), encoding='utf-8')
            jobs.append((h, tmp / ('%03d.pdf' % k), tmp / ('profile%d' % (k % 4)), x['name']))
        with ThreadPoolExecutor(max_workers=4) as pool:
            # ένα προφίλ ανά νήμα: ο browser δεν επιτρέπει ταυτόχρονη χρήση ίδιου προφίλ
            groups = [jobs[i::4] for i in range(4)]
            def run(group):
                for h, pdf, prof, _ in group:
                    to_pdf(exe, h, pdf, prof)
            list(pool.map(run, groups))
        b = io.BytesIO()
        label = 'Ωρολόγιο - '
        with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
            used = set()
            for h, pdf, _, name in jobs:
                fn = safe_name(label + name)
                while fn in used:
                    fn += '_'
                used.add(fn)
                z.write(pdf, fn + '.pdf')
        return b.getvalue(), len(jobs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
