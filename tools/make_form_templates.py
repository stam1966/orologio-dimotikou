"""Φτιάχνει τα πρότυπα των «Εντύπων Διεύθυνσης» (src/forms/*.xlsx) από συμπληρωμένα έντυπα σχολείου.

  python tools/make_form_templates.py <Ω.Π._και_ωράριο.xlsx> <Ολοήμερο.xlsx>

Κρατά μόνο τη μορφή (στυλ, πλάτη, ύψη, συγχωνεύσεις, σελιδοποίηση) και τις σταθερές επικεφαλίδες.
Σβήνει ονόματα, αριθμούς, στοιχεία σχολείου/Διεύθυνσης και τα μεταδεδομένα του αρχείου, ώστε
να μη μπει ποτέ προσωπικό δεδομένο στο αποθετήριο. Τα αρχικά αρχεία ΔΕΝ αποθηκεύονται.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src' / 'vendor'))
import openpyxl  # noqa: E402


def clear(ws, rng):
    for row in ws[rng]:
        for c in row:
            if type(c).__name__ != 'MergedCell':
                c.value = None


def scrub(wb):
    p = wb.properties
    p.creator = p.lastModifiedBy = 'Ωρολόγιο Σχολείου'
    p.title = p.subject = p.description = p.keywords = p.category = None
    p.lastPrinted = None


def op(src, dst):
    wb = openpyxl.load_workbook(src)
    ws = wb['ΩΡΑΡΙΟ '] if 'ΩΡΑΡΙΟ ' in wb.sheetnames else wb.worksheets[0]
    ws.title = 'ΩΡΑΡΙΟ'
    clear(ws, 'A9:AH24'); clear(ws, 'A26:AH42')
    for k in ('O7', 'P7', 'Q7'):
        ws[k] = None
    ws['A25'] = 'Γ Ε Ν Ι Κ Ο  Σ Υ Ν Ο Λ Ο'
    ws.protection.sheet = False
    ws.conditional_formatting = type(ws.conditional_formatting)()
    ws2 = wb.worksheets[1]
    ws2.title = 'ΩΡΟΛΟΓΙΟ ΤΑΞΕΩΝ'
    clear(ws2, 'B3:H5'); ws2['Q4'] = None
    for top in (9, 31):
        clear(ws2, 'D%d:V%d' % (top, top + 17))
    for k in ('H7', 'N7', 'T7', 'H29', 'N29', 'T29'):
        ws2[k] = None
    scrub(wb); wb.save(dst)


def ol(src, dst):
    wb = openpyxl.load_workbook(src)
    ws = wb['ΠΡΟΓΡΑΜΜΑ']
    clear(ws, 'A6:J8'); clear(ws, 'F13:J32'); clear(ws, 'B14:B32'); clear(ws, 'D34:J36')
    ws._images = []
    ws2 = wb['ΩΡΑΡΙΟ ΕΚΠ']
    clear(ws2, 'A9:X19'); clear(ws2, 'A20:D40'); clear(ws2, 'G24:S40'); clear(ws2, 'T22:X40'); clear(ws2, 'B22:F23')
    ws2.protection.sheet = False
    scrub(wb); wb.save(dst)


if __name__ == '__main__':
    out = ROOT / 'src' / 'forms'; out.mkdir(exist_ok=True)
    op(sys.argv[1], out / 'op.xlsx'); ol(sys.argv[2], out / 'oloimero.xlsx')
    print('ok', out)
