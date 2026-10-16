export default function JobCard({ job, companyName, saved, onDetails, children }) {
  return <article className="career-card">
    <div className="career-company"><span className="career-company-mark" aria-hidden="true">{companyName?.[0]?.toUpperCase() || '↗'}</span><div><p>{companyName || `Company #${job.company_id}`}</p><h2>{job.title}</h2></div></div>
    <p className="career-muted">{job.location} · {job.is_remote ? 'Remote' : 'Onsite'}</p>
    <div className="career-tags"><span>{job.category.replaceAll('_', ' ')}</span>{(job.skills_json || []).slice(0, 4).map((skill, index) => <span key={index}>{typeof skill === 'string' ? skill : JSON.stringify(skill)}</span>)}</div>
    <dl className="career-facts">{job.salary != null && <><dt>Salary</dt><dd>{job.salary}</dd></>}<dt>Posted</dt><dd>{job.posting_date}</dd><dt>Apply by</dt><dd>{job.deadline}</dd></dl>
    {saved && <p className="career-badge">Saved to your jobs</p>}
    <div className="career-card-actions"><button onClick={() => onDetails(job.id)} aria-label={`View details for ${job.title}`}>View Details <span aria-hidden="true">↗</span></button>{children}</div>
  </article>;
}
