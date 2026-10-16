import { useState } from 'react';
import useApiData from './useApiData';
import { apiRequest } from '../api';
import JobCard from './JobCard';
import './CareerPages.css';

export default function SavedJobsPage({ user, onUnauthorized, onBack, onDetails }) {
  const result = useApiData('/students/me/saved-jobs', user, onUnauthorized);
  const companies = useApiData('/companies', user, onUnauthorized);
  const [removing, setRemoving] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function remove(job) {
    setRemoving(job.id); setError(''); setNotice('');
    try {
      const entries = await apiRequest(`/saved-items/student/${user.id}`, { token: user.access_token, onUnauthorized });
      const ownEntries = entries.filter(entry => entry.student_id === user.id && entry.job_id === job.id);
      for (const entry of ownEntries) {
        await apiRequest(`/saved-items/${entry.id}`, { method: 'DELETE', token: user.access_token, onUnauthorized });
      }
      setNotice(`${job.title} removed from saved jobs.`);
      result.retry();
    } catch (err) { setError(err.message); result.retry(); }
    finally { setRemoving(null); }
  }
  return <section className="career-page">
    <button className="career-back" onClick={onBack}>← Dashboard</button>
    <header className="career-page-heading"><span className="career-eyebrow">YOUR OPPORTUNITY SHORTLIST</span><h1>Saved Jobs</h1><p>Keep your next possibilities close. Take another look when you're ready.</p></header>
    {notice && <p className="career-notice" role="status">{notice}</p>}{error && <p className="career-notice" role="alert">Could not remove saved job. {error}</p>}
    {result.loading ? <p className="career-state" role="status">Loading saved jobs…</p> : result.error ? <div className="career-state"><p role="alert">{result.error}</p><button onClick={result.retry}>Retry</button></div> : <>
      <p className="career-result-count" role="status">{result.data.length} saved {result.data.length === 1 ? 'job' : 'jobs'}</p>
      {!result.data.length ? <div className="career-state"><h2>A little space for your next big step.</h2><p>Save jobs from the dashboard or a job's detail page. They'll appear here.</p><button onClick={onBack}>Explore your dashboard</button></div> :
        <div className="career-card-grid">{result.data.map(job => <JobCard key={job.id} job={job} companyName={companies.data?.find(company => company.user_id === job.company_id)?.company_name} saved onDetails={onDetails}>
          <button className="career-secondary" disabled={removing !== null} onClick={() => remove(job)} aria-label={`Remove ${job.title} from saved jobs`}>{removing === job.id ? 'Removing…' : 'Remove saved job'}</button>
        </JobCard>)}</div>}
    </>}
  </section>;
}
