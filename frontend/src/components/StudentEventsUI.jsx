import './EventsAssistant.css';

function EventDate({ event }) {
  return <div className="event-date-tile" aria-hidden="true"><span>{new Date(`${event.event_date}T12:00:00`).toLocaleDateString(undefined, { month: 'short' })}</span><strong>{Number(event.event_date.slice(-2))}</strong></div>;
}
function EventFacts({ event }) {
  return <dl className="event-facts"><dt>Date</dt><dd><time dateTime={event.event_date}>{event.event_date}</time></dd><dt>Time</dt><dd>{event.event_time} (local)</dd><dt>Location</dt><dd>{event.location}</dd></dl>;
}
export function StudentEventDiscovery({ q, setQ, mode, setMode, result, onBack, onSelect }) {
  return <section className="student-events">
    <button className="event-back" onClick={onBack}>← Dashboard</button>
    <header className="event-page-heading"><span className="event-eyebrow">MAKE YOUR NEXT CONNECTION</span><h1>Events & opportunities</h1><p>Meet employers, explore your interests, and take part in your career community.</p></header>
    <div className="event-filter-panel"><label>Search event name<input type="search" placeholder="Find an event…" value={q} onChange={e => setQ(e.target.value)} /></label><label>Event list<select value={mode} onChange={e => setMode(e.target.value)}><option value="all">Upcoming events</option><option value="registered">My registered events</option></select></label></div>
    {result.loading ? <p className="event-state" role="status">Loading events…</p> : result.error ? <div className="event-state"><p role="alert">{result.error}</p><button onClick={result.retry}>Retry events</button></div> : <>
      <p className="event-result-count" role="status">{result.data.length} events found · Ordered by date and time</p>
      {!result.data.length ? <div className="event-state"><h2>{mode === 'registered' ? 'No matching registrations.' : 'No matching upcoming events.'}</h2><p>{q ? 'Try a different event name or clear your search.' : mode === 'registered' ? 'Explore upcoming events and register from the event details.' : 'Check back for new events from employers.'}</p>{(q || mode !== 'all') && <button onClick={() => { setQ(''); setMode('all'); }}>Show upcoming events</button>}</div> :
        <div className="event-card-grid">{result.data.map(event => <article className="event-card" key={event.id}>
          <div className="event-card-heading"><EventDate event={event} /><div><p className="event-host">{event.company_name}</p><h2>{event.event_name}</h2></div></div>
          <EventFacts event={event} /><p className="event-card-description">{event.description}</p>
          <div className="event-card-eligibility"><strong>Eligibility</strong><p>{event.eligibility || 'See event details for eligibility.'}</p>{event.eligible_majors.length > 0 && <p>Majors: {event.eligible_majors.join(', ')}</p>}{event.eligible_colleges.length > 0 && <p>Colleges: {event.eligible_colleges.join(', ')}</p>}</div>
          {event.registered ? <span className="event-badge">Registered</span> : !event.eligible && <p className="event-eligibility-note">{event.ineligible_reason}</p>}
          <button onClick={() => onSelect(event.id)} aria-label={`View details for ${event.event_name}`}>{event.registered ? 'View registration details' : 'View details & registration'} <span aria-hidden="true">↗</span></button>
        </article>)}</div>}
    </>}
  </section>;
}
export function StudentEventDetail({ event, confirmed, setConfirmed, busy, error, register, onBack }) {
  return <section className="student-events">
    <button className="event-back" onClick={onBack}>← Back to Events</button>
    <header className="event-detail-hero"><EventDate event={event} /><div><span className="event-eyebrow">HOSTED BY {event.company_name}</span><h1>{event.event_name}</h1><p>{event.location}</p>{event.registered && <span className="event-badge">Registered</span>}</div></header>
    <div className="event-detail-grid"><div className="event-panel"><h2>About this event</h2><p className="event-description">{event.description}</p><h2>Who can attend</h2><p>{event.eligibility || 'All students'}</p>{event.eligible_majors.length > 0 && <p><strong>Majors:</strong> {event.eligible_majors.join(', ')}</p>}{event.eligible_colleges.length > 0 && <p><strong>Colleges:</strong> {event.eligible_colleges.join(', ')}</p>}</div>
      <aside className="event-panel event-registration"><span className="event-eyebrow">PLAN YOUR VISIT</span><h2>Event registration</h2><EventFacts event={event} />
        {event.registered ? <p className="event-confirmation" role="status">You are registered for this event.</p> : <>
          {!event.eligible && <p className="event-confirmation" role="status">{event.ineligible_reason}</p>}
          <label className={`event-confirm-choice${confirmed ? ' is-selected' : ''}`}><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /><span>I meet the written eligibility requirements.</span></label>
          <button disabled={!event.eligible || !confirmed || busy} onClick={register}>{busy ? 'Registering…' : 'Register for Event'}</button>
        </>}{error && <p className="event-confirmation" role="alert">{error}</p>}
      </aside></div>
  </section>;
}
