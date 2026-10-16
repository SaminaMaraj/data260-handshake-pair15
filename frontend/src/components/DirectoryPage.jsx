import { useState } from "react";
import useApiData from "./useApiData";
import { Photo } from "./PartACommon";

export function StudentDetails({ studentId, user, onUnauthorized, onBack }) {
  const profile = useApiData(`/students/${studentId}`, user, onUnauthorized);
  const contact = useApiData(`/profiles/${studentId}/contact`, user, onUnauthorized);
  return <section className="feature-page">
    <button onClick={onBack}>Back</button><h1>Student Profile</h1>
    {profile.loading ? <p role="status">Loading profile...</p> : profile.error ? <p role="alert">{profile.error}</p> : <>
      <Photo url={profile.data.profile_picture_url} user={user} />
      <h2>{profile.data.full_name}</h2>
      <dl className="job-info">{Object.entries(profile.data).filter(([key]) => !["user_id", "profile_picture_url", "full_name"].includes(key)).map(([key,value]) =>
        <div key={key}><dt>{key.replaceAll("_", " ").replace(" json", "")}</dt><dd>{Array.isArray(value) ? value.join(", ") : value ?? "Not provided"}</dd></div>)}
        <dt>Email</dt><dd>{contact.data?.email || contact.error || "Loading..."}</dd>
      </dl>
    </>}
  </section>;
}

export default function DirectoryPage({ user, onUnauthorized, onBack }) {
  const [q,setQ] = useState(""), [major,setMajor] = useState(""), [skill,setSkill] = useState(""), [selected,setSelected] = useState(null);
  const result = useApiData(`/directory/students?${new URLSearchParams({q,major,skill})}`, user, onUnauthorized);
  if (selected) return <StudentDetails studentId={selected} user={user} onUnauthorized={onUnauthorized} onBack={() => setSelected(null)} />;
  return <section className="feature-page">
    <button onClick={onBack}>Back to Dashboard</button><h1>Student Directory</h1>
    <div className="form-grid">
      <label>Name, college or skills<input value={q} onChange={e=>setQ(e.target.value)} /></label>
      <label>Major<input value={major} onChange={e=>setMajor(e.target.value)} /></label>
      <label>Skillset<input value={skill} onChange={e=>setSkill(e.target.value)} /></label>
    </div>
    {result.loading ? <p role="status">Loading students...</p> : result.error ? <p role="alert">{result.error}</p> : <>
      <p role="status">{result.data.length} students found.</p>
      {result.data.map(student => <article className="job-result" key={student.user_id}>
        <h2>{student.full_name}</h2><p>{student.college_name} · {student.major}</p>
        <p>{student.skills_json?.join(", ")}</p><button onClick={()=>setSelected(student.user_id)}>View Student Profile</button>
      </article>)}
    </>}
  </section>;
}
