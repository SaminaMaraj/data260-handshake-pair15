import useApiData from "./useApiData";
import { emptyFilters, filterJobs, jobSearchPath } from "./jobFilters";
import JobInfo from "./JobInfo";

export default function JobsPage({ user, onUnauthorized, onBack, onDetails, filters, setFilters }) {
  const { data, loading, error, retry } = useApiData(jobSearchPath(filters), user, onUnauthorized);
  const jobs = data ? filterJobs(data, { ...filters, title: "" }) : [];
  function change(event) { setFilters({ ...filters, [event.target.name]: event.target.value }); }
  return <section className="feature-page">
    <button onClick={onBack}>Back to Dashboard</button>
    <h1>Browse Jobs</h1>
    <div className="form-grid">
      <div><label htmlFor="job-title-filter">Company name or job title</label><input id="job-title-filter" name="title" value={filters.title} onChange={change} /></div>
      <div><label htmlFor="job-location-filter">Location</label><input id="job-location-filter" name="location" value={filters.location} onChange={change} /></div>
      <div><label htmlFor="job-category-filter">Category</label><select id="job-category-filter" name="category" value={filters.category} onChange={change}>
        <option value="">All categories</option><option value="full_time">Full time</option><option value="part_time">Part time</option>
        <option value="on_campus">On campus</option><option value="internship">Internship</option>
      </select></div>
      <div><label htmlFor="job-remote-filter">Work arrangement</label><select id="job-remote-filter" name="remote" value={filters.remote} onChange={change}>
        <option value="">All arrangements</option><option value="remote">Remote</option><option value="onsite">Onsite</option>
      </select></div>
    </div>
    <button onClick={() => setFilters({ ...emptyFilters })}>Clear Filters</button>
    {loading ? <p role="status">Loading jobs...</p> : error ? <>
      <p role="alert">Could not load jobs. {error}</p><button onClick={retry}>Retry</button>
    </> : <>
      <p role="status">{!jobs.length ? "No jobs match your filters." : `${jobs.length} jobs found.`}</p>
      {jobs.map((job) => <article className="job-result" key={job.id}>
        <h2>{job.title}</h2><JobInfo job={job} />
        <button onClick={() => onDetails(job.id)}>View Details</button>
      </article>)}
    </>}
  </section>;
}
