import { useState } from "react";
import { apiRequest } from "../api";
import useApiData from "./useApiData";
import { Upload, PdfPreview } from "./PartACommon";
import CompanyDetails from "./CompanyDetails";
import JobInfo from "./JobInfo";
import "./CareerPages.css";

export default function JobDetailsPage({ jobId, user, onUnauthorized, onBack, onApplications, onProfile }) {
  const job = useApiData(`/jobs/${jobId}`, user, onUnauthorized);
  const resumes = useApiData("/applications/resume-options", user, onUnauthorized);
  const saved = useApiData('/students/me/saved-jobs', user, onUnauthorized);
  const applications = useApiData('/applications', user, onUnauthorized);
  const companies = useApiData('/companies', user, onUnauthorized);
  const [saving, setSaving] = useState(false);
  const [savedNow, setSavedNow] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [saveError, setSaveError] = useState('');
  const isSaved = savedNow || saved.data?.some(item => item.id === jobId);
  const [resumeId, setResumeId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);
  async function apply() {
    setError(""); setSubmitting(true);
    try {
      setSuccess(await apiRequest("/applications", {
        method: "POST", token: user.access_token, onUnauthorized,
        body: { job_id: jobId, resume_id: Number(resumeId) },
      }));
    } catch (err) { setError(err.message); }
    finally { setSubmitting(false); }
  }
  async function saveJob() {
    setSaving(true); setSaveMessage(''); setSaveError('');
    try {
      await apiRequest(`/students/me/saved-jobs/${jobId}`, { method: 'POST', token: user.access_token, onUnauthorized });
      setSavedNow(true); setSaveMessage('Job saved to your shortlist.');
    } catch (err) { setSaveError(err.message); }
    finally { setSaving(false); }
  }
  const application = success || applications.data?.find(item => item.job_id === jobId);
  return <section className="career-page career-detail">
    <button className="career-back" onClick={onBack}>← Back to Jobs</button>
    {job.loading ? <p role="status">Loading job...</p> : job.error ? <>
      <p role="alert">Could not load job. {job.error}</p><button onClick={job.retry}>Retry</button>
    </> : <>
      <header className="career-detail-hero"><span className="career-eyebrow">YOUR NEXT OPPORTUNITY</span>
        <p className="career-muted">{companies.data?.find(company => company.user_id === job.data.company_id)?.company_name || `Company #${job.data.company_id}`}</p>
        <h1>{job.data.title}</h1><p>{job.data.location} · {job.data.category.replaceAll('_', ' ')} · {job.data.is_remote ? 'Remote' : 'Onsite'}</p>
        <div className="career-card-actions"><a className="career-apply-link" href="#job-application">Apply for this role ↓</a><button className="career-secondary" disabled={saving || isSaved} onClick={saveJob}>{isSaved ? 'Job Saved' : saving ? 'Saving…' : 'Save Job'}</button></div>
        {saveMessage && <p role="status">{saveMessage}</p>}{saveError && <p role="alert">{saveError}</p>}
        {application && <p className="career-notice">Application status: <span className={`career-badge career-status-${application.status}`}>{application.status}</span></p>}
      </header>
      <div className="career-detail-grid"><div className="career-panel career-description">
      <h2>Description</h2><p className="job-description">{job.data.description}</p>
      <h2>Skills</h2><p>{job.data.skills_json?.length
        ? job.data.skills_json.map((skill) => typeof skill === "string" ? skill : JSON.stringify(skill)).join(", ")
        : "Not specified"}</p>
      </div><aside className="career-panel"><h2>At a glance</h2><JobInfo job={job.data} /></aside></div>
      <CompanyDetails companyId={job.data.company_id} user={user} onUnauthorized={onUnauthorized} />
      <section id="job-application" className="career-panel career-application-form" aria-labelledby="job-application-title">
      <span className="career-eyebrow">TAKE THE NEXT STEP</span><h2 id="job-application-title">Apply with your resume</h2><p>Upload a PDF or choose a resume already on file.</p>
      <Upload user={user} onUnauthorized={onUnauthorized} onUploaded={resume=>{setResumeId(String(resume.id));resumes.retry();}} />
      {resumeId && <PdfPreview key={resumeId} resumeId={resumeId} user={user} onUnauthorized={onUnauthorized} />}
      {success ? <p role="status">Application submitted successfully. Status: {success.status}</p> : <>
        {resumes.loading ? <p role="status">Loading resume choices...</p> : resumes.error ? <>
          <p role="alert">Could not load resume choices. {resumes.error}</p><button onClick={resumes.retry}>Retry Resumes</button>
        </> : !resumes.data.length ? <p role="status">A resume is required to apply. You have no resume on file. Upload a PDF resume using the form above.</p> :
          <div className="form-grid"><div><label htmlFor="application-resume">Resume</label>
            <select id="application-resume" value={resumeId} onChange={(event) => setResumeId(event.target.value)}>
              <option value="">Choose your resume</option>
              {resumes.data.map((resume) => <option value={resume.id} key={resume.id}>{resume.original_filename}</option>)}
            </select>
          </div></div>}
        <button disabled={!resumeId || submitting || resumes.loading || Boolean(resumes.error)} onClick={apply}>
          {submitting ? "Submitting..." : "Apply"}
        </button>
      </>}
      {error && <p role="alert">{error}</p>}
      {error.includes("student profile") && <button onClick={onProfile}>My Profile</button>}
      </section>
      <div className="page-actions"><button className="career-secondary" onClick={onApplications}>My Applications</button></div>
    </>}
  </section>;
}
