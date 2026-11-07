import unittest, sys, json, copy, threading, re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import core, assistant, rules as R

DEMO = json.loads((Path(__file__).resolve().parents[1] / 'src' / 'demo_school.json').read_text(encoding='utf-8'))


def project():
    p = core.check_structure(copy.deepcopy(DEMO))
    p['teachers'][0]['name'] = 'Μαρία Παπαδοπούλου'; p['teachers'][1]['name'] = 'Γιώργος Νικολάου'
    return p


class Codec(unittest.TestCase):
    def test_encode_decode(self):
        p = project(); cx = assistant.Codec(p, True)
        t0 = cx.tcode[p['teachers'][0]['id']]; t1 = cx.tcode[p['teachers'][1]['id']]
        s = cx.encode_text('Η Μαρία να μην έχει πρώτη ώρα· ο κ. Νικολάου την Τρίτη.')
        self.assertNotIn('Μαρία', s); self.assertNotIn('Νικολάου', s)
        self.assertIn(t0, s); self.assertIn(t1, s)
        self.assertEqual(cx.decode_text('Ο ' + t1 + ' και ο ' + t0), 'Ο Γιώργος Νικολάου και ο Μαρία Παπαδοπούλου')
        v = cx.view(p)
        self.assertNotIn('Μαρία', json.dumps(v, ensure_ascii=False))
        ctx = assistant.context(v, cx)
        self.assertNotIn('Παπαδοπούλου', ctx); self.assertIn(t0, ctx)
        self.assertEqual(assistant.Codec(p, False).encode_text('Μαρία'), 'Μαρία')


class Config(unittest.TestCase):
    def test_save_public(self):
        import tempfile
        d = tempfile.mkdtemp()
        c = assistant.save_cfg(d, {'provider': 'openai', 'key': 'sk-secret-1234', 'model': 'gpt-x'})
        self.assertEqual(c['keys']['openai'], 'sk-secret-1234')
        pub = assistant.public_cfg(assistant.load_cfg(d))
        self.assertNotIn('sk-secret', json.dumps(pub)); self.assertEqual(pub['keys']['openai'], '…1234'); self.assertEqual(pub['models']['openai'], 'gpt-x')
        assistant.save_cfg(d, {'provider': 'openai', 'model': 'gpt-y'})  # χωρίς key: κρατά το παλιό
        self.assertEqual(assistant.load_cfg(d)['keys']['openai'], 'sk-secret-1234')
        with self.assertRaises(ValueError):
            assistant.save_cfg(d, {'provider': 'xx'})
        with self.assertRaises(ValueError):
            assistant.save_cfg(d, {'provider': 'custom', 'base': 'ftp://x'})


class Tools(unittest.TestCase):
    def setUp(self):
        self.p = project(); self.cx = assistant.Codec(self.p, True); self.v = self.cx.view(self.p)
        self.s = assistant.Session(self.v, self.cx, lambda q: core.solve(q, 10))

    def test_move_rule_availability_proposal_apply(self):
        s = self.s
        ev = next(e for e in self.v['events'] if e['place'] and not e['locked'])
        code = self.cx.ecode[ev['id']]
        out = s.run('free_slots', {'event': code})
        self.assertIn('Δυνατές θέσεις', out)
        m = re.search(r'Δυνατές θέσεις: (\w+) ([\w,]+)', out)
        if m:
            day = [d[:3] for d in self.v['days']].index(m.group(1)) + 1
            r = s.run('move', {'event': code, 'day': day, 'period': m.group(2).split(',')[0]})
            self.assertTrue(r.startswith('Έγινε'), r)
        tc = self.cx.tcode[self.p['teachers'][0]['id']]
        self.assertIn('ενημερώθηκε', s.run('set_rule', {'target_type': 'teacher', 'target': tc, 'rule': 'max_gaps_day', 'value': 1, 'weight': 3}))
        self.assertIn('ΣΦΑΛΜΑ', s.run('set_rule', {'target_type': 'teacher', 'target': tc, 'rule': 'nope', 'value': 1}))
        self.assertIn('ΣΦΑΛΜΑ', s.run('move', {'event': 'E99999', 'day': 1, 'period': '1'}))
        per = str(self.v['periods'][1]['name'])
        self.assertIn('ενημερώθηκε', s.run('set_availability', {'target_type': 'teacher', 'target': tc, 'day': 2, 'periods': [per], 'mode': 'unavailable'}))
        r = s.run('resolve', {})
        self.assertTrue(r.startswith('Επανυπολογίστηκε') or r.startswith('Δεν βρέθηκε'), r)
        self.assertIn('Διαφορές', s.run('check', {}))
        self.assertIn('πρόταση 1', s.run('save_proposal', {'title': 'Δοκιμή ' + tc, 'explanation': 'x'}))
        pr = s.proposals[0]
        self.assertTrue(pr['lines'])
        q = assistant.apply(self.p, self.cx.restore(pr['project'], self.p))
        self.assertEqual(q['teachers'][0]['name'], 'Μαρία Παπαδοπούλου')
        tid = self.p['teachers'][0]['id']
        self.assertNotIn([1, 1], q['teacher_rules'][tid]['allowed'])
        self.assertEqual(q['teacher_rules'][tid]['max_gaps_day'], {'v': 1, 'w': 3})
        s.run('reset', {}); self.assertIn('ΣΦΑΛΜΑ', s.run('save_proposal', {'title': 'κενή'}))


