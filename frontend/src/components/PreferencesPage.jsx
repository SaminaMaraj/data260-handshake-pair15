import { useState } from 'react';
import useApiData from './useApiData';
import { apiRequest } from '../api';
import './StudentAccount.css';

function PreferenceForm({ data, user, onUnauthorized }) {
  const [form, setForm] = useState({ ...data, preferred_skills_json: data.preferred_skills_json?.join(', ') || '' });
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [failed, setFailed] = useState(false);
  async function save(e) {
    e.preventDefault(); setBusy(true); setMessage(''); setFailed(false);
    try {
      await apiRequest('/students/me/preferences', { method: 'PUT', token: user.access_token, onUnauthorized, body: {
        ...form, preferred_city: form.preferred_city || null, preferred_category: form.preferred_category || null, minimum_salary: form.minimum_salary || null,
        preferred_skills_json: form.preferred_skills_json.split(',').map(s => s.trim()).filter(Boolean),
      } });
      setMessage('Preferences saved.');
    } catch (err) { setFailed(true); setMessage(err.message); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save} className="student-preferences-form">
    <div className="account-panel"><div className="account-section-heading"><span aria-hidden="true">01</span><div><h2>Where & how you work</h2><p className="account-description">Choose a location and the type of opportunity you prefer.</p></div></div>
      <div className="form-grid"><label>Preferred city<select value={form.preferred_city || ''} onChange={e => setForm({ ...form, preferred_city: e.target.value })}><option value="">Any city</option>{['Sunnyvale', 'Cupertino', 'Palo Alto'].map(city => <option key={city}>{city}</option>)}</select></label>
        <label>Preferred category<select value={form.preferred_category || ''} onChange={e => setForm({ ...form, preferred_category: e.target.value })}><option value="">Any category</option>{['full_time', 'part_time', 'on_campus', 'internship'].map(category => <option value={category} key={category}>{category.replaceAll('_', ' ')}</option>)}</select></label></div>
      <label className={`account-choice${form.remote_only ? ' is-selected' : ''}`}><input type="checkbox" checked={form.remote_only} onChange={e => setForm({ ...form, remote_only: e.target.checked })} /><span><strong>Remote only</strong><span>Indicate that you prefer remote opportunities.</span></span></label>
    </div>
    <div className="account-panel"><div className="account-section-heading"><span aria-hidden="true">02</span><div><h2>Skills & compensation</h2><p className="account-description">Help describe the opportunities that interest you.</p></div></div>
      <div className="form-grid"><label>Minimum salary<input type="number" min="0" step="0.01" value={form.minimum_salary ?? ''} onChange={e => setForm({ ...form, minimum_salary: e.target.value })} /></label><label>Preferred skills (comma separated)<input value={form.preferred_skills_json} onChange={e => setForm({ ...form, preferred_skills_json: e.target.value })} /></label></div>
    </div>
    <div className="account-save-bar"><p>You can update these preferences at any time.</p><button disabled={busy}>{busy ? 'Saving…' : 'Save Preferences'}</button></div>
    {message && <p className="account-message" role={failed ? 'alert' : 'status'}>{message}</p>}
  </form>;
}
export default function PreferencesPage({ user, onUnauthorized, onBack }) {
  const result = useApiData('/students/me/preferences', user, onUnauthorized);
  return <section className="student-account"><button className="account-back" onClick={onBack}>← Dashboard</button>
    <header className="account-page-heading"><span className="account-eyebrow">MAKE YOUR SEARCH YOURS</span><h1>Job Preferences</h1><p>Set your interests and preferred working arrangements in one place.</p></header>
    {result.loading ? <p className="account-panel" role="status">Loading preferences…</p> : result.error ? <div className="account-panel"><p role="alert">{result.error}</p><button onClick={result.retry}>Retry</button></div> : <PreferenceForm data={result.data} user={user} onUnauthorized={onUnauthorized} />}
  </section>;
}
