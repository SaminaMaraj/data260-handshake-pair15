import { useEffect, useState } from "react";
import { apiRequest } from "../api";
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
  ["experience", "Experience", "textarea"],
  ["phone", "Phone", "tel", false, 30],
  ["profile_picture_url", "Profile picture URL", "url", false, 500],
  ["skills_json", "Skills (JSON array, e.g. [\"Python\", \"SQL\"])", "json"],
];
const companyFields = [
  ["company_name", "Company name", "text", true, 255],
  ["location", "Location", "text", false, 255],
  ["description", "Description", "textarea"],
  ["contact_phone", "Contact phone", "tel", false, 30],
  ["profile_picture_url", "Profile picture URL", "url", false, 500],
];

export default function ProfilePage({ user, onUnauthorized, onBack }) {
  const student = user.role === "student";
  const resource = student ? "/students" : "/companies";
  const fields = student ? studentFields : companyFields;
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
      setSuccess(exists ? "Profile updated successfully." : "Profile created successfully.");
      setExists(true);
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  return <section className="feature-page">
    <button onClick={onBack}>Back to Dashboard</button>
    <h1>{student ? "Student" : "Company"} Profile</h1>
    {loading ? <p role="status">Loading profile...</p> : loadError ? <>
      <p role="alert">Could not load profile. {loadError}</p>
      <button onClick={() => { setLoadError(""); setLoading(true); setAttempt(attempt + 1); }}>Retry</button>
    </> : <>
      {!exists && <p>No {student ? "student" : "company"} profile exists yet. Create yours below.</p>}
      <form onSubmit={save}>
        <fieldset disabled={saving}>
          <Fields fields={fields} form={form} setForm={setForm} />
          <button type="submit">{saving ? "Saving..." : exists ? "Save Changes" : "Create Profile"}</button>
        </fieldset>
      </form>
    </>}
    {error && <p role="alert">{error}</p>}
    {success && <p role="status">{success}</p>}
  </section>;
}
