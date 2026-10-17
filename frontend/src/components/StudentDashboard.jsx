import { useState } from 'react';
import useApiData from './useApiData';
import { apiRequest } from '../api';
import AssistantChat from './AssistantChat';
import './StudentDashboard.css';

function Symbol({ kind }) {
  const paths = {
    jobs: 'M8 6V3h8v3 M3 7h18v14H3z M3 12c6 3 12 3 18 0 M12 11v5',
    applications: 'M14 3H5v18h14V8z M14 3v5h5 M8 12h8 M8 16h6',
    saved: 'M6 3h12v18l-6-4-6 4z',
    events: 'M3 5h18v16H3z M7 3v4 M17 3v4 M3 10h18 M7 14h3 M14 17h3',
    assistant: 'M3 5h18v12H9l-6 4z M8 10h1 M15 10h1 M9 13h6',
  };
  return <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind]} /></svg>;
}

function Skyline() {
  return <svg className="student-skyline" viewBox="0 0 380 200" fill="none" aria-hidden="true">
    <circle cx="282" cy="59" r="35" fill="var(--orange)" opacity=".18" />
    <path d="M0 170c70-20 130 15 200 0s120-12 180 0v30H0z" fill="var(--blue-soft)" />
    <g fill="var(--heading-navy)" opacity=".12"><path d="M185 160V88h22v72h8V45l13-31 13 31v115h12V68h24v92h12V101h32v59h14V80h23v80z" /></g>
    <g stroke="var(--heading-navy)" strokeWidth="3" strokeLinecap="round"><path d="M14 157h170 M44 168V75h10v93 M140 168V75h10v93 M16 126q32 0 33-46 48 90 96 0 10 46 39 46 M54 92v60 M72 113v39 M91 126v26 M111 125v27 M130 109v43" /></g>
    <path d="M20 183c24-7 40 7 64 0s40 7 64 0 40 7 64 0" stroke="var(--heading-navy)" opacity=".2" strokeWidth="2" />
  </svg>;
}

function LoadState({ result, label, children }) {
  if (result.loading) return <p className="student-state" role="status">Loading {label}…</p>;
  if (result.error) return <div className="student-state"><p role="alert">Could not load {label}. {result.error}</p><button className="student-secondary" onClick={result.retry}>Retry {label}</button></div>;
  return children;
}

function openAssistant() {
  const title = document.getElementById('assistant-title');
  if (title) {
    title.setAttribute('tabindex', '-1');
    title.focus({ preventScroll: true });
    title.scrollIntoView({ block: 'start' });
  }
}

