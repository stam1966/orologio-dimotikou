"""Εξαγωγή σε μορφή «aSc Timetables 2012 XML» (Αρχείο → Εισαγωγή → aSc XML στο aSc).
Γράφεται σε windows-1253, όπως τα αρχεία του aSc. Τα αναγνωριστικά που ήρθαν από το aSc
διατηρούνται. Οι κανόνες και οι διαθεσιμότητες δεν μεταφέρονται (δεν υπάρχουν στη μορφή)."""
import xml.etree.ElementTree as ET

DAYCODE = lambda days: ','.join(''.join('1' if k == d else '0' for k in range(5)) for d in days)


def export_asc(p):
    root = ET.Element('timetable', dict(ascttversion='2023.12.1', importtype='database',
                                        options='export:idprefix:%CHRID,import:idprefix:%TEMPID,groupstype1,decimalseparatordot,lessonsincludeclasseswithoutstudents,handlestudentsafterlessons',
                                        defaultexport='1', displayname='aSc Timetables 2012 XML', displaycountries=''))

    def section(tag, columns):
        return ET.SubElement(root, tag, dict(options='canadd,export:silent', columns=columns))

    per = section('periods', 'period,name,short,starttime,endtime')
    for x in p['periods']:
        ET.SubElement(per, 'period', dict(name=x['name'], short=x['name'], period=str(x['id']), starttime=x['start'], endtime=x['end']))

    dd = section('daysdefs', 'id,days,name,short')
    defs = {}

    def daysdef(days):
        days = tuple(sorted(days))
        if days not in defs:
            if days == (0, 1, 2, 3, 4):
                did, name, sh = 'DANY', 'Οποιαδήποτε ημέρα', 'X'
            elif len(days) == 1:
                did, name, sh = 'D' + str(days[0]), p['days'][days[0]], p['days'][days[0]][:3]
            else:
                did, name, sh = 'D' + ''.join(map(str, days)), ', '.join(p['days'][d][:3] for d in days), ''.join(p['days'][d][:2] for d in days)
            defs[days] = did
            ET.SubElement(dd, 'daysdef', dict(id=did, name=name, short=sh, days=DAYCODE(days)))
        return defs[days]
    daysdef((0, 1, 2, 3, 4))
    ET.SubElement(dd, 'daysdef', dict(id='DEVERY', name='Κάθε ημέρα', short='E', days='11111'))
    for d in range(5):
        daysdef((d,))

    wd = section('weeksdefs', 'id,weeks,name,short'); ET.SubElement(wd, 'weeksdef', dict(id='WALL', name='Όλες οι εβδομάδες', short='Όλ', weeks='1'))
    td = section('termsdefs', 'id,terms,name,short'); ET.SubElement(td, 'termsdef', dict(id='TALL', name='Όλο το έτος', short='Έτος', terms='1'))

    sub = section('subjects', 'id,name,short,partner_id')
    for s in p['subjects']:
        ET.SubElement(sub, 'subject', dict(id=s['id'], name=s['name'], short=s.get('short') or s['name'], partner_id=''))

    te = section('teachers', 'id,name,short,gender,color,email,mobile,partner_id,firstname,lastname')
    for t in p['teachers']:
        parts = t['name'].split(' ', 1)
        ET.SubElement(te, 'teacher', dict(id=t['id'], firstname=t.get('firstname', parts[1] if len(parts) > 1 else ''), lastname=t.get('lastname', parts[0]),
                                          name=t['name'], short=t.get('short') or t['name'], gender=t.get('gender', ''), color=t.get('color', ''),
                                          email='', mobile='', partner_id=''))
    section('buildings', 'id,name,partner_id')
    rooms = section('classrooms', 'id,name,short,capacity,buildingid,partner_id')
    for r in p['rooms']:
        ET.SubElement(rooms, 'classroom', dict(id=r['id'], name=r['name'], short=r.get('short') or r['name'], capacity='*', buildingid='', partner_id=''))
    section('grades', 'grade,name,short')
    cl = section('classes', 'id,name,short,classroomids,teacherid,grade,partner_id')
    for c in p['classes']:
        ET.SubElement(cl, 'class', dict(id=c['id'], name=c['name'], short=c.get('short') or c['name'], teacherid=c.get('teacher', ''), classroomids='', grade='', partner_id=''))

    gr = section('groups', 'id,classid,name,entireclass,divisiontag,studentcount,studentids')
    groups = list(p['groups'])
    have_whole = {g['classid'] for g in groups if g.get('entireclass') == '1'}
    for c in p['classes']:  # το aSc περιμένει ομάδα «Όλο το τμήμα» για κάθε τμήμα
        if c['id'] not in have_whole:
            groups.append(dict(id='G' + c['id'], name='Όλο το τμήμα', classid=c['id'], studentids='', entireclass='1', divisiontag='0', studentcount=''))
    whole = {g['classid']: g['id'] for g in groups if g.get('entireclass') == '1'}
    for g in groups:
        ET.SubElement(gr, 'group', {k: str(g.get(k, '')) for k in ('id', 'name', 'classid', 'studentids', 'entireclass', 'divisiontag', 'studentcount')})
    section('students', 'id,classid,name,number,email,mobile,partner_id,firstname,lastname')
    section('studentsubjects', 'studentid,subjectid,seminargroup,importance,alternatefor')

    le = section('lessons', 'id,subjectid,classids,groupids,teacherids,classroomids,periodspercard,periodsperweek,daysdefid,weeksdefid,termsdefid,seminargroup,capacity,partner_id')
    ca = section('cards', 'lessonid,period,days,weeks,terms,classroomids')
    for l in p['lessons']:
        gids = l['groups'] or [whole[c] for c in l['classes'] if c in whole]
        ET.SubElement(le, 'lesson', dict(id=l['id'], classids=','.join(l['classes']), subjectid=l['subject'], periodspercard=str(l['duration']),
                                         periodsperweek=f"{float(l['hours']):.1f}", teacherids=','.join(l['teachers']), classroomids=l.get('room', ''),
                                         groupids=','.join(gids), capacity='*', seminargroup='', termsdefid='TALL', weeksdefid='WALL',
                                         daysdefid=daysdef(l['days']), partner_id=''))
    for e in p['events']:
        if not e['place']:
            continue
        l = next(x for x in p['lessons'] if x['id'] == e['lesson'])
        d, i = e['place']
        for j in range(i, i + l['duration']):  # το aSc γράφει μία κάρτα ανά διδακτική ώρα
            ET.SubElement(ca, 'card', dict(lessonid=l['id'], classroomids=l.get('room', ''), period=str(p['periods'][j]['id']), weeks='1', terms='1',
                                           days=''.join('1' if k == d else '0' for k in range(5))))
    ET.indent(root, space='   ')
    body = ET.tostring(root, encoding='unicode').encode('windows-1253', 'xmlcharrefreplace')
    return b'<?xml version="1.0" encoding="windows-1253"?>\r\n' + body.replace(b'\n', b'\r\n')
