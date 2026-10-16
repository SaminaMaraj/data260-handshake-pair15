import { useState } from 'react';
import useApiData from './useApiData';
import './CareerPages.css';

function dateLabel(value) {
  return new Date(value + (/[zZ]|[+-]\d\d:\d\d$/.test(value) ? '' : 'Z')).toLocaleString();
}
export default function ApplicationsPage({ user, onUnauthorized, onBack, onBrowse, onDetails }) {
  const [status, setStatus] = useState('');
  const { data, loading, error, retry } = useApiData(`/applications${status ? `?status=${status}` : ''}`, user, onUnauthorized);
  const resumes = useApiData('/applications/resume-options', user, onUnauthorized);
  return <section className="career-page">
    <button className="career-back" onClick={onBack}>← Dashboard</button>
    <header className="career-page-heading career-heading-actions"><div><span className="career-eyebrow">EVERY STEP COUNTS</span><h1>My Applications</h1><p>Follow your progress and revisit the opportunities you've applied for.</p></div><button onClick={onBrowse}>Browse Jobs ↗</button></header>
    <div className="career-filter-panel"><label htmlFor="application-status-filter">Application status</label><select id="application-status-filter" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{['pending', 'reviewed', 'declined'].map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></div>
    {loading ? <p className="career-state" role="status">Loading applications…</p> : error ? <div className="career-state"><p role="alert">Could not load applications. {error}</p><button onClick={retry}>Retry</button></div> : !data.length ? <div className="career-state"><h2>{status ? 'No applications with this status.' : 'Your next chapter starts with an application.'}</h2><p>{status ? 'Choose another status to see more of your history.' : 'Find a role you like and apply with your resume.'}</p><button onClick={status ? () => setStatus('') : onBrowse}>{status ? 'Show all applications' : 'Browse Jobs'}</button></div> : <>
      <p className="career-result-count" role="status">{data.length} {data.length === 1 ? 'application' : 'applications'}</p>
      <div className="career-application-list">{data.map(application => <article className="career-card career-application" key={application.id}>
        <div className="career-application-heading"><div><p className="career-muted">{application.company_name || 'Company information unavailable'}</p><h2>{application.job_title || `Job #${application.job_id}`}</h2></div><span className={`career-badge career-status-${application.status}`}>{application.status}</span></div>
        <dl className="career-facts"><dt>Applied</dt><dd>{dateLabel(application.applied_at)}</dd>{application.reviewed_at && <><dt>Reviewed</dt><dd>{dateLabel(application.reviewed_at)}</dd></>}<dt>Resume</dt><dd>{resumes.data?.find(resume => resume.id === application.resume_id)?.original_filename || `Resume #${application.resume_id}`}</dd></dl>
        <button onClick={() => onDetails(application.job_id)} aria-label={`View details for ${application.job_title || 'job ' + application.job_id}`}>View Job Details ↗</button>
      </article>)}</div>
    </>}
  </section>;
}
