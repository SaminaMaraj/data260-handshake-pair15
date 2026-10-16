import { useState } from "react";
import useApiData from "./useApiData";
import { apiRequest } from "../api";
import { StudentDetails } from "./DirectoryPage";
import { PdfPreview } from "./PartACommon";

export default function ApplicantsPage({ user, onUnauthorized, onBack, initialJobId = "" }) {
  const [jobId,setJobId]=useState(String(initialJobId)), [status,setStatus]=useState(""), [student,setStudent]=useState(null);
  const [resume,setResume]=useState(null), [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const jobs=useApiData('/companies/me/jobs',user,onUnauthorized);
  const query=new URLSearchParams(); if(jobId) query.set('job_id',jobId); if(status) query.set('status',status);
  const applications=useApiData(`/companies/me/applications?${query}`,user,onUnauthorized);
  async function change(id,value) {
    setBusy(true);setError("");
    try { await apiRequest(`/applications/${id}/status`,{method:'PATCH',token:user.access_token,onUnauthorized,body:{status:value}}); applications.retry(); }
    catch(err){setError(err.message);} finally{setBusy(false);}
  }
  if(student) return <StudentDetails studentId={student} user={user} onUnauthorized={onUnauthorized} onBack={()=>setStudent(null)} />;
  return <section className="feature-page">
    <button onClick={onBack}>Back to Dashboard</button><h1>Applicants</h1>
    <label>Job<select value={jobId} onChange={e=>setJobId(e.target.value)}><option value="">All my jobs</option>
      {jobs.data?.map(j=><option value={j.id} key={j.id}>{j.title}</option>)}</select></label>
    <label>Application status<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>
      {['pending','reviewed','declined'].map(s=><option key={s} value={s}>{s}</option>)}</select></label>
    {error && <p role="alert">{error}</p>}{jobs.error && <p role="alert">{jobs.error}</p>}
    {applications.loading ? <p role="status">Loading applicants...</p> : applications.error ? <p role="alert">{applications.error}</p> : <>
      <p role="status">{applications.data.length} applications found.</p>
      {applications.data.map(app=><article key={app.id} className="job-result">
        <h2>{app.job_title}</h2><p>{app.student_name} (#{app.student_id}) · Applied {app.applied_at} · Status: {app.status}</p>
        <button onClick={()=>setStudent(app.student_id)}>View Student Profile</button>
        <button onClick={()=>setResume(resume===app.resume_id ? null : app.resume_id)}>Preview Resume</button>
        <label>Update status for application {app.id}<select disabled={busy} value={app.status} onChange={e=>change(app.id,e.target.value)}>
          {['pending','reviewed','declined'].map(s=><option key={s} value={s}>{s}</option>)}</select></label>
        {resume===app.resume_id && <PdfPreview key={resume} resumeId={resume} user={user} onUnauthorized={onUnauthorized} />}
      </article>)}
    </>}
  </section>;
}
