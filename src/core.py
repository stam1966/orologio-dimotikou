"""Independent timetable model. No aSc binaries or code required."""
import copy, json, os, re, tempfile, uuid, itertools
import rules as R
from pathlib import Path
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET

VERSION = '0.5.0-beta'
DAYS = ['Δευτέρα','Τρίτη','Τετάρτη','Πέμπτη','Παρασκευή']
def uid(): return uuid.uuid4().hex[:16]
def blank():
    return dict(schema=1,version=VERSION,title='Ωρολόγιο Δημοτικού',school='',year='',days=DAYS[:],periods=[],teachers=[],classes=[],subjects=[],rooms=[],groups=[],lessons=[],events=[],teacher_rules={},class_rules={},subject_rules={},global_rules={'min_gaps':{'w':1,'on':True}})
def mapping(p,k): return {x['id']:x for x in p[k]}
def split(s): return [x for x in s.split(',') if x]
def slots(p): return [[d,i] for d in range(5) for i in range(len(p['periods']))]
def import_xml(raw):
    if len(raw)>10_000_000: raise ValueError('Το XML υπερβαίνει τα 10 MB.')
    r=ET.fromstring(raw)
    if r.tag=='orologio':
        from outputs import import_native
        return import_native(r)
    if r.tag!='timetable':raise ValueError('Αναμένεται XML aSc TimeTables.')
    p=blank(); p['source_version']=r.get('ascttversion','');p['title']='Πρόγραμμα από XML'
    def rows(k):return [x.attrib for x in r.findall(k+'/*')]
    per=sorted(rows('periods'),key=lambda x:int(x['period']))
    p['periods']=[dict(id=x['period'],name=x.get('name',x['period']),start=x['starttime'],end=x['endtime']) for x in per]
    pi={x['id']:i for i,x in enumerate(p['periods'])}
    for key,src in [('teachers','teachers'),('subjects','subjects'),('classes','classes'),('rooms','classrooms')]:
        p[key]=[dict(id=x['id'],name=x['name'],short=x.get('short',x['name'])) for x in rows(src)]
    # Χρώμα εκπαιδευτικού και υπεύθυνος τμήματος, όπως ορίζονται στο aSc
    tcol={x['id']:x.get('color','') for x in rows('teachers')}
    for t in p['teachers']:
        c=tcol.get(t['id'],'')
        if re.fullmatch(r'#[0-9A-Fa-f]{6}',c or ''):t['color']=c.upper()
    tids={t['id'] for t in p['teachers']};ctea={x['id']:x.get('teacherid','') for x in rows('classes')}
    for c in p['classes']:
        if ctea.get(c['id']) in tids:c['teacher']=ctea[c['id']]
    p['groups']=rows('groups')
    for x in rows('weeksdefs'):
        if x['weeks']!='1':raise ValueError('Η πρώτη έκδοση υποστηρίζει ένα εβδομαδιαίο πρόγραμμα.')
    for x in rows('termsdefs'):
        if x['terms']!='1':raise ValueError('Δεν υποστηρίζονται πολλαπλές περίοδοι έτους.')
    dd={x['id']:x['days'] for x in rows('daysdefs')}
    cards=defaultdict(list)
    for x in rows('cards'):
        if len(x['days'])!=5 or x.get('weeks','1')!='1' or x.get('terms','1')!='1':raise ValueError('Μη υποστηριζόμενη εβδομάδα / ημέρες.')
        for d,b in enumerate(x['days']):
            if b=='1':cards[x['lessonid']].append((d,pi[x['period']]))
    for x in rows('lessons'):
        dur=int(x['periodspercard']);hours=float(x['periodsperweek'])
        if dur<1 or not hours.is_integer() or int(hours)%dur:raise ValueError('Μη ακέραιη κατανομή ωρών στην ανάθεση '+x['id'])
        rooms=split(x.get('classroomids',''))
        if len(rooms)>1:raise ValueError('Η πρώτη έκδοση απαιτεί μία σταθερή αίθουσα ανά ανάθεση.')
        days=dd.get(x.get('daysdefid'),'10000,01000,00100,00010,00001')
        allowed=sorted({i for bit in days.split(',') for i,b in enumerate(bit) if b=='1'})
        l=dict(id=x['id'],subject=x['subjectid'],teachers=split(x['teacherids']),classes=split(x['classids']),groups=split(x.get('groupids','')),room=rooms[0] if rooms else '',hours=int(hours),duration=dur,days=allowed,max_daily=0)
        p['lessons'].append(l)
        remaining=sorted(cards.pop(x['id'],[]))
        placements=[]
        while remaining:
            d,i=remaining[0];chunk=[(d,i+j) for j in range(dur)]
            if not all(a in remaining for a in chunk):raise ValueError('Οι συνεχόμενες ώρες δεν ομαδοποιούνται με ασφάλεια: '+x['id'])
            for a in chunk:remaining.remove(a)
            placements.append([d,i])
        if len(placements)>int(hours)//dur:raise ValueError('Περισσότερες τοποθετήσεις από τις ώρες ανάθεσης.')
        for n in range(int(hours)//dur):p['events'].append(dict(id=uid(),lesson=l['id'],place=placements[n] if n<len(placements) else None,locked=False))
    if cards:raise ValueError('Το XML έχει τοποθετήσεις άγνωστης ανάθεσης.')
    # Suggested class windows only; teacher availability is never inferred.
    for c in p['classes']:
        observed=set()
        for e in p['events']:
            l=next(l for l in p['lessons'] if l['id']==e['lesson'])
            if c['id'] in l['classes'] and e['place']:
                observed.update(range(e['place'][1],e['place'][1]+l['duration']))
        p['class_rules'][c['id']]=dict(allowed=[[d,i] for d in range(5) for i in sorted(observed)] if observed else slots(p))
    check_structure(p)
    return p

def check_structure(p):
    if p.get('schema')!=1:raise ValueError('Μη υποστηριζόμενη μορφή έργου.')
    if len(p['days'])!=5 or not 1<=len(p['periods'])<=20:raise ValueError('Απαιτούνται 5 ημέρες και 1–20 περίοδοι.')
    for key in ['teachers','classes','subjects','rooms','groups','lessons','events']:
        ids=[x['id'] for x in p[key]]
        if len(ids)!=len(set(ids)):raise ValueError('Διπλό αναγνωριστικό: '+key)
    for period in p['periods']:
        for k in ['start','end']:
            h,m=map(int,period[k].split(':'))
            if not (0<=h<24 and 0<=m<60):raise ValueError('Μη έγκυρη ώρα.')
        if minutes(period['start'])>=minutes(period['end']):raise ValueError('Η λήξη περιόδου πρέπει να είναι μετά την έναρξη.')
    for a,b in zip(p['periods'],p['periods'][1:]):
        if minutes(a['end'])>minutes(b['start']):raise ValueError('Επικάλυψη χρονικών περιόδων.')
    ids={k:set(mapping(p,k)) for k in ['teachers','classes','subjects','rooms','groups','lessons']}
    for g in p['groups']:
        if g['classid'] not in ids['classes']:raise ValueError('Άγνωστο τμήμα ομάδας.')
    for l in p['lessons']:
        if l['subject'] not in ids['subjects']:raise ValueError('Άγνωστο μάθημα.')
        for k in ['teachers','classes','groups']:
            if not set(l[k])<=ids[k]:raise ValueError('Άγνωστη αναφορά '+k)
        if not l['teachers']:raise ValueError('Κάθε ανάθεση χρειάζεται εκπαιδευτικό.')
        if l['room'] and l['room'] not in ids['rooms']:raise ValueError('Άγνωστη αίθουσα.')
        if not isinstance(l['hours'],int) or not isinstance(l['duration'],int) or l['hours']<1 or not 1<=l['duration']<=len(p['periods']) or l['hours']%l['duration']:raise ValueError('Οι ώρες πρέπει να διαιρούνται με τη διάρκεια.')
        if not l['days'] or any(d not in range(5) for d in l['days']):raise ValueError('Μη έγκυρες ημέρες.')
        if not isinstance(l.get('max_daily',0),int) or l.get('max_daily',0)<0:raise ValueError('Μη έγκυρο ημερήσιο όριο μαθήματος.')
    counts=Counter(e['lesson'] for e in p['events'])
    for e in p['events']:
        if e['lesson'] not in ids['lessons']:raise ValueError('Άγνωστη ανάθεση τοποθέτησης.')
        if e['locked'] and e['place'] is None:raise ValueError('Δεν κλειδώνεται ατοποθέτητη διδασκαλία.')
        if e['place'] is not None:
            if len(e['place'])!=2 or any(type(v)!=int for v in e['place']) or e['place'][0] not in range(5) or e['place'][1] not in range(len(p['periods'])):raise ValueError('Μη έγκυρη θέση.')
    for l in p['lessons']:
        if counts[l['id']]!=l['hours']//l['duration']:raise ValueError('Ασυμφωνία πλήθους διδασκαλιών.')
    n=len(p['periods'])
    for t in p['teachers']:
        if t.get('color') and not re.fullmatch(r'#[0-9A-Fa-f]{6}',t['color']):raise ValueError('Μη έγκυρο χρώμα εκπαιδευτικού.')
    for c in p['classes']:
        if c.get('teacher') and c['teacher'] not in ids['teachers']:raise ValueError('Άγνωστος υπεύθυνος τμήματος.')
    for l in p['lessons']:
        if type(l.get('exempt_subject_limit',False))!=bool:raise ValueError('Μη έγκυρη εξαίρεση ανάθεσης.')
    for key,entities in [('teacher_rules','teachers'),('class_rules','classes'),('subject_rules','subjects')]:
        for id,rule in p.get(key,{}).items():
            if id not in ids[entities]:raise ValueError('Κανόνας άγνωστης οντότητας.')
            for field in ('allowed','avoid'):
                for d,i in rule.get(field,[]):
                    if type(d)!=int or type(i)!=int or d not in range(5) or i not in range(n):raise ValueError('Μη έγκυρη διαθεσιμότητα.')
            if rule.get('avoid_w',3) not in (1,2,3,4,5):raise ValueError('Μη έγκυρη βαρύτητα θέσεων «υπό όρους».')
            for k,v in rule.items():
                if k in ('allowed','avoid','avoid_w','start_counts'):continue
                if k not in R.TYPES[entities]:raise ValueError('Άγνωστος κανόνας: '+k)
                R.check_rule_value(entities,k,v,n)
            mx=R.norm(rule.get('max_daily'));mn=R.norm(rule.get('min_daily'))
            if mx and mn and mx['w']==0 and mn['w']==0 and mn['v']>mx['v']:raise ValueError('Ελάχιστο μεγαλύτερο από μέγιστο.')
            for k,v in rule.get('start_counts',{}).items():
                if int(k) not in range(n) or type(v)!=int or not 0<=v<=5:raise ValueError('Μη έγκυρος αριθμός ημερών έναρξης.')
    for c in p['classes']:
        if c.get('grade') is not None and (type(c['grade'])!=str or len(c['grade'])>10):raise ValueError('Μη έγκυρη τάξη τμήματος.')
    cur=p.get('curriculum',{})
    if not isinstance(cur,dict):raise ValueError('Μη έγκυρο επίσημο ωρολόγιο.')
    for gr,row in cur.items():
        if type(gr)!=str or not isinstance(row,dict):raise ValueError('Μη έγκυρο επίσημο ωρολόγιο.')
        for sid,h in row.items():
            if sid not in ids['subjects'] or type(h)!=int or not 0<=h<=40:raise ValueError('Μη έγκυρη τιμή στο επίσημο ωρολόγιο.')
    g=p.get('global_rules',{}).get('min_gaps')
    if g is not None and (not isinstance(g,dict) or g.get('w',1) not in (1,2,3,4,5)):raise ValueError('Μη έγκυρος γενικός κανόνας κενών.')
    return p

def minutes(s):h,m=map(int,s.split(':'));return 60*h+m

def resources(p,l):return R.resources(p,l)
def candidates(p,l):return R.candidates(p,l)

def slot_status(p,event_id):
    """Για χειροκίνητη μετακίνηση. Επιστρέφει {'st':{"d,i":κατάσταση}, 'why':{"d,i":αιτιολογία}}.
    Κατάσταση: ok / maybe (θέση «υπό όρους») / busy (σύγκρουση) / no (απαγορεύεται από κανόνα)."""
    ls=mapping(p,'lessons');e=next(x for x in p['events'] if x['id']==event_id);l=ls[e['lesson']];n=len(p['periods']);dur=l['duration']
    em={t:r for t,r in R.earliest_map(p).items() if r['w']==0}
    res=R.resources(p,l);occ={}
    tday={};subjday={};lessonday={};dayend_subj={}
    S=mapping(p,'subjects');T=mapping(p,'teachers');C=mapping(p,'classes')
    for x in p['events']:
        if x['id']==event_id or not x['place']:continue
        lx=ls[x['lesson']];d0,i0=x['place']
        for j in range(i0,i0+lx['duration']):
            for r in R.resources(p,lx):occ[(r,d0,j)]=lx
            for t in lx['teachers']:tday.setdefault((t,d0),set()).add(j)
        if not lx.get('exempt_subject_limit'):
            for c in lx['classes']:subjday[(lx['subject'],c,d0)]=subjday.get((lx['subject'],c,d0),0)+1
        lessonday[(lx['id'],d0)]=lessonday.get((lx['id'],d0),0)+lx['duration']
        for t in lx['teachers']:
            r=R.rule(p,'subjects',lx['subject'],'day_end')
            if r and r['w']==0:dayend_subj.setdefault((t,d0),[]).append((r['v'],lx['subject']))
    av=[(R.avoid(p,'teachers',t)[0],T[t]['name']) for t in l['teachers']]+[(R.avoid(p,'classes',c)[0],C[c]['name']) for c in l['classes']]+[(R.avoid(p,'subjects',l['subject'])[0],S[l['subject']]['name'])]
    lim=R.subject_limit(p,l['subject']);own_end=R.rule(p,'subjects',l['subject'],'day_end')
    st={};why={}
    def who(lx):
        return S[lx['subject']]['name']+' ('+', '.join(C[c].get('short') or C[c]['name'] for c in lx['classes'])+(', ' if lx['classes'] else '')+', '.join(T[t]['name'] for t in lx['teachers'])+')'
    for d in range(5):
        for i in range(n):
            k=f'{d},{i}';cover=range(i,i+dur)
            if i>n-dur:st[k]='no';why[k]='Δεν χωράει: χρειάζονται '+str(dur)+' συνεχόμενες ώρες.';continue
            keys=R.forbid_keys(p,l,d,i,em)
            if keys:st[k]='no';why[k]='; '.join(R.describe(p,x) for x in keys);continue
            clash=[]
            for j in cover:
                for r in res:
                    if (r,d,j) in occ:
                        lx=occ[(r,d,j)];sn=S[lx['subject']]['name']
                        if r.startswith('t:'):txt=T[r[2:]]['name']+': διδάσκει ήδη '+sn+(' στο '+', '.join(C[c]['name'] for c in lx['classes']) if lx['classes'] else '')+' ('+p['periods'][j]['name']+'η ώρα)'
                        elif r.startswith('c:'):txt=C[r.split(':')[1]]['name']+': έχει ήδη '+sn+' με '+', '.join(T[t]['name'] for t in lx['teachers'])+' ('+p['periods'][j]['name']+'η ώρα)'
                        else:txt='Η αίθουσα είναι κατειλημμένη: '+who(lx)
                        if txt not in clash:clash.append(txt)
            if clash:st[k]='busy';why[k]='; '.join(clash);continue
            rules=[]
            if lim and lim['w']==0 and not l.get('exempt_subject_limit'):
                for c in l['classes']:
                    if subjday.get((l['subject'],c,d),0)+1>lim['v']:rules.append(S[l['subject']]['name']+': ήδη '+str(subjday.get((l['subject'],c,d),0))+' φορά/ές '+p['days'][d]+' στο '+C[c]['name']+' (μέγιστο '+str(lim['v'])+')')
            if l.get('max_daily') and lessonday.get((l['id'],d),0)+dur>l['max_daily']:rules.append('Μέγιστες ώρες/ημέρα της ανάθεσης ('+str(l['max_daily'])+')')
            for t in l['teachers']:
                mx=R.rule(p,'teachers',t,'max_daily');used=tday.get((t,d),set())
                if mx and mx['w']==0 and len(used|set(cover))>mx['v']:rules.append(T[t]['name']+': ξεπερνά τις '+str(mx['v'])+' ώρες την ημέρα')
                for v,sid in dayend_subj.get((t,d),[]):
                    if i+dur-1>v:rules.append(T[t]['name']+': έχει '+S[sid]['name']+' εκείνη την ημέρα και πρέπει να τελειώσει έως '+p['periods'][v]['end'])
                if own_end and own_end['w']==0 and any(j>own_end['v'] for j in used):rules.append(T[t]['name']+': διδάσκει μετά τις '+p['periods'][own_end['v']]['end']+' εκείνη την ημέρα· με '+S[l['subject']]['name']+' πρέπει να τελειώνει νωρίτερα')
            if rules:st[k]='no';why[k]='; '.join(rules);continue
            soft=[nm for a,nm in av if any((d,j) in a for j in cover)]
            if soft:st[k]='maybe';why[k]='Υπό όρους (επιτρέπεται, αλλά καλύτερα να αποφεύγεται) για: '+', '.join(soft)
            else:st[k]='ok';why[k]='Ελεύθερη θέση'
    if e['place']:
        k=f"{e['place'][0]},{e['place'][1]}";st[k]='cur';why[k]='Τρέχουσα θέση'
    return {'st':st,'why':why}

GRADES=['Α','Β','Γ','Δ','Ε','ΣΤ']
def grade_of(c):
    """Τάξη τμήματος: ρητή ή από το όνομα (π.χ. «Α Τάξη», «Β1», «ΣΤ2»)."""
    if c.get('grade'):return c['grade']
    for txt in (c.get('short') or '',c['name']):
        t=txt.upper().replace('Τ΄','Τ').strip()
        for g in sorted(GRADES,key=len,reverse=True):
            if t==g or (t.startswith(g) and (len(t)==len(g) or t[len(g)] in ' 0123456789΄\'-')):return g
    return ''

def curriculum_check(p):
    """Αποκλίσεις ωρών ανά τμήμα από το επίσημο ωρολόγιο: {class_id: [κείμενα]}."""
    cur=p.get('curriculum') or {};S=mapping(p,'subjects');out={}
    for c in p['classes']:
        g=grade_of(c);want=cur.get(g)
        if not g or not want:continue
        have={}
        for l in p['lessons']:
            if c['id'] in l['classes']:have[l['subject']]=have.get(l['subject'],0)+l['hours']
        msgs=[]
        for sid,h in want.items():
            if have.get(sid,0)!=h:msgs.append(S[sid]['name']+': '+str(have.get(sid,0))+' αντί για '+str(h))
        for sid,h in have.items():
            if sid not in want and sid in S and h:msgs.append(S[sid]['name']+': '+str(h)+(' ώρα' if h==1 else ' ώρες')+', δεν υπάρχει στο επίσημο ωρολόγιο της '+g+'΄')
        if msgs:out[c['id']]=msgs
    return out

def findings(p,complete=False):return R.evaluate(p,complete)
def validation(p,complete=False):
    """Παραβιάσεις υποχρεωτικών κανόνων (κείμενα)."""
    check_structure(p);return [f['text'] for f in R.evaluate(p,complete) if f['hard']]
def warnings(p):
    """Επιθυμητοί κανόνες που δεν τηρούνται, με τη σειρά βαρύτητας."""
    check_structure(p);return sorted([f for f in R.evaluate(p,True) if not f['hard']],key=lambda f:-f['penalty'])

def save(p,path):
    check_structure(p);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        from datetime import datetime
        backup=path.parent/'backups';backup.mkdir(exist_ok=True)
        (backup/(path.stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')).write_bytes(path.read_bytes())
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(p,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def load(path):return check_structure(json.loads(Path(path).read_text(encoding='utf-8')))

def solve(p,seconds=30,cancel=None):
    check_structure(p)
    result=R.solve(p,seconds,cancel)
    if 'project' not in result:
        return result
    q=result['project'];errors=validation(q,True)
    if errors:raise ValueError('Η παραγόμενη λύση απέτυχε στον ανεξάρτητο έλεγχο: '+'; '.join(errors[:5]))
    soft=warnings(q);gaps=R.gap_total(q,False)
    result['message']='Έγκυρη λύση'+(' (βέλτιστη για τους κανόνες)' if result['status']=='optimal' else '')+'. Κενά εκπαιδευτικών: '+str(gaps)+'. '+('Όλοι οι επιθυμητοί κανόνες τηρούνται.' if not soft else 'Επιθυμητοί κανόνες που δεν τηρήθηκαν πλήρως: '+str(len(soft))+' (δείτε «Έλεγχος»).')
    result['score']=R.score(q)
    return result


def move_event(project, event_id, place, swap_id=None):
    p=copy.deepcopy(project)
    e=next(e for e in p['events'] if e['id']==event_id)
    if e['locked']:raise ValueError('Η διδασκαλία είναι κλειδωμένη.')
    if swap_id:
        other=next(x for x in p['events'] if x['id']==swap_id)
        if other is e or not e['place'] or not other['place']:raise ValueError('Μη έγκυρη ανταλλαγή.')
        if other['locked']:raise ValueError('Η δεύτερη διδασκαλία είναι κλειδωμένη.')
        e['place'],other['place']=other['place'],e['place']
    else:e['place']=place
    check_structure(p)
    # Απορρίπτεται μόνο ό,τι ΧΕΙΡΟΤΕΡΕΥΕΙ υποχρεωτικό κανόνα· υπάρχουσες εκκρεμότητες δεν μπλοκάρουν.
    before={f['key']:f['amount'] for f in R.evaluate(project) if f['hard']}
    worse=[f['text'] for f in R.evaluate(p) if f['hard'] and f['amount']>before.get(f['key'],0)]
    if worse:raise ValueError('Η μετακίνηση απορρίφθηκε: '+' · '.join(worse[:5]))
    return p
