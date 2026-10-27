"""Εισαγωγή .roz (aSc) και JSON «Δεδομένα Προγράμματος». Το .roz χτίζεται συνθετικά
με τη δομή που επαληθεύτηκε σε πραγματικό αρχείο (κανένα πραγματικό δεδομένο στο αποθετήριο)."""
import unittest, sys, struct, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import core, rules as R, rozimport, gymimport

NP = 4


def rid(n):
    return bytes([n, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77])


def hdr(n, name, short=''):
    a = name.encode('cp1253'); b = short.encode('cp1253')
    return b'\x02\x00\x01\x00' + rid(n) + b'\x00' * 4 + b'\x00\x00\x00\x02' + bytes([len(a)]) + a + bytes([len(b)]) + b


def grid(cells):
    """cells: σύνολο (ημέρα, ώρα) επιτρεπτών· None = χωρίς περιορισμό (όλα 0)."""
    out = b''
    for d in range(10):
        row = [(4 if cells and (d, i) in cells else 0) for i in range(NP)] + [6] * (32 - NP)
        out += struct.pack('<32i', *row)
    return out


def build_roz(lock_first=True):
    d = bytearray(b'Z\x02\x00\x00\x05ASCTT' + b'\x00' * 40)
    n = 1
    for i in range(NP):                                     # ώρες 08:00…
        rec = b'\x02\x00\x01\x00' + rid(n) + b'\x00' * 4 + b'\x00\x00\x00\x02' + struct.pack('<i', i) + b'\x00' * 5 + struct.pack('<4i', 8 + i, 0, 8 + i, 45)
        d += rec + b'\xff' * 40; n += 1
    subj = [('ΓΛΩΣΣΑ', 'ΓΛ', None), ('ΠΡΩΙΝΗ', 'ΠΖ', {(dd, 0) for dd in range(5)})]
    for name, short, cells in subj:
        d += hdr(n, name, short) + b'\x00\xff\xff\xff\xff' + b'\x00' * 23 + grid(cells) + b'\x00' * 20; n += 1
    teach = [('Άλφα Α', 'ΑΑ', {(dd, i) for dd in range(5) for i in range(1, NP)}), ('Βήτα Β', 'ΒΒ', None)]
    for name, short, cells in teach:
        d += hdr(n, name, short) + b'\x00' * 21 + struct.pack('<i', NP) + b'\x00' * 8 + grid(cells) + b'\x00' * 20; n += 1
    groups = [('Όλο το τμήμα', 1, 0), ('Ομάδα 1', 0, 1), ('Ομάδα 2', 0, 1)]
    for name, ent, div in groups:
        a = name.encode('cp1253')
        d += b'\x02\x00\x01\x00' + rid(n) + b'\x00' * 4 + b'\x00\x00\x00\x02' + bytes([len(a)]) + a + bytes([ent, 0, 0, 0]) + struct.pack('<i', div) + b'\xff' * 12; n += 1
    d += hdr(n, 'CLASSTT', 'Α Τάξη') + b'\x01' + 'Α'.encode('cp1253') + b'\x00' + struct.pack('<i', 3) + struct.pack('<4i', 3, 0, 1, 2) + b'\x00' * 30 + grid(None); n += 1
    lessons = [(0, 0, [0], 2, 1), (1, 1, [0], 5, 1)]            # (μάθημα, εκπαιδευτικός, ομάδες, κάρτες, διάρκεια)
    for s, t, gl, cards, dur in lessons:
        body = b'\x00' * 11 + bytes([dur - 1]) + b'\x00' * 3 + struct.pack('<i', cards) + b'\x00' * 5 + struct.pack('<i', 1) + b'\x00\xf7\xf7\xf7'
        body += struct.pack('<i', s) + struct.pack('<i', len(gl)) + b''.join(struct.pack('<i', g) for g in gl) + struct.pack('<i', 1) + struct.pack('<i', t)
        d += b'\x02\x00\x01\x00' + rid(n) + b'\x00' * 4 + b'\x00\x00\x00\x02' + b'\x00\x00' + body + b'\xff' * 60; n += 1
    d += b'\x00' * 50
    cards = [(0, 1, 1, 0), (0, 2, 2, 0)] + [(1, 0, 1 << k, 1 if lock_first else 0) for k in range(5)]
    for les, per, mask, lock in cards:
        c = bytearray(75); c[10] = lock
        struct.pack_into('<i', c, 14, les); struct.pack_into('<i', c, 26, per); struct.pack_into('<i', c, 38, mask)
        d += c
    d += hdr(n, 'Master') + b'\x00' * 100
    return bytes(d)


class Roz(unittest.TestCase):
    def test_synthetic_roz(self):
        p, rep = rozimport.parse(build_roz())
        self.assertEqual([x['name'] for x in p['subjects']], ['ΓΛΩΣΣΑ', 'ΠΡΩΙΝΗ'])
        self.assertEqual([x['name'] for x in p['teachers']], ['Άλφα Α', 'Βήτα Β'])
        self.assertEqual([x['name'] for x in p['classes']], ['Α Τάξη'])
        self.assertEqual([(x['start'], x['end']) for x in p['periods']][:2], [('8:00', '8:45'), ('9:00', '9:45')])
        self.assertEqual(sorted((l['hours'], l['duration']) for l in p['lessons']), [(2, 1), (5, 1)])
        self.assertEqual(rep['counts']['placed'], 7)
        locked = [e for e in p['events'] if e['locked']]
        self.assertEqual(len(locked), 5); self.assertTrue(all(e['place'][1] == 0 for e in locked))
        t1 = p['teachers'][0]['id']
        self.assertEqual(len(p['teacher_rules'][t1]['allowed']), 5 * (NP - 1))   # όχι 1η ώρα
        self.assertNotIn(p['teachers'][1]['id'], p['teacher_rules'])            # χωρίς περιορισμό
        self.assertEqual(len(p['subject_rules'][p['subjects'][1]['id']]['allowed']), 5)
        self.assertEqual(p['teachers'][0]['id'], rid(1 + NP + 2)[::-1].hex().upper())    # ίδιο id με το XML του aSc
        self.assertEqual(p['groups'][0]['entireclass'], '1')

    def test_bad_files(self):
        for raw in (b'not roz' * 10, build_roz()[:400]):
            with self.assertRaises(ValueError):
                rozimport.parse(raw)


