import { useState } from "react";
import useApiData from "./useApiData";
import { apiRequest } from "../api";
function PreferenceForm({data,user,onUnauthorized}){
  const [form,setForm]=useState({...data,preferred_skills_json:data.preferred_skills_json?.join(', ')||''}),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  async function save(e){e.preventDefault();setBusy(true);setMessage('');
    try{await apiRequest('/students/me/preferences',{method:'PUT',token:user.access_token,onUnauthorized,body:{...form,
      preferred_city:form.preferred_city||null,preferred_category:form.preferred_category||null,minimum_salary:form.minimum_salary||null,
      preferred_skills_json:form.preferred_skills_json.split(',').map(s=>s.trim()).filter(Boolean)}});setMessage('Preferences saved.');}
    catch(err){setMessage(err.message);}finally{setBusy(false);}}
  return <form onSubmit={save}><div className="form-grid">
    <label>Preferred city<select value={form.preferred_city||''} onChange={e=>setForm({...form,preferred_city:e.target.value})}><option value="">Any city</option>
      {['Sunnyvale','Cupertino','Palo Alto'].map(c=><option key={c}>{c}</option>)}</select></label>
    <label>Preferred category<select value={form.preferred_category||''} onChange={e=>setForm({...form,preferred_category:e.target.value})}><option value="">Any category</option>
      {['full_time','part_time','on_campus','internship'].map(c=><option value={c} key={c}>{c.replaceAll('_',' ')}</option>)}</select></label>
    <label>Minimum salary<input type="number" min="0" step="0.01" value={form.minimum_salary??''} onChange={e=>setForm({...form,minimum_salary:e.target.value})} /></label>
    <label>Preferred skills (comma separated)<input value={form.preferred_skills_json} onChange={e=>setForm({...form,preferred_skills_json:e.target.value})} /></label>
    <label><input type="checkbox" checked={form.remote_only} onChange={e=>setForm({...form,remote_only:e.target.checked})} /> Remote only</label>
  </div><button disabled={busy}>Save Preferences</button>{message&&<p role="status">{message}</p>}</form>;
}
export default function PreferencesPage({user,onUnauthorized,onBack}){
  const result=useApiData('/students/me/preferences',user,onUnauthorized);
  return <section className="feature-page"><button onClick={onBack}>Back to Dashboard</button><h1>Job Preferences</h1>
    {result.loading?<p role="status">Loading preferences...</p>:result.error?<p role="alert">{result.error}</p>:<PreferenceForm data={result.data} user={user} onUnauthorized={onUnauthorized} />}
  </section>;
}
