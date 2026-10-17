import { CompanyHeading } from "./CompanyUI";
import { StudentEventDiscovery, StudentEventDetail } from "./StudentEventsUI";
import { useState } from "react";
import useApiData from "./useApiData";
import { apiRequest } from "../api";
import { StudentDetails } from "./DirectoryPage";

function EventForm({ event, user, onUnauthorized, onSaved, onCancel }) {
  const [form,setForm]=useState(event ? {...event,eligible_majors:event.eligible_majors.join(', '),eligible_colleges:event.eligible_colleges.join(', ')} : {
    event_name:'',description:'',event_date:'',event_time:'',location:'Sunnyvale',eligibility:'',eligible_majors:'',eligible_colleges:''});
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function save(e){
    e.preventDefault();setBusy(true);setError('');
    const {event_name,description,event_date,event_time,location,eligibility}=form;
    const body={event_name,description,event_date,event_time,location,eligibility,
      eligible_majors:form.eligible_majors.split(',').map(s=>s.trim()).filter(Boolean),
      eligible_colleges:form.eligible_colleges.split(',').map(s=>s.trim()).filter(Boolean)};
    try{await apiRequest(event?`/events/${event.id}`:'/events',{method:event?'PUT':'POST',body,token:user.access_token,onUnauthorized});onSaved();}
    catch(err){setError(err.message);}finally{setBusy(false);}
  }
  return <form className="company-panel company-form" onSubmit={save}><h2>{event?'Edit Event':'Create Event'}</h2><fieldset disabled={busy}>
    <div className="form-grid">{[['event_name','Event name','text'],['description','Description','text'],['event_date','Event date','date'],
      ['event_time','Event time (local)','time'],['location','Location','text'],['eligibility','Written eligibility requirements','text'],
      ['eligible_majors','Eligible majors (comma separated; blank means all)','text'],['eligible_colleges','Eligible colleges (comma separated; blank means all)','text']]
      .map(([key,label,type])=><label key={key}>{label}<input type={type} required={['event_name','description','event_date','event_time','location'].includes(key)}
        value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})} /></label>)}</div>
    <button type="submit">{busy?'Saving...':'Save Event'}</button><button type="button" onClick={onCancel}>Cancel</button>
  </fieldset>{error&&<p role="alert">{error}</p>}</form>;
}

