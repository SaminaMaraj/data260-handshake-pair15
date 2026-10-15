import { useState } from "react";
import { apiRequest } from "../api";
import useApiData from "./useApiData";
import JobInfo from "./JobInfo";

export default function JobDetailsPage({ jobId, user, onUnauthorized, onBack, onApplications, onProfile }) {
  const job = useApiData(`/jobs/${jobId}`, user, onUnauthorized);
  const resumes = useApiData("/applications/resume-options", user, onUnauthorized);
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
  return <section className="feature-page">
    <button onClick={onBack}>Back to Jobs</button>
    {job.loading ? <p role="status">Loading job...</p> : job.error ? <>
      <p role="alert">Could not load job. {job.error}</p><button onClick={job.retry}>Retry</button>
    </> : <>
      <h1>{job.data.title}</h1><JobInfo job={job.data} />
      <h2>Description</h2><p className="job-description">{job.data.description}</p>
      <h2>Skills</h2><p>{job.data.skills_json?.length
        ? job.data.skills_json.map((skill) => typeof skill === "string" ? skill : JSON.stringify(skill)).join(", ")
        : "Not specified"}</p>
      {success ? <p role="status">Application submitted successfully. Status: {success.status}</p> : <>
        {resumes.loading ? <p role="status">Loading resume choices...</p> : resumes.error ? <>
          <p role="alert">Could not load resume choices. {resumes.error}</p><button onClick={resumes.retry}>Retry Resumes</button>
        </> : !resumes.data.length ? <p role="status">A resume is required to apply. You have no resume on file. Resume upload will be available in Run 3.</p> :
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
      <div className="page-actions"><button onClick={onApplications}>My Applications</button></div>
    </>}
  </section>;
}
