import useApiData from './useApiData';
import JobInfo from './JobInfo';
export default function SavedJobsPage({user,onUnauthorized,onBack,onDetails}){
  const result=useApiData('/students/me/saved-jobs',user,onUnauthorized);
  return <section className="feature-page"><button onClick={onBack}>Back to Dashboard</button><h1>Saved Jobs</h1>
    {result.loading?<p role="status">Loading saved jobs...</p>:result.error?<p role="alert">{result.error}</p>:<>
      <p>{result.data.length} saved jobs</p>{result.data.map(j=><article className="job-result" key={j.id}><h2>{j.title}</h2><JobInfo job={j}/><button onClick={()=>onDetails(j.id)}>View Details</button></article>)}
    </>}
  </section>;
}