GYM = {
    'school': 'Δοκιμαστικό Γυμνάσιο', 'days': ['ΔΕ', 'ΤΡ', 'ΤΕ', 'ΠΕ', 'ΠΑ'], 'periods': 5, 'classes': ['Α1', 'Α2'],
    'subjects': ['ΓΛΩΣΣΑ', 'ΜΑΘΗΜΑΤΙΚΑ'],
    'teachers': [
        {'name': 'ΑΛΦΑ', 'avail': [1] * 24 + [0.5], 'cond': {'perDay': {'on': True, 'min': 1, 'max': 4}, 'kena': {'on': True, 'val': 2}, 'no2': True, 'from2': True, 'sev7': {'on': True, 'val': 1}}, 'active': True},
        {'name': 'ΒΗΤΑ', 'avail': [0] * 5 + [1] * 20, 'cond': {}, 'active': True},
        {'name': 'ΓΑΜΜΑ', 'avail': [1] * 25, 'cond': {}, 'active': True},
        {'name': 'ΔΕΛΤΑ', 'avail': [1] * 25, 'cond': {}, 'active': False}],
    'lessons': [
        {'id': 'L1', 'cls': 'Α1', 'subject': 'ΓΛΩΣΣΑ', 'teacher': 'ΑΛΦΑ', 'hours': 3, 'block': True, 'group': 'ΚΑΝ'},
        {'id': 'L2', 'cls': 'Α1', 'subject': 'ΓΛΩΣΣΑ', 'teacher': 'ΒΗΤΑ', 'hours': 3, 'block': True, 'group': 'ΤΕ'},
        {'id': 'L3', 'cls': 'Α2', 'subject': 'ΜΑΘΗΜΑΤΙΚΑ', 'teacher': 'ΓΑΜΜΑ', 'hours': 2, 'block': False, 'group': 'Όλο το τμήμα'},
        {'id': 'L4', 'cls': 'Α2', 'subject': 'ΜΑΘΗΜΑΤΙΚΑ', 'teacher': 'ΑΛΦΑ', 'hours': 2, 'block': False, 'group': 'Όλο το τμήμα'},
        {'id': 'L5', 'cls': 'Α1', 'subject': 'ΜΑΘΗΜΑΤΙΚΑ', 'teacher': 'ΔΕΛΤΑ', 'hours': 2, 'block': False, 'group': 'Όλο το τμήμα'}],
    'links': [{'id': 'K1', 'type': 'support', 'lessonIds': ['L1', 'L2'], 'note': 'Α1 Γλώσσα ΚΑΝ∥ΤΕ'},
              {'id': 'K2', 'type': 'co', 'lessonIds': ['L3', 'L4'], 'note': 'συνδιδασκαλία'}],
    'pins': []}


class GymJson(unittest.TestCase):
    def test_mapping(self):
        self.assertTrue(gymimport.is_gym_json(GYM)); self.assertFalse(gymimport.is_gym_json(core.blank()))
        p, rep = gymimport.parse(json.loads(json.dumps(GYM)))
        self.assertEqual(p['school'], 'Δοκιμαστικό Γυμνάσιο'); self.assertEqual(len(p['periods']), 5)
        self.assertEqual([t['name'] for t in p['teachers']], ['ΑΛΦΑ', 'ΒΗΤΑ', 'ΓΑΜΜΑ'])        # ΔΕΛΤΑ δεν συμμετέχει
        a = p['teacher_rules'][p['teachers'][0]['id']]
        self.assertEqual(a['avoid'], [[4, 4]]); self.assertEqual(a['max_daily']['v'], 4); self.assertEqual(a['max_gaps_day']['v'], 1)
        self.assertEqual(a['earliest'], dict(v=1, w=0, on=True))
        self.assertEqual(len(p['teacher_rules'][p['teachers'][1]['id']]['allowed']), 20)
        self.assertTrue(any('τελευταίων ωρών' in n for n in rep['notes']))
        # διώρο με 3 ώρες → διώρο + μονόωρο· δέσιμο με ομάδες → ταυτόχρονα· χωρίς ομάδες → συνδιδασκαλία
        self.assertEqual(len(p['links']), 1); self.assertEqual(len(p['links'][0]['lessons']), 4)
        sides = R.link_sides(p, p['links'][0]); self.assertEqual(sorted(len(s) for s in sides), [2, 2])
        co = [l for l in p['lessons'] if len(l['teachers']) == 2]
        self.assertEqual(len(co), 1); self.assertEqual(co[0]['hours'], 2)
        g = {x['name']: x for x in p['groups']}
        self.assertEqual(g['ΚΑΝ']['divisiontag'], g['ΤΕ']['divisiontag'])
        core.check_structure(p)
