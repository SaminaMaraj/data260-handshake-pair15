import useApiData from "./useApiData";

export default function ApplicationsPage({ user, onUnauthorized, onBack, onBrowse, onDetails }) {
  const { data, loading, error, retry } = useApiData("/applications", user, onUnauthorized);
  return <section className="feature-page">
    <div className="page-actions"><button onClick={onBack}>Back to Dashboard</button><button onClick={onBrowse}>Browse Jobs</button></div>
    <h1>My Applications</h1>
    {loading ? <p role="status">Loading applications...</p> : error ? <>
      <p role="alert">Could not load applications. {error}</p><button onClick={retry}>Retry</button>
    </> : !data.length ? <p>You have not applied to any jobs yet.</p> : data.map((application) =>
      <article className="job-result" key={application.id}>
        <h2>{application.job_title}</h2>
        <p>Company: {application.company_name}</p>
        <p>Applied: {new Date(application.applied_at + (/[zZ]|[+-]\d\d:\d\d$/.test(application.applied_at) ? "" : "Z")).toLocaleString()}</p>
        <p>Status: {application.status}</p>
        <button onClick={() => onDetails(application.job_id)}>View Details</button>
      </article>)}
  </section>;
}
