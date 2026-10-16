"""Live Part A integration tests. Unique fixtures retained; never resets/deletes data."""
from datetime import date, timedelta
from io import BytesIO
import secrets
import uuid
import httpx
from PIL import Image
from pypdf import PdfWriter

BASE='http://127.0.0.1:9150'
client=httpx.Client(base_url=BASE,timeout=20)
checks=0

def req(method,path,expected=200,token=None,body=None,files=None):
    global checks
    r=client.request(method,path,headers={'Authorization':'Bearer '+token} if token else {},
                     json=body,files=files)
    assert r.status_code==expected,f'{method} {path}: expected {expected}, got {r.status_code}: {r.text[:300]}'
    checks+=1
    return r.json() if 'application/json' in r.headers.get('content-type','') else r.content

def account(role):
    data={'email':f'parta-{uuid.uuid4().hex}@example.com','password':secrets.token_urlsafe(20)}
    user=req('POST','/users/register',201,body={**data,'role':role})
    token=req('POST','/users/login',body=data)['access_token']
    return user['id'],token

def main():
    sid,st=account('student'); other,ot=account('student'); cid,ct=account('company'); cid2,ct2=account('company')
    name='PartA-'+uuid.uuid4().hex[:10]
    profile={'user_id':sid,'full_name':name,'college_name':'SJSU','major':'Data Science','skills_json':['SQL','Python'],
             'city':'Sunnyvale','education':'BS coursework, data systems','phone':'555-0100'}
    req('POST','/students',201,st,profile)
    req('POST','/students',201,ot,{'user_id':other,'full_name':'Other Test Student','major':'History'})
    req('POST','/companies',201,ct,{'user_id':cid,'company_name':name+' Company','location':'Cupertino','contact_phone':'555-0101'})
    req('POST','/companies',201,ct2,{'user_id':cid2,'company_name':'Other Company'})
    assert req('GET',f'/students/{sid}',token=st)['education']==profile['education']
    for role_token in (st,ct):
        results=req('GET','/directory/students?q='+name,token=role_token);assert [s['user_id'] for s in results]==[sid]
        assert any(s['user_id']==sid for s in req('GET','/directory/students?major=Data%20Science&skill=SQL',token=role_token))
    req('GET','/directory/students',401)
    updated_email=f'parta-updated-{uuid.uuid4().hex}@example.com'
    assert req('PUT','/users/me',token=st,body={'email':updated_email})['email']==updated_email
    assert req('GET',f'/profiles/{sid}/contact',token=ct)['email']==updated_email
    req('PUT','/users/me',422,st,{'email':'not-an-email'})
    pref={'preferred_city':'Palo Alto','preferred_category':'internship','minimum_salary':'3000.00','preferred_skills_json':['SQL'],'remote_only':True}
    assert req('PUT','/students/me/preferences',token=st,body=pref)==pref
    assert req('GET','/students/me/preferences',token=st)==pref
    req('PUT','/students/me/preferences',403,ct,pref)
    req('PUT','/students/me/preferences',422,st,{**pref,'minimum_salary':-1})
    req('POST','/users/register',422,body={'email':'invalidpass@example.com','password':'short','role':'student'})
    job={'title':name+' Analyst','posting_date':date.today().isoformat(),'deadline':(date.today()+timedelta(days=30)).isoformat(),
         'location':'Palo Alto','description':'Part A integration fixture','category':'internship','salary':'4000.00','company_id':cid}
    j=req('POST','/jobs',201,ct,job);jid=j['id']
    assert [x['id'] for x in req('GET','/jobs/search?q='+name+'%20Company',token=st)]==[jid]
    assert [x['id'] for x in req('GET','/companies/me/jobs',token=ct)]==[jid]
    assert req('GET','/companies/me/jobs',token=ct2)==[]
    req('GET','/companies/me/jobs',403,st)
    edit={k:v for k,v in job.items() if k!='company_id'};edit['title']=name+' Updated Analyst'
    req('PUT',f'/jobs/{jid}',403,ct2,edit)
    assert req('PUT',f'/jobs/{jid}',token=ct,body=edit)['title']==edit['title']
    req('POST',f'/students/me/saved-jobs/{jid}',201,st)
    req('POST',f'/students/me/saved-jobs/{jid}',201,st)
    assert len(req('GET','/students/me/saved-jobs',token=st))==1
    pdf=BytesIO();writer=PdfWriter();writer.add_blank_page(width=612,height=792);writer.write(pdf)
    content=pdf.getvalue()
    req('POST','/resumes',403,ct,files={'file':('test.pdf',content,'application/pdf')})
    req('POST','/resumes',422,st,files={'file':('test.pdf',b'fake','application/pdf')})
    req('POST','/resumes',413,st,files={'file':('huge.pdf',b'x'*(5*1024*1024+1),'application/pdf')})
    resume=req('POST','/resumes',201,st,files={'file':('resume.pdf',content,'application/pdf')})
    rid=resume['id']
    assert req('GET',f'/resumes/{rid}/file',token=st)==content
    req('GET',f'/resumes/{rid}/file',403,ct)
    image=BytesIO();Image.new('RGB',(10,10),'blue').save(image,format='PNG')
    photo=req('POST','/profiles/me/picture',token=st,files={'file':('photo.png',image.getvalue(),'image/png')})
    assert req('GET',photo['profile_picture_url'],token=ct).startswith(b'\xff\xd8')
    req('POST','/profiles/me/picture',422,st,files={'file':('x.png',b'fake','image/png')})
    app=req('POST','/applications',201,st,{'job_id':jid,'resume_id':rid});aid=app['id']
    req('POST','/applications',409,st,{'job_id':jid,'resume_id':rid})
    assert req('GET',f'/resumes/{rid}/file',token=ct)==content
    req('GET',f'/resumes/{rid}/file',403,ct2);req('GET',f'/resumes/{rid}/file',403,ot)
    assert len(req('GET',f'/companies/me/applications?job_id={jid}',token=ct))==1
    req('GET',f'/companies/me/applications?job_id={jid}',403,ct2)
    req('PATCH',f'/applications/{aid}/status',403,st,{'status':'reviewed'})
    req('PATCH',f'/applications/{aid}/status',403,ct2,{'status':'reviewed'})
    req('PATCH',f'/applications/{aid}/status',422,ct,{'status':'accepted'})
    for status in ('reviewed','declined','pending'):
        result=req('PATCH',f'/applications/{aid}/status',token=ct,body={'status':status})
        assert (result['reviewed_at'] is None)==(status=='pending')
        assert req('GET','/applications?status='+status,token=st)[0]['status']==status
    event={'event_name':name+' Career Day','description':'Synthetic event fixture','event_date':(date.today()+timedelta(days=10)).isoformat(),
           'event_time':'12:00','location':'Cupertino','eligibility':'Data Science students at SJSU','eligible_majors':['Data Science'],'eligible_colleges':['SJSU']}
    req('POST','/events',403,st,event)
    req('POST','/events',422,ct,{**event,'event_date':'2020-01-01'})
    e=req('POST','/events',201,ct,event);eid=e['id']
    req('PUT',f'/events/{eid}',403,ct2,event)
    req('PUT',f'/events/{eid}',token=ct,body={**event,'location':'Palo Alto'})
    result=req('GET','/events?q='+name,token=st);assert result[0]['id']==eid and result[0]['eligible']
    all_events=req('GET','/events',token=st)
    keys=[(e['event_date'],e['event_time'],e['id']) for e in all_events];assert keys==sorted(keys)
    req('POST',f'/events/{eid}/registrations',403,ot,{'confirm_eligibility':True})
    req('POST',f'/events/{eid}/registrations',403,ct,{'confirm_eligibility':True})
    req('POST',f'/events/{eid}/registrations',422,st,{'confirm_eligibility':False})
    assert req('POST',f'/events/{eid}/registrations',201,st,{'confirm_eligibility':True})['registered']
    req('POST',f'/events/{eid}/registrations',409,st,{'confirm_eligibility':True})
    assert req('GET','/events?registered=true&upcoming=false',token=st)[0]['id']==eid
    assert req('GET',f'/events/{eid}/registrations',token=ct)[0]['student']['user_id']==sid
    req('GET',f'/events/{eid}/registrations',403,ct2)
    req('GET',f'/events/{eid}/registrations',403,st)
    schema=req('GET','/openapi.json')
    for path in ['/resumes','/events','/events/{event_id}/registrations','/companies/me/applications','/students/me/preferences']:
        assert path in schema['paths']
    print(f'PASS Part A: {checks} live requests; uploads, access restrictions, search, profiles, preferences, jobs, applicants, statuses, events, registrations and OpenAPI. Test data retained.')

if __name__=='__main__':main()