function EventDetails({ id,user,onUnauthorized,onBack,onEdit }) {
  const result=useApiData(`/events/${id}`,user,onUnauthorized);
  const [confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[showAttendees,setShowAttendees]=useState(false);
  async function register(){
    setBusy(true);setError('');
    try{await apiRequest(`/events/${id}/registrations`,{method:'POST',body:{confirm_eligibility:confirmed},token:user.access_token,onUnauthorized});result.retry();}
    catch(err){setError(err.message);}finally{setBusy(false);}
  }
  if(result.loading) return <p role="status">Loading event...</p>;
  if(result.error) return <><button onClick={onBack}>Back to Events</button><p role="alert">{result.error}</p></>;
  const e=result.data;
  if (user.role === 'student') return <StudentEventDetail event={e} confirmed={confirmed}
    setConfirmed={setConfirmed} busy={busy} error={error} register={register} onBack={onBack} />;
  return <div className="company-panel company-event-detail"><button className="company-back" onClick={onBack}>← Back to Events</button><span className="company-eyebrow">EVENT DETAILS</span><h1>{e.event_name}</h1>
    <p>{e.company_name}</p><p>{e.description}</p><p>{e.event_date} at {e.event_time} · {e.location}</p>
    <h2>Eligibility</h2><p>{e.eligibility||'All students'}</p>
    {e.eligible_majors.length>0&&<p>Majors: {e.eligible_majors.join(', ')}</p>}
    {e.eligible_colleges.length>0&&<p>Colleges: {e.eligible_colleges.join(', ')}</p>}
    {user.role==='student' ? e.registered ? <p role="status">You are registered for this event.</p> : <>
      {!e.eligible&&<p role="status">{e.ineligible_reason}</p>}
      <label><input type="checkbox" checked={confirmed} onChange={ev=>setConfirmed(ev.target.checked)} /> I meet the written eligibility requirements.</label>
      <button disabled={!e.eligible||!confirmed||busy} onClick={register}>{busy?'Registering...':'Register for Event'}</button>
    </> : e.company_id===user.id && <><button onClick={()=>onEdit(e)}>Edit Event</button><button onClick={()=>setShowAttendees(!showAttendees)}>View Registered Students</button></>}
    {error&&<p role="alert">{error}</p>}
    {showAttendees&&<Attendees id={id} user={user} onUnauthorized={onUnauthorized} />}
  </div>;
}

function Attendees({id,user,onUnauthorized}){
  const result=useApiData(`/events/${id}/registrations`,user,onUnauthorized);
  const [student,setStudent]=useState(null);
  if(student) return <StudentDetails studentId={student} user={user} onUnauthorized={onUnauthorized} onBack={()=>setStudent(null)} />;
  return <section><h2>Registered Students</h2>{result.loading?<p role="status">Loading registrations...</p>:result.error?<p role="alert">{result.error}</p>:<>
    <p>{result.data.length} registrations</p>{result.data.map(r=><article key={r.student.user_id} className="job-result"><h3>{r.student.full_name}</h3>
      <p>{r.student.college_name} · {r.student.major}</p><button onClick={()=>setStudent(r.student.user_id)}>View Student Profile</button></article>)}
  </>}</section>;
}

export default function EventsPage({user,onUnauthorized,onBack,initialEventId=null}){
  const [q,setQ]=useState(''),[mode,setMode]=useState('all'),[selected,setSelected]=useState(initialEventId),[editing,setEditing]=useState(null);
  const query=new URLSearchParams({q,upcoming:mode==='all'?'true':'false'});if(mode==='mine')query.set('mine','true');if(mode==='registered')query.set('registered','true');
  const result=useApiData(`/events?${query}`,user,onUnauthorized);
  if (user.role === 'student') return selected
    ? <EventDetails key={selected} id={selected} user={user} onUnauthorized={onUnauthorized}
        onEdit={setEditing} onBack={() => { setSelected(null); result.retry(); }} />
    : <StudentEventDiscovery q={q} setQ={setQ} mode={mode} setMode={setMode} result={result}
        onBack={onBack} onSelect={setSelected} />;
  return <section className="company-portal company-events">
    {editing ? <EventForm key={editing.id||'new'} event={editing.id?editing:null} user={user} onUnauthorized={onUnauthorized}
      onCancel={()=>setEditing(null)} onSaved={()=>{setEditing(null);setSelected(null);setMode('mine');result.retry();}} />
      : selected ? <EventDetails key={selected} id={selected} user={user} onUnauthorized={onUnauthorized} onEdit={setEditing} onBack={()=>{setSelected(null);result.retry();}} />
      : <><CompanyHeading title="Events" description="Bring students and your company together. Plan and manage your events." onBack={onBack}><button onClick={()=>setEditing({})}>+ Create Event</button></CompanyHeading><div className="company-panel company-filters">
        <label>Search event name<input value={q} onChange={e=>setQ(e.target.value)} /></label>
        <label>Event list<select value={mode} onChange={e=>setMode(e.target.value)}><option value="all">Upcoming events</option>
          {user.role==='company'?<option value="mine">My events</option>:<option value="registered">My registered events</option>}</select></label>
        </div>{result.loading?<p role="status">Loading events...</p>:result.error?<div className="company-state"><p role="alert">{result.error}</p><button onClick={result.retry}>Retry events</button></div>:<>
          <p role="status">{result.data.length ? `${result.data.length} events found, ordered by date and time.` : "No events match this view. Create an event or try another search."}</p>
          {result.data.map(e=><article className="company-panel company-event" key={e.id}><div className="company-event-date"><span>EVENT DATE</span><time dateTime={e.event_date}>{e.event_date}</time></div><div><h2>{e.event_name}</h2><p>{e.event_time} · {e.location}</p>
            <p>{e.company_name}{e.registered?' · Registered':''}</p><button onClick={()=>setSelected(e.id)}>View Event Details</button></div></article>)}
        </>}
      </>}
  </section>;
}
