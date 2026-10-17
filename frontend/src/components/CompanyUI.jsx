import './CompanyPortal.css';

export function CompanyHeading({ title, description, onBack, children }) {
  return <header className="company-heading">
    {onBack && <button className="company-back" onClick={onBack}>← Back to Dashboard</button>}
    <div className="company-heading-row"><div><span className="company-eyebrow">COMPANY WORKSPACE</span><h1>{title}</h1><p>{description}</p></div>{children && <div className="company-actions">{children}</div>}</div>
  </header>;
}

export function CompanyState({ result, label, children }) {
  if (result.loading) return <p className="company-state" role="status">Loading {label}…</p>;
  if (result.error) return <div className="company-state"><p role="alert">Could not load {label}. {result.error}</p><button className="company-secondary" onClick={result.retry}>Retry {label}</button></div>;
  return children;
}

export function JobStatus({ job }) {
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const closed = job.deadline < today;
  return <span className={`company-badge ${closed ? 'is-muted' : ''}`}>{closed ? 'Deadline passed' : 'Accepting applications'}</span>;
}
