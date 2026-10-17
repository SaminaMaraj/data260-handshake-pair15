import useApiData from './useApiData';
import { CompanyState, JobStatus } from './CompanyUI';

export default function CompanyDashboard({ user, onUnauthorized, onNavigate }) {
  const profile = useApiData(`/companies/${user.id}`, user, onUnauthorized);
  const jobs = useApiData('/companies/me/jobs', user, onUnauthorized);
  const applications = useApiData('/companies/me/applications', user, onUnauthorized);
  const events = useApiData('/events?mine=true&upcoming=true', user, onUnauthorized);
  const name = profile.data?.company_name || user.company_name;
  return <div className="company-portal company-dashboard">
    <section className="company-welcome"><span className="company-eyebrow">BUILD YOUR NEXT TEAM</span>
      <h1>{name ? `Welcome back, ${name}.` : 'Your next great hire starts here.'}</h1>
      <p>Connect with students, share opportunities, and keep your hiring moving forward.</p>
      <div className="company-actions"><button onClick={() => onNavigate('post-job')}>+ Post a Job</button><button className="company-secondary" onClick={() => onNavigate('applicants')}>Review Applicants</button></div>
      {profile.error && <button className="company-link" onClick={() => onNavigate('profile')}>View or complete your company profile →</button>}
    </section>
    <section className="company-statistics" aria-label="Company activity summary">
      {[
        ['Job postings', jobs, 'company-jobs', 'All your opportunities'],
        ['Applications', applications, 'applicants', 'Across your job postings'],
        ['Upcoming events', events, 'events', 'Hosted by your company'],
      ].map(([label, result, page, caption]) => <article className="company-panel company-stat" key={label}>
        <h2>{label}</h2><CompanyState result={result} label={label.toLowerCase()}><strong>{result.data?.length}</strong></CompanyState><p>{caption}</p><button className="company-link" onClick={() => onNavigate(page)}>View {label.toLowerCase()} →</button>
      </article>)}
    </section>
    <div className="company-columns">
      <section className="company-panel"><div className="company-section-heading"><h2>Recent Job Postings</h2><button className="company-link" onClick={() => onNavigate('company-jobs')}>Manage jobs →</button></div>
        <CompanyState result={jobs} label="job postings">
          {!jobs.data?.length && <div className="company-empty"><h3>Make your first connection</h3><p>Post an opportunity to start receiving applications.</p><button onClick={() => onNavigate('post-job')}>Post a Job</button></div>}
          {jobs.data?.slice(0, 3).map(job => <article className="company-preview" key={job.id}><JobStatus job={job} /><h3>{job.title}</h3><p>{job.location} · {(job.category || 'Uncategorized').replaceAll('_', ' ')}{job.is_remote ? ' · Remote' : ''}</p><small>Posted {job.posting_date} · Deadline {job.deadline}</small></article>)}
        </CompanyState>
      </section>
      <section className="company-panel"><div className="company-section-heading"><h2>Application Activity</h2><button className="company-link" onClick={() => onNavigate('applicants')}>View all →</button></div>
        <CompanyState result={applications} label="applications">
          {!applications.data?.length && <div className="company-empty"><h3>No applications yet</h3><p>New applications to your jobs will appear here.</p></div>}
          {applications.data?.slice(0, 4).map(application => <article className="company-preview" key={application.id}><span className="company-badge is-muted">{application.status}</span><h3>{application.student_name}</h3><p>{application.job_title}</p><small>Applied {application.applied_at}</small></article>)}
        </CompanyState>
      </section>
    </div>
    <section className="company-panel company-quick-actions"><div><h2>Keep your company connected</h2><p>Help students discover your team and your next event.</p></div><div className="company-actions"><button className="company-secondary" onClick={() => onNavigate('profile')}>Company Profile</button><button className="company-secondary" onClick={() => onNavigate('events')}>Manage Events</button><button className="company-secondary" onClick={() => onNavigate('directory')}>Student Directory</button></div></section>
  </div>;
}
