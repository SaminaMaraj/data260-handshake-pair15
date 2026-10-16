"""Part A workflows: profiles, directory, uploads, employers, events, preferences."""
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select, or_, cast, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_company, require_student
from app.database import get_db
from app.models.core import User, Student, Company, Job
from app.models.additional import Resume, Application, Event, EventRegistration, StudentPreference, SavedItem
from app.schemas import UserRead, StudentRead, JobRead, JobBase, ResumeOption, ApplicationRead, JobCategory
from app.routers.applications import application_query

router = APIRouter(tags=['Part A'])
UPLOADS = Path(__file__).resolve().parents[2] / 'uploads'
Status = Literal['pending', 'reviewed', 'declined']


class EmailUpdate(BaseModel):
    email: EmailStr


@router.put('/users/me', response_model=UserRead)
def update_email(data: EmailUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.scalar(select(User.id).where(User.email == data.email, User.id != user.id)):
        raise HTTPException(409, 'Email is already registered')
    user.email = data.email
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email is already registered')
    db.refresh(user)
    return user


@router.get('/directory/students', response_model=list[StudentRead])
def directory(q: str = '', major: str = '', skill: str = '', db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    stmt = select(Student)
    if q.strip():
        term = '%' + q.strip() + '%'
        stmt = stmt.where(or_(Student.full_name.ilike(term), Student.college_name.ilike(term),
                             cast(Student.skills_json, String).ilike(term)))
    if major.strip():
        stmt = stmt.where(Student.major.ilike('%'+major.strip()+'%'))
    if skill.strip():
        stmt = stmt.where(cast(Student.skills_json, String).ilike('%'+skill.strip()+'%'))
    return db.scalars(stmt.order_by(Student.full_name, Student.user_id)).all()


@router.get('/profiles/{user_id}/contact')
def contact(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, 'User not found')
    return {'email':target.email}


async def read_upload(file: UploadFile, limit: int):
    data = await file.read(limit+1)
    await file.close()
    if not data or len(data)>limit:
        raise HTTPException(413, f'File must be nonempty and no larger than {limit//1024//1024} MB')
    return data


@router.post('/resumes', response_model=ResumeOption, status_code=201)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_student)):
    if db.get(Student,user.id) is None:
        raise HTTPException(409,'Create your student profile before uploading a resume.')
    data = await read_upload(file, 5*1024*1024)
    if not (file.filename or '').lower().endswith('.pdf') or not data.startswith(b'%PDF-'):
        raise HTTPException(422,'Upload a valid PDF resume.')
    try:
        pdf = PdfReader(BytesIO(data))
        if pdf.is_encrypted or not len(pdf.pages):
            raise ValueError()
    except Exception:
        raise HTTPException(422,'PDF must be readable, unencrypted, and contain at least one page.')
    directory = UPLOADS/'resumes'
    directory.mkdir(parents=True,exist_ok=True)
    path = directory/(uuid4().hex+'.pdf')
    with path.open('xb') as out:
        out.write(data)
    resume = Resume(student_id=user.id,original_filename=Path(file.filename).name[:255],
                    stored_filename=path.name,file_path=str(path))
    db.add(resume)
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)  # Only the file just created by this failed upload.
        raise HTTPException(503,'Resume could not be saved. Please retry.')
    db.refresh(resume)
    return resume


@router.get('/resumes/{resume_id}/file', responses={200:{'content':{'application/pdf':{}}}})
def resume_file(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resume = db.get(Resume,resume_id)
    if resume is None:
        raise HTTPException(404,'Resume not found')
    permitted = user.role=='student' and resume.student_id==user.id
    if user.role=='company':
        permitted = db.scalar(select(Application.id).join(Job).where(
            Application.resume_id==resume_id, Job.company_id==user.id)) is not None
    if not permitted:
        raise HTTPException(403,'This resume is not available to your account')
    path = Path(resume.file_path)
    root = (UPLOADS/'resumes').resolve()
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root) or path.suffix!='.pdf':
        raise HTTPException(404,'No uploaded PDF is available for this fixture resume')
    return FileResponse(path,media_type='application/pdf',filename=resume.original_filename,
                        content_disposition_type='inline',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})


