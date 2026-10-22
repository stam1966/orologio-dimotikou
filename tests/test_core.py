import unittest,sys,tempfile,json,copy,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import core

def fixture():
    p=core.blank();p['periods']=[dict(id=str(i),name=str(i+1),start=f'{8+i:02}:00',end=f'{8+i:02}:45') for i in range(4)]
    p['teachers']=[dict(id='t',name='Δοκιμή',short='Δ')];p['classes']=[dict(id='c',name='Α',short='Α')];p['subjects']=[dict(id='s',name='Μάθημα',short='Μ')]
    p['lessons']=[dict(id='l',subject='s',teachers=['t'],classes=['c'],groups=[],room='',hours=2,duration=1,days=[0],max_daily=0)]
    p['events']=[dict(id='e1',lesson='l',place=[0,0],locked=False),dict(id='e2',lesson='l',place=[0,2],locked=False)]
    return p
class Tests(unittest.TestCase):
    def test_atomic_swap(self):
        p=fixture();old=copy.deepcopy(p)
        q=core.move_event(p,'e1',[0,2],'e2')
        self.assertEqual([e['place'] for e in q['events']],[[0,2],[0,0]])
        self.assertEqual(p,old)
        p['events'][1]['locked']=True
        with self.assertRaises(ValueError):core.move_event(p,'e1',[0,2],'e2')
    def test_rejected_move_preserves_source(self):
        p=fixture();old=copy.deepcopy(p)
        with self.assertRaises(ValueError):core.move_event(p,'e1',[0,2])
        self.assertEqual(p,old)
    def test_swap_duration_collision(self):
        p=fixture();p['lessons'][0]['duration']=2;p['lessons'][0]['hours']=4
        p['events'][1]['place']=[0,3];old=copy.deepcopy(p)
        with self.assertRaises(ValueError):core.move_event(p,'e1',[0,3],'e2')
        self.assertEqual(p,old)
    def test_reference(self):
        # Τα πραγματικά δεδομένα του σχολείου: φορτώνονται, ελέγχονται και εκτυπώνονται χωρίς σφάλμα.
        path=Path(__file__).resolve().parents[1]/'data/project.json'
        if not path.exists():self.skipTest('Δεν υπάρχει ακόμη έργο.')
        import outputs
        p=core.load(path);core.findings(p,True)
        self.assertEqual(sum(l['hours'] for l in p['lessons']),sum(l['duration']*sum(1 for e in p['events'] if e['lesson']==l['id']) for l in p['lessons']))
        outputs.report(p,dict(kind='teachers',mode='poster'));outputs.export_xlsx(p)
    def test_teacher_collision(self):
        p=fixture();p['events'][1]['place']=[0,0];self.assertTrue(any('Σύγκρουση' in x for x in core.validation(p)))
    def test_gap_limit(self):
        p=fixture();p['teacher_rules']['t']={'max_gaps_day':0};self.assertTrue(core.validation(p));r=core.solve(p,5);self.assertIn(r['status'],['optimal','feasible']);self.assertEqual(core.validation(r['project'],True),[])
    def test_locked_impossible(self):
        p=fixture();p['events'][0]['locked']=True;p['teacher_rules']['t']={'allowed':[[0,2],[0,3]]};old=copy.deepcopy(p);r=core.solve(p,5);self.assertEqual(r['status'],'infeasible');self.assertEqual(p,old)
    def test_unavailable_placement(self):
        p=fixture();p['class_rules']['c']={'allowed':[[0,0]]};self.assertTrue(core.validation(p))
    def test_start_counts(self):
        p=fixture();p['teacher_rules']['t']={'start_counts':{'1':1},'max_gaps_day':0};r=core.solve(p,5);self.assertIn(r['status'],['optimal','feasible']);self.assertEqual(min(e['place'][1] for e in r['project']['events']),1)
    def test_double_block(self):
        p=fixture();p['lessons'][0]['duration']=2;p['events']=p['events'][:1];p['events'][0]['place']=[0,3];self.assertTrue(core.validation(p));r=core.solve(p,5);self.assertEqual(core.validation(r['project'],True),[])
    def test_unknown_reference(self):
        p=fixture();p['lessons'][0]['teachers']=['missing']
        with self.assertRaises(ValueError):core.check_structure(p)
    def test_save_backup(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'p.json';p=fixture();core.save(p,path);p['title']='Νέο';core.save(p,path);self.assertEqual(core.load(path),p);backup=list((Path(d)/'backups').glob('*.json'));self.assertEqual(len(backup),1);self.assertNotEqual(core.load(backup[0])['title'],'Νέο')
    def test_groups_parallel(self):
        p=fixture();p['groups']=[dict(id='g1',classid='c',entireclass='0',divisiontag='1'),dict(id='g2',classid='c',entireclass='0',divisiontag='1')]
        a=copy.deepcopy(p['lessons'][0]);b=copy.deepcopy(a);a['groups']=['g1'];b['groups']=['g2'];a['teachers']=[];b['teachers']=[]
        self.assertFalse(core.resources(p,a)&core.resources(p,b));b['groups']=[];self.assertTrue(core.resources(p,a)&core.resources(p,b))
    def test_cancel(self):
        p=fixture();c=threading.Event();c.set();r=core.solve(p,5,c);self.assertEqual(r['status'],'cancelled');self.assertNotIn('project',r)
    def test_daily_limit_impossible(self):
        p=fixture();p['teacher_rules']['t']={'max_daily':1};self.assertEqual(core.solve(p,5)['status'],'infeasible')
if __name__=='__main__':unittest.main(verbosity=2)
