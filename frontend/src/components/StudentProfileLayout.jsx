import { Photo, Upload } from './PartACommon';
import { Fields } from './fields';
import './StudentAccount.css';

const groups = [
  { title: 'Personal information', description: 'The details that help employers get to know you.', names: ['full_name', 'date_of_birth', 'phone', 'city', 'state', 'country'] },
  { title: 'Education', description: 'Your academic background and the path you are building.', names: ['college_name', 'degree', 'major', 'graduation_year', 'cgpa', 'education'] },
  { title: 'Skills & experience', description: 'Share your strengths, projects, and professional experience.', names: ['skills_json', 'experience'] },
  { title: 'Career interests', description: 'Tell employers what you would like to do next.', names: ['career_objective'] },
  { title: 'Profile image', description: 'Use an existing image URL, or upload a picture below after saving your profile.', names: ['profile_picture_url'] },
];

export default function StudentProfileLayout({ user, onUnauthorized, onBack, fields, form, setForm, exists, loading, loadError, retry, accountEmail, setAccountEmail, saving, save, error, success, onPicture }) {
  const name = form.full_name?.trim();
  const initials = (name || accountEmail || '').split(/\s+|@/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase();
  function edit() {
    document.getElementById('full_name')?.focus();
  }
  return <section className="student-account">
    <button className="account-back" onClick={onBack}>← Dashboard</button>
    <div className="account-page-heading"><span className="account-eyebrow">YOUR STORY, YOUR NEXT STEP</span><h1>Student Profile</h1><p>Build a clear picture of your experience and ambitions.</p></div>
    {loading ? <p className="account-panel" role="status">Loading profile…</p> : loadError ? <div className="account-panel"><p role="alert">Could not load profile. {loadError}</p><button onClick={retry}>Retry</button></div> : <>
      <header className="student-profile-hero"><div className="student-profile-identity"><div className="student-profile-avatar"><span aria-hidden="true">{initials}</span><Photo url={form.profile_picture_url} user={user} /></div><div><span className="account-eyebrow">STUDENT PROFILE</span><h2>{name || 'Make this profile yours'}</h2><p>{accountEmail}</p>{form.college_name && <p>{form.college_name}</p>}{(form.degree || form.major) && <p>{[form.degree, form.major].filter(Boolean).join(' · ')}</p>}</div></div><button onClick={edit} disabled={saving}>{exists ? 'Edit Profile' : 'Complete Profile'}</button></header>
      {!exists && <p className="account-message">No student profile exists yet. Complete the fields below to create yours.</p>}
      <form onSubmit={save} className="student-profile-form">
        <fieldset disabled={saving}>
          <section className="account-panel" aria-labelledby="student-contact-title"><h2 id="student-contact-title">Account email</h2><p className="account-description">Keep your contact email up to date.</p><label htmlFor="profile-email">Email <span aria-hidden="true">*</span></label><input id="profile-email" type="email" required value={accountEmail} onChange={event => setAccountEmail(event.target.value)} /></section>
          {groups.map((group, index) => <section className="account-panel" key={group.title} aria-labelledby={`profile-group-${index}`}><div className="account-section-heading"><span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span><div><h2 id={`profile-group-${index}`}>{group.title}</h2><p className="account-description">{group.description}</p></div></div><Fields fields={group.names.map(name => fields.find(field => field[0] === name))} form={form} setForm={setForm} /></section>)}
          <div className="account-save-bar"><p>Fields marked * are required.</p><div><button type="button" className="account-secondary" onClick={onBack}>Cancel</button><button type="submit">{saving ? 'Saving…' : exists ? 'Save Changes' : 'Create Profile'}</button></div></div>
        </fieldset>
      </form>
      {exists && <section className="account-panel student-photo-upload"><h2>Upload a profile picture</h2><p className="account-description">Choose a PNG or JPEG image, up to 3 MB.</p><Upload kind="picture" user={user} onUnauthorized={onUnauthorized} onUploaded={onPicture} /></section>}
    </>}
    {error && <p className="account-message" role="alert">{error}</p>}{success && <p className="account-message" role="status">{success}</p>}
  </section>;
}
