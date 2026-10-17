import { CompanyHeading, JobStatus } from "./CompanyUI";
import useApiData from "./useApiData";
import JobInfo from "./JobInfo";
import { companyJobs } from "./jobFilters";

export default function CompanyJobsPage({ user, onUnauthorized, onBack, onPost, onEdit, onApplicants }) {
  const { data, loading, error, retry } = useApiData("/companies/me/jobs", user, onUnauthorized);
  const jobs = data ? companyJobs(data, user.id) : [];
  return <section className="company-portal">
    <CompanyHeading title="My Job Posts" description="Manage your opportunities and connect with applicants." onBack={onBack}><button onClick={onPost}>+ Post Job</button></CompanyHeading>
    {loading ? <p role="status">Loading job posts...</p> : error ? <>
      <p role="alert">Could not load job posts. {error}</p><button onClick={retry}>Retry</button>
    </> : <>
      <p role="status">{jobs.length ? `${jobs.length} job posts found.` : "You have not posted any jobs yet."}</p>

      {jobs.map((job) => <article className="company-panel company-job" key={job.id}>
        <div className="company-section-heading"><div><JobStatus job={job} /><h2>{job.title}</h2></div><div className="company-actions"><button className="company-secondary" onClick={()=>onEdit(job)}>Edit Job</button><button onClick={()=>onApplicants(job.id)}>View Applicants</button></div></div><JobInfo job={job} />
        <p className="job-description">{job.description}</p>
      </article>)}
    </>}
  </section>;
}
