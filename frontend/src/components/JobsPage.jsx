import useApiData from './useApiData';
import { emptyFilters, filterJobs, jobSearchPath } from './jobFilters';
import JobCard from './JobCard';
import './CareerPages.css';

export default function JobsPage({ user, onUnauthorized, onBack, onDetails, filters, setFilters }) {
  const { data, loading, error, retry } = useApiData(jobSearchPath(filters), user, onUnauthorized);
  const companies = useApiData('/companies', user, onUnauthorized);
  const saved = useApiData('/students/me/saved-jobs', user, onUnauthorized);
  const jobs = data ? filterJobs(data, { ...filters, title: '' }) : [];
  function change(event) { setFilters({ ...filters, [event.target.name]: event.target.value }); }
  return <section className="career-page">
    <button className="career-back" onClick={onBack}>← Dashboard</button>
    <header className="career-page-heading"><span className="career-eyebrow">FIND YOUR NEXT CHAPTER</span><h1>Discover your next opportunity.</h1><p>Explore roles that match your interests, skills, and ambitions.</p></header>
    <section className="career-filter-panel" aria-label="Job search and filters">
      <div className="career-search"><label htmlFor="job-title-filter">Company name or job title</label><input type="search" placeholder="Search opportunities…" id="job-title-filter" name="title" value={filters.title} onChange={change} /></div>
      <div className="career-filter-grid">
        <div><label htmlFor="job-location-filter">Location</label><input id="job-location-filter" name="location" placeholder="City or location" value={filters.location} onChange={change} /></div>
        <div><label htmlFor="job-category-filter">Employment type</label><select id="job-category-filter" name="category" value={filters.category} onChange={change}><option value="">All categories</option><option value="full_time">Full time</option><option value="part_time">Part time</option><option value="on_campus">On campus</option><option value="internship">Internship</option></select></div>
        <div><label htmlFor="job-remote-filter">Work arrangement</label><select id="job-remote-filter" name="remote" value={filters.remote} onChange={change}><option value="">All arrangements</option><option value="remote">Remote</option><option value="onsite">Onsite</option></select></div>
      </div><button className="career-secondary" onClick={() => setFilters({ ...emptyFilters })}>Clear Filters</button>
    </section>
    {saved.error && <div className="career-notice"><p>Saved status is unavailable. {saved.error}</p><button className="career-secondary" onClick={saved.retry}>Retry saved status</button></div>}
    {loading ? <p className="career-state" role="status">Finding opportunities…</p> : error ? <div className="career-state"><p role="alert">Could not load jobs. {error}</p><button onClick={retry}>Retry</button></div> : <>
      <p className="career-result-count" role="status">{jobs.length} {jobs.length === 1 ? 'opportunity' : 'opportunities'} found</p>
      {!jobs.length ? <div className="career-state"><h2>No matching opportunities yet.</h2><p>Try a different title, location, or employment type.</p><button onClick={() => setFilters({ ...emptyFilters })}>Clear Filters</button></div> :
        <div className="career-card-grid">{jobs.map(job => <JobCard key={job.id} job={job} companyName={companies.data?.find(company => company.user_id === job.company_id)?.company_name} saved={saved.data?.some(item => item.id === job.id)} onDetails={onDetails} />)}</div>}
    </>}
  </section>;
}
