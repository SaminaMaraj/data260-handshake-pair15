import { CompanyHeading } from "./CompanyUI";
import StudentProfileLayout from "./StudentProfileLayout";
import { useEffect, useState } from "react";
import { apiRequest } from "../api";
import { Photo, Upload } from "./PartACommon";
import { Fields } from "./fields";
import { toPayload, toForm } from "./formValues";

const studentFields = [
  ["full_name", "Full name", "text", true, 150],
  ["college_name", "College name", "text", false, 255],
  ["career_objective", "Career objective", "textarea"],
  ["date_of_birth", "Date of birth", "date"],
  ["city", "City", "text", false, 100],
  ["state", "State", "text", false, 100],
  ["country", "Country", "text", false, 100],
  ["degree", "Degree", "text", false, 150],
  ["major", "Major", "text", false, 150],
  ["graduation_year", "Graduation year", "year"],
  ["cgpa", "CGPA", "cgpa"],
  ["education", "Education history", "textarea"],
  ["experience", "Experience", "textarea"],
  ["phone", "Phone", "tel", false, 30],
  ["profile_picture_url", "Profile picture URL", "text", false, 500],
  ["skills_json", "Skills (JSON array, e.g. [\"Python\", \"SQL\"])", "json"],
];
const companyFields = [
  ["company_name", "Company name", "text", true, 255],
  ["location", "Location", "text", false, 255],
  ["description", "Description", "textarea"],
  ["contact_phone", "Contact phone", "tel", false, 30],
  ["profile_picture_url", "Profile picture URL", "text", false, 500],
];

export default function ProfilePage({ user, onUnauthorized, onBack }) {
  const student = user.role === "student";
  const resource = student ? "/students" : "/companies";
  const fields = student ? studentFields : companyFields;
  const [accountEmail, setAccountEmail] = useState(user.email);
  const [form, setForm] = useState({});
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    apiRequest("/users/me", {token:user.access_token,onUnauthorized}).then(data=>{if(active)setAccountEmail(data.email);}).catch(()=>{});
    apiRequest(`${resource}/${user.id}`, { token: user.access_token, onUnauthorized })
      .then((data) => {
        if (active) { setForm(toForm(data)); setExists(true); }
      })
      .catch((err) => {
        if (active && err.status !== 404) setLoadError(err.message);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [resource, user.id, user.access_token, onUnauthorized, attempt]);

  async function save(event) {
    event.preventDefault();
    setError(""); setSuccess(""); setSaving(true);
    try {
      const body = toPayload(form, fields);
      const data = await apiRequest(exists ? `${resource}/${user.id}` : resource, {
        method: exists ? "PUT" : "POST", token: user.access_token, onUnauthorized,
        body: exists ? body : { ...body, user_id: user.id },
      });
      setForm(toForm(data));
      if (accountEmail !== user.email) {
        await apiRequest("/users/me", {method:"PUT", token:user.access_token, onUnauthorized, body:{email:accountEmail}});
      }
      setSuccess(exists ? "Profile updated successfully." : "Profile created successfully.");
      setExists(true);
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  if (student) return <StudentProfileLayout
    user={user} onUnauthorized={onUnauthorized} onBack={onBack} fields={fields}
    form={form} setForm={setForm} exists={exists} loading={loading} loadError={loadError}
    retry={() => { setLoadError(""); setLoading(true); setAttempt(attempt + 1); }}
    accountEmail={accountEmail} setAccountEmail={setAccountEmail} saving={saving}
    save={save} error={error} success={success}
    onPicture={data => { setForm({ ...form, ...data }); setSuccess("Profile picture updated."); }}
  />;

  return <section className="company-portal">
    <CompanyHeading title="Company Profile" description="Introduce your team and keep your company information up to date." onBack={onBack} />
    {loading ? <p role="status">Loading profile...</p> : loadError ? <>
      <p role="alert">Could not load profile. {loadError}</p>
      <button onClick={() => { setLoadError(""); setLoading(true); setAttempt(attempt + 1); }}>Retry</button>
    </> : <>
      {!exists && <p>No {student ? "student" : "company"} profile exists yet. Create yours below.</p>}
      <div className="company-panel company-profile-summary"><Photo url={form.profile_picture_url} user={user} /><div><span className="company-eyebrow">YOUR COMPANY</span><h2>{form.company_name || "Create your company profile"}</h2><p>{form.location || "Add your location below"}</p></div></div>
      <form className="company-panel company-form" onSubmit={save}>
        <fieldset disabled={saving}>
          <label htmlFor="profile-email">Email</label><input id="profile-email" type="email" required value={accountEmail} onChange={e=>setAccountEmail(e.target.value)} />
          <Fields fields={fields} form={form} setForm={setForm} />
          <button type="submit">{saving ? "Saving..." : exists ? "Save Changes" : "Create Profile"}</button>
        </fieldset>
      </form>
      {exists && <section className="company-panel company-logo"><h2>Company Logo</h2><p>Upload a profile picture to help students recognize your company.</p><Upload kind="picture" user={user} onUnauthorized={onUnauthorized} onUploaded={data=>{setForm({...form,...data});setSuccess("Profile picture updated.");}} /></section>}
    </>}
    {error && <p role="alert">{error}</p>}
    {success && <p role="status">{success}</p>}
  </section>;
}