@router.post('/profiles/me/picture')
async def upload_picture(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.get(Student if user.role=='student' else Company,user.id)
    if profile is None:
        raise HTTPException(409,'Create your profile before uploading a picture')
    data=await read_upload(file,3*1024*1024)
    try:
        image=Image.open(BytesIO(data))
        if image.format not in ('PNG','JPEG') or image.width*image.height>16_000_000:
            raise ValueError()
        image.verify()
        image=Image.open(BytesIO(data)).convert('RGB')
        image.thumbnail((800,800))
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422,'Upload a valid PNG or JPEG image (at most 16 megapixels)')
    directory=UPLOADS/'pictures'
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(uuid4().hex+'.jpg')
    image.save(path,format='JPEG')
    profile.profile_picture_url='/media/profile/'+path.name
    try:
        db.commit()
    except Exception:
        db.rollback(); path.unlink(missing_ok=True)
        raise HTTPException(503,'Picture could not be saved')
    return {'profile_picture_url':profile.profile_picture_url}


@router.get('/media/profile/{filename}')
def picture(filename: str, user: User = Depends(get_current_user)):
    if not re.fullmatch(r'[a-f0-9]{32}\.jpg',filename):
        raise HTTPException(404,'Picture not found')
    path=UPLOADS/'pictures'/filename
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404,'Picture not found')
    return FileResponse(path,media_type='image/jpeg')


@router.get('/companies/me/jobs', response_model=list[JobRead])
def company_jobs(db: Session = Depends(get_db), user: User = Depends(require_company)):
    return db.scalars(select(Job).where(Job.company_id==user.id).order_by(Job.id.desc())).all()


@router.put('/jobs/{job_id}', response_model=JobRead)
def edit_job(job_id: int, data: JobBase, db: Session = Depends(get_db), user: User = Depends(require_company)):
    job=db.get(Job,job_id)
    if job is None: raise HTTPException(404,'Job not found')
    if job.company_id!=user.id: raise HTTPException(403,'You can only edit your own jobs')
    for key,value in data.model_dump().items(): setattr(job,key,value)
    db.commit();db.refresh(job)
    return job


@router.get('/companies/me/applications', response_model=list[ApplicationRead])
def applicants(job_id: int | None = None, status: Status | None = None,
               db: Session = Depends(get_db), user: User = Depends(require_company)):
    stmt=application_query().where(Job.company_id==user.id)
    if job_id is not None:
        job=db.get(Job,job_id)
        if job is None: raise HTTPException(404,'Job not found')
        if job.company_id!=user.id: raise HTTPException(403,'You can only review your own jobs')
        stmt=stmt.where(Application.job_id==job_id)
    if status: stmt=stmt.where(Application.status==status)
    return db.execute(stmt.order_by(Application.applied_at.desc(),Application.id.desc())).mappings().all()


class StatusUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    status: Status


@router.patch('/applications/{application_id}/status', response_model=ApplicationRead)
def review(application_id: int, data: StatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_company)):
    app=db.get(Application,application_id)
    if app is None: raise HTTPException(404,'Application not found')
    if db.get(Job,app.job_id).company_id!=user.id: raise HTTPException(403,'You can only review your own applicants')
    app.status=data.status
    app.reviewed_at=None if data.status=='pending' else datetime.utcnow()
    db.commit()
    return db.execute(application_query().where(Application.id==app.id)).mappings().one()


class EventInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    event_name: str=Field(min_length=1,max_length=255)
    description: str=Field(min_length=1,max_length=10000)
    event_date: date
    event_time: time
    location: str=Field(min_length=1,max_length=255)
    eligibility: str=Field(default='',max_length=2000)
    eligible_majors: list[str]=Field(default_factory=list,max_length=50)
    eligible_colleges: list[str]=Field(default_factory=list,max_length=50)

    @field_validator('event_time')
    @classmethod
    def local_time(cls,value):
        if value.tzinfo is not None: raise ValueError('Use local event time without a timezone offset')
        return value

    @field_validator('event_name','description','location')
    @classmethod
    def not_blank(cls,value):
        if not value.strip(): raise ValueError('Must not be blank')
        return value.strip()

    @field_validator('eligible_majors','eligible_colleges')
    @classmethod
    def clean_rules(cls,values):
        if any(not v.strip() or len(v)>255 for v in values): raise ValueError('Eligibility names must be 1–255 characters')
        return [v.strip() for v in values]