SCRIPT = []


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Mock.seen.append((self.path, self.headers, body))
        if body.get('model') == 'missing':
            b = json.dumps([{'error': {'code': 404, 'message': 'models/missing is not found for API version v1beta', 'status': 'NOT_FOUND'}}]).encode()
            self.send_response(404); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b); return
        step = sum(1 for m in body['messages'] if m['role'] == 'tool' or (isinstance(m.get('content'), list) and any(b.get('type') == 'tool_result' for b in m['content'])))
        calls = SCRIPT[step] if step < len(SCRIPT) else []
        if self.path.endswith('/messages'):
            content = [{'type': 'text', 'text': 'Έτοιμο για τον Τ1.'}] if not calls else [{'type': 'tool_use', 'id': 'c%d' % i, 'name': n, 'input': a} for i, (n, a) in enumerate(calls)]
            r = {'content': content, 'stop_reason': 'tool_use' if calls else 'end_turn', 'usage': {'input_tokens': 100, 'output_tokens': 10}}
        else:
            msg = {'role': 'assistant', 'content': None if calls else 'Έτοιμο για τον Τ1.'}
            if calls:
                msg['tool_calls'] = [{'id': 'c%d' % i, 'type': 'function', 'function': {'name': n, 'arguments': json.dumps(a)}} for i, (n, a) in enumerate(calls)]
            r = {'choices': [{'message': msg}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 10}}
        b = json.dumps(r).encode(); self.send_response(200); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        b = json.dumps({'data': [{'id': 'model-a'}, {'id': 'model-b'}]}).encode(); self.send_response(200); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)


class Providers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Mock.seen = []
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d/v1' % cls.srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def run_chat(self, pv):
        p = project()
        per = str(p['periods'][0]['name'])
        SCRIPT[:] = [[('set_availability', {'target_type': 'teacher', 'target': 'Τ1', 'day': 1, 'periods': [per], 'mode': 'avoid'})],
                     [('check', {})], [('save_proposal', {'title': 'Χωρίς 1η ώρα για Τ1', 'explanation': 'Ο Τ1 προτιμά να μην έχει 1η.'})]]
        cfg = {'provider': pv, 'keys': {pv: 'sk-test'}, 'models': {pv: 'm'}, 'bases': {pv: self.base}, 'anonymize': True}
        Mock.seen.clear()
        r = assistant.chat(p, [], 'Η Μαρία να μην έχει πρώτη ώρα', cfg)
        self.assertEqual(r['reply'], 'Έτοιμο για τον Μαρία Παπαδοπούλου.')
        self.assertEqual(len(r['proposals']), 1); self.assertIn('Μαρία', r['proposals'][0]['title'])
        self.assertEqual(r['proposals'][0]['project']['teachers'][0]['name'], 'Μαρία Παπαδοπούλου')
        sent = json.dumps([b for _, _, b in Mock.seen], ensure_ascii=False)
        self.assertNotIn('Μαρία', sent); self.assertNotIn('Παπαδοπούλου', sent); self.assertNotIn('Νικολάου', sent)
        return Mock.seen

    def test_anthropic(self):
        seen = self.run_chat('anthropic')
        self.assertTrue(seen[0][0].endswith('/messages')); self.assertEqual(seen[0][1]['x-api-key'], 'sk-test')

    def test_openai_compatible(self):
        seen = self.run_chat('gemini')
        self.assertTrue(seen[0][0].endswith('/chat/completions')); self.assertEqual(seen[0][1]['Authorization'], 'Bearer sk-test')

    def test_missing_model_message(self):
        cfg = {'provider': 'gemini', 'keys': {'gemini': 'k'}, 'models': {'gemini': 'missing'}, 'bases': {'gemini': self.base}, 'anonymize': True}
        with self.assertRaises(ValueError) as cm:
            assistant.chat(project(), [], 'x', cfg)
        m = str(cm.exception)
        self.assertIn('is not found', m); self.assertIn('model-a', m)

    def test_models_and_errors(self):
        cfg = {'provider': 'ollama', 'keys': {}, 'models': {}, 'bases': {'ollama': self.base}, 'anonymize': True}
        self.assertEqual(assistant.list_models(cfg), ['model-a', 'model-b'])
        with self.assertRaises(ValueError):
            assistant.chat(project(), [], 'x', {'provider': 'anthropic', 'keys': {}, 'models': {}, 'bases': {}, 'anonymize': True})


if __name__ == '__main__':
    unittest.main()