export default function StudentDashboard({ user, onUnauthorized, onNavigate, onDetails, onEvent }) {
  const profile = useApiData(`/students/${user.id}`, user, onUnauthorized);
  const applications = useApiData('/applications', user, onUnauthorized);
  const saved = useApiData('/students/me/saved-jobs', user, onUnauthorized);
  const events = useApiData('/events?upcoming=true', user, onUnauthorized);
  const jobs = useApiData('/jobs', user, onUnauthorized);
  const companies = useApiData('/companies', user, onUnauthorized);
  const [saving, setSaving] = useState(null);
  const [saveError, setSaveError] = useState('');
  const [savedHere, setSavedHere] = useState([]);
  const [saveNotice, setSaveNotice] = useState('');
  const name = profile.data?.full_name || user.full_name || user.name;
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const available = (jobs.data || []).filter(job => job.deadline >= localDate)
    .sort((a, b) => b.posting_date.localeCompare(a.posting_date) || b.id - a.id);
  const savedIds = new Set([...(saved.data || []).map(job => job.id), ...savedHere]);
  const statistics = [
    { key: 'applications', label: 'Applications', result: applications, count: applications.data?.length },
    { key: 'saved', label: 'Saved Jobs', result: saved, count: savedIds.size },
    { key: 'events', label: 'Upcoming Events', result: events, count: events.data?.length },
    { key: 'jobs', label: 'Available Jobs', result: jobs, count: available.length },
  ];
  async function saveJob(job) {
    setSaving(job.id); setSaveError(''); setSaveNotice('');
    try {
      await apiRequest(`/students/me/saved-jobs/${job.id}`, { method: 'POST', token: user.access_token, onUnauthorized });
      setSavedHere(previous => [...previous, job.id]);
      setSaveNotice(`${job.title} saved to your jobs.`);
      saved.retry();
    } catch (error) { setSaveError(error.message); }
    finally { setSaving(null); }
  }

  return <><div className="student-dashboard">
    <section className="student-welcome" aria-labelledby="student-welcome-title">
      <div className="student-welcome-copy"><span className="student-eyebrow">YOUR NEXT CHAPTER STARTS HERE</span>
        <h2 id="student-welcome-title">{name ? `Welcome back, ${name.split(' ')[0]}!` : 'Welcome to your next opportunity.'}</h2>
        <p>Find your place in the Bay Area and beyond. Explore opportunities, meet employers, and take your next step.</p>
        <div className="student-actions"><button onClick={() => onNavigate('jobs')}>Browse Jobs <span aria-hidden="true">↗</span></button><button className="student-secondary" onClick={() => onNavigate('events')}>View Events</button></div>
        {profile.error && <button className="student-text-button" onClick={() => onNavigate('profile')}>View or complete your profile</button>}
      </div><Skyline />
    </section>

    <section className="student-statistics" aria-label="Your activity summary">
      {statistics.map(stat => <article className="student-stat" key={stat.key}><span className={`student-icon student-icon-${stat.key}`}><Symbol kind={stat.key} /></span><div>
        <h2>{stat.label}</h2><LoadState result={stat.result} label={stat.label.toLowerCase()}><strong className="student-stat-number">{stat.count}</strong></LoadState>
        <button className="student-text-button" onClick={() => onNavigate(stat.key)}>View {stat.label.toLowerCase()} <span aria-hidden="true">→</span></button>
      </div></article>)}
    </section>

    <div className="student-columns"><section className="student-panel student-jobs" aria-labelledby="student-jobs-title">
      <div className="student-section-heading"><div><span className="student-eyebrow">EXPLORE WHAT'S NEXT</span><h2 id="student-jobs-title">Latest Job Opportunities</h2></div><button className="student-text-button" onClick={() => onNavigate('jobs')}>View all <span aria-hidden="true">→</span></button></div>
      <LoadState result={jobs} label="job opportunities">
        {!available.length && <p className="student-state">No open jobs right now. Check back for new opportunities.</p>}
        {available.slice(0, 3).map(job => {
          const company = (companies.data || []).find(company => company.user_id === job.company_id)?.company_name;
          return <article className="student-job-preview" key={job.id}>
            <div className="student-job-heading"><span className="student-company-mark" aria-hidden="true">{company?.[0]?.toUpperCase() || <Symbol kind="jobs" />}</span><div><h3>{job.title}</h3><p>{company || `Company #${job.company_id}`}</p></div></div>
            <p className="student-job-location">{job.location}{job.is_remote ? ' · Remote' : ''}</p>
            <div className="student-tags"><span>{job.category.replaceAll('_', ' ')}</span>{(job.skills_json || []).slice(0, 3).map((skill, index) => <span key={index}>{skill}</span>)}</div>
            <div className="student-job-footer"><div>{job.salary != null && <p className="student-salary">Salary: {job.salary}</p>}<span className="student-muted">Posted {job.posting_date}</span></div><div className="student-actions">
              <button className="student-secondary" aria-label={`${savedIds.has(job.id) ? 'Saved' : 'Save'} ${job.title}`} disabled={savedIds.has(job.id) || saving !== null || saved.loading || !!saved.error} onClick={() => saveJob(job)}>{savedIds.has(job.id) ? 'Saved' : saving === job.id ? 'Saving…' : 'Save'}</button>
              <button onClick={() => onDetails(job.id)} aria-label={`View details for ${job.title}`}>View Details</button>
            </div></div>
          </article>;
        })}
      </LoadState>
      {saveError && <p role="alert">{saveError}</p>}{saveNotice && <p role="status">{saveNotice}</p>}
    </section>

    <aside className="student-secondary-column" aria-label="Career resources">
      <section className="student-assistant-preview"><span className="student-icon"><Symbol kind="assistant" /></span><span className="student-eyebrow">A LITTLE GUIDANCE</span><h2>Your career, in conversation.</h2><p>Open your existing assistant workspace to continue exploring your next steps.</p><button onClick={openAssistant}>Open Assistant <span aria-hidden="true">↗</span></button></section>
      <section className="student-panel" aria-labelledby="student-events-title"><div className="student-section-heading"><h2 id="student-events-title">Upcoming Events</h2><button className="student-text-button" onClick={() => onNavigate('events')}>View all</button></div>
        <LoadState result={events} label="events">
          {!events.data?.length && <p className="student-state">No upcoming events yet. Check back soon.</p>}
          {events.data?.slice(0, 3).map(event => {
            const date = new Date(`${event.event_date}T${event.event_time}`);
            return <article className="student-event-preview" key={event.id}><div className="student-date" aria-hidden="true"><span>{date.toLocaleDateString(undefined, { month: 'short' })}</span><strong>{date.getDate()}</strong></div><div><h3>{event.event_name}</h3><p>{event.company_name}</p><time dateTime={`${event.event_date}T${event.event_time}`}>{date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })} · {date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</time><p>{event.location}</p>{event.registered && <span className="student-registration">Registered</span>}<button className="student-text-button" onClick={() => onEvent(event.id)} aria-label={`View ${event.event_name} details`}>View event <span aria-hidden="true">→</span></button></div></article>;
          })}
        </LoadState>
      </section>
    </aside></div>
  </div><AssistantChat user={user} onUnauthorized={onUnauthorized} /></>;
}