class EventRead(BaseModel):
    id: int
    company_id: int
    company_name: str
    event_name: str
    description: str
    event_date: date
    event_time: time
    location: str
    eligibility: str
    eligible_majors: list[str]
    eligible_colleges: list[str]
    eligible: bool
    ineligible_reason: str
    registered: bool


class RegistrationRead(BaseModel):
    student: StudentRead
    registered_at: datetime


def rules(event):
    try:
        data=json.loads(event.eligibility or '')
        if isinstance(data,dict) and data.get('version')==1: return data
    except (ValueError,TypeError): pass
    return {'description':event.eligibility or '', 'majors':[], 'colleges':[]}


def eligibility(event,student):
    if student is None: return False,'Create your student profile first.'
    r=rules(event)
    for key,actual in [('majors',student.major),('colleges',student.college_name)]:
        if r.get(key) and (actual or '').strip().casefold() not in [v.casefold() for v in r[key]]:
            return False,'Your profile does not match the event '+key+' requirement.'
    return True,''


def event_output(event,db,user):
    r=rules(event)
    eligible,reason=eligibility(event,db.get(Student,user.id)) if user.role=='student' else (False,'Only students can register.')
    upcoming=datetime.combine(event.event_date,event.event_time)>datetime.now()
    if not upcoming: eligible,reason=False,'Registration has closed.'
    registered=db.scalar(select(EventRegistration.id).where(EventRegistration.event_id==event.id,EventRegistration.student_id==user.id)) is not None
    company=db.get(Company,event.company_id)
    return {'id':event.id,'company_id':event.company_id,'company_name':company.company_name,
            'event_name':event.event_name,'description':event.description,'event_date':event.event_date,
            'event_time':event.event_time,'location':event.location,'eligibility':r['description'],
            'eligible_majors':r.get('majors',[]),'eligible_colleges':r.get('colleges',[]),
            'eligible':eligible,'ineligible_reason':reason,'registered':registered}


