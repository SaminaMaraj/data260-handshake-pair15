import useApiData from "./useApiData";
import JobInfo from "./JobInfo";
import { companyJobs } from "./jobFilters";

export default function CompanyJobsPage({ user, onUnauthorized, onBack, onPost, onEdit, onApplicants }) {
  const { data, loading, error, retry } = useApiData("/companies/me/jobs", user, onUnauthorized);
  const jobs = data ? companyJobs(data, user.id) : [];
  return <section className="feature-page">
    <button onClick={onBack}>Back to Dashboard</button>
    <h1>My Job Posts</h1>
    <button onClick={onPost}>Post Job</button>
    {loading ? <p role="status">Loading job posts...</p> : error ? <>
      <p role="alert">Could not load job posts. {error}</p><button onClick={retry}>Retry</button>
    </> : <>
      <p role="status">{jobs.length ? `${jobs.length} job posts found.` : "You have not posted any jobs yet."}</p>

      {jobs.map((job) => <article className="job-result" key={job.id}>
        <h2>{job.title}</h2><button onClick={()=>onEdit(job)}>Edit Job</button><button onClick={()=>onApplicants(job.id)}>View Applicants</button><JobInfo job={job} />
        <p className="job-description">{job.description}</p>
      </article>)}
    </>}
  </section>;
}