@router.get('/events', response_model=list[EventRead])
def events(q: str='', mine: bool=False, registered: bool=False, upcoming: bool=True,
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt=select(Event)
    if mine:
        if user.role!='company': raise HTTPException(403,'Company account required')
        stmt=stmt.where(Event.company_id==user.id)
    if registered:
        if user.role!='student': raise HTTPException(403,'Student account required')
        stmt=stmt.join(EventRegistration).where(EventRegistration.student_id==user.id)
    if q.strip(): stmt=stmt.where(Event.event_name.ilike('%'+q.strip()+'%'))
    if upcoming:
        now=datetime.now()
        stmt=stmt.where(or_(Event.event_date>now.date(),(Event.event_date==now.date()) & (Event.event_time>now.time())))
    return [event_output(e,db,user) for e in db.scalars(stmt.order_by(Event.event_date,Event.event_time,Event.id)).all()]


def save_event(event,data):
    for key,value in data.model_dump(exclude={'eligibility','eligible_majors','eligible_colleges'}).items(): setattr(event,key,value)
    event.eligibility=json.dumps({'version':1,'description':data.eligibility,'majors':data.eligible_majors,'colleges':data.eligible_colleges})


@router.post('/events', status_code=201, response_model=EventRead)
def create_event(data: EventInput, db: Session = Depends(get_db), user: User = Depends(require_company)):
    if db.get(Company,user.id) is None: raise HTTPException(409,'Create your company profile first')
    if datetime.combine(data.event_date,data.event_time)<=datetime.now(): raise HTTPException(422,'Event must be in the future')
    event=Event(company_id=user.id)
    save_event(event,data);db.add(event);db.commit();db.refresh(event)
    return event_output(event,db,user)


@router.get('/events/{event_id}', response_model=EventRead)
def event_detail(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event=db.get(Event,event_id)
    if event is None: raise HTTPException(404,'Event not found')
    return event_output(event,db,user)


@router.put('/events/{event_id}', response_model=EventRead)
def update_event(event_id: int, data: EventInput, db: Session = Depends(get_db), user: User = Depends(require_company)):
    event=db.get(Event,event_id)
    if event is None: raise HTTPException(404,'Event not found')
    if event.company_id!=user.id: raise HTTPException(403,'You can only edit your own events')
    if datetime.combine(data.event_date,data.event_time)<=datetime.now(): raise HTTPException(422,'Event must be in the future')
    save_event(event,data);db.commit();db.refresh(event)
    return event_output(event,db,user)


class RegisterEvent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm_eligibility: bool


@router.post('/events/{event_id}/registrations',status_code=201,response_model=EventRead)
def register_event(event_id: int, data: RegisterEvent, db: Session = Depends(get_db), user: User = Depends(require_student)):
    event=db.get(Event,event_id)
    if event is None: raise HTTPException(404,'Event not found')
    output=event_output(event,db,user)
    if output['registered']: raise HTTPException(409,'You are already registered for this event')
    if not output['eligible']: raise HTTPException(403,output['ineligible_reason'])
    if not data.confirm_eligibility: raise HTTPException(422,'Confirm that you meet the stated eligibility requirements')
    registration=EventRegistration(event_id=event_id,student_id=user.id)
    db.add(registration)
    try: db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'You are already registered for this event')
    return event_output(event,db,user)


@router.get('/events/{event_id}/registrations',response_model=list[RegistrationRead])
def attendees(event_id: int, db: Session = Depends(get_db), user: User = Depends(require_company)):
    event=db.get(Event,event_id)
    if event is None: raise HTTPException(404,'Event not found')
    if event.company_id!=user.id: raise HTTPException(403,'You can only view registrations for your own events')
    rows=db.execute(select(Student,EventRegistration.registered_at).join(EventRegistration,Student.user_id==EventRegistration.student_id)
                    .where(EventRegistration.event_id==event_id).order_by(Student.full_name)).all()
    return [{'student':StudentRead.model_validate(s).model_dump(),'registered_at':stamp} for s,stamp in rows]


class PreferenceInput(BaseModel):
    model_config=ConfigDict(extra='forbid',from_attributes=True)
    preferred_city: str | None=Field(default=None,max_length=100)
    preferred_category: JobCategory | None=None
    minimum_salary: Decimal | None=Field(default=None,ge=0,max_digits=12,decimal_places=2)
    preferred_skills_json: list[str] | None=None
    remote_only: bool=False


@router.get('/students/me/preferences',response_model=PreferenceInput)
def preferences(db: Session = Depends(get_db),user: User = Depends(require_student)):
    return db.get(StudentPreference,user.id) or PreferenceInput()


@router.put('/students/me/preferences',response_model=PreferenceInput)
def update_preferences(data: PreferenceInput,db: Session = Depends(get_db),user: User = Depends(require_student)):
    if db.get(Student,user.id) is None: raise HTTPException(409,'Create your student profile first')
    row=db.get(StudentPreference,user.id)
    if row is None: row=StudentPreference(student_id=user.id);db.add(row)
    for key,value in data.model_dump().items(): setattr(row,key,value)
    db.commit();db.refresh(row)
    return row


@router.get('/students/me/saved-jobs',response_model=list[JobRead])
def saved_jobs(db: Session = Depends(get_db),user: User = Depends(require_student)):
    return db.scalars(select(Job).join(SavedItem,SavedItem.job_id==Job.id).where(SavedItem.student_id==user.id).distinct()).all()


@router.post('/students/me/saved-jobs/{job_id}',status_code=201)
def save_job(job_id: int,db: Session = Depends(get_db),user: User = Depends(require_student)):
    if db.get(Student,user.id) is None: raise HTTPException(409,'Create your student profile first')
    if db.get(Job,job_id) is None: raise HTTPException(404,'Job not found')
    row=db.scalar(select(SavedItem).where(SavedItem.student_id==user.id,SavedItem.job_id==job_id))
    if row is None:
        db.add(SavedItem(student_id=user.id,job_id=job_id));db.commit()
    return {'saved':True,'job_id':job_id}
