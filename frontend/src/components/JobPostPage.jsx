import { CompanyHeading } from "./CompanyUI";
import { useState } from "react";
import { apiRequest } from "../api";
import { Fields } from "./fields";
import { toPayload, toForm } from "./formValues";

const fields = [
  ["title", "Job title", "text", true, 255],
  ["posting_date", "Posting date", "date", true],
  ["deadline", "Deadline", "date", true],
  ["location", "Location", "text", true, 255],
  ["salary", "Salary", "salary"],
  ["category", "Category", "category", true],
  ["description", "Description", "textarea", true],
  ["is_remote", "Remote position", "checkbox"],
  ["skills_json", "Skills (JSON array, e.g. [\"Python\", \"SQL\"])", "json"],
];

export default function JobPostPage({ user, onUnauthorized, onBack, onProfile, existingJob = null }) {
  const [form, setForm] = useState(existingJob ? toForm(existingJob) : { posting_date: new Date().toLocaleDateString("en-CA"), is_remote: false });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [needsProfile, setNeedsProfile] = useState(false);
  const [created, setCreated] = useState(null);
  async function save(event) {
    event.preventDefault(); setError(""); setNeedsProfile(false); setSaving(true);
    try {
      const body = toPayload(form, fields);
      if (body.deadline < body.posting_date) throw new Error("Deadline must be on or after posting date.");
      setCreated(await apiRequest(existingJob ? `/jobs/${existingJob.id}` : "/jobs", {
        method: existingJob ? "PUT" : "POST", token: user.access_token, onUnauthorized,
        body: existingJob ? body : { ...body, company_id: user.id },
      }));
    } catch (err) {
      if (err.status === 409) { setNeedsProfile(true); setError("Create your company profile before posting a job."); }
      else setError(err.message);
    } finally { setSaving(false); }
  }
  return <section className="company-portal">
    <CompanyHeading title={existingJob ? "Edit Job" : "Post a Job"} description="Share the details students need to find their next opportunity. Required fields are marked *." onBack={onBack} />
    {created ? <p role="status">{existingJob ? "Job updated successfully." : "Job posted successfully."} {created.title} (Job #{created.id})</p> :
      <form className="company-panel company-form" onSubmit={save}><fieldset disabled={saving}>
        <Fields fields={fields} form={form} setForm={setForm} />
        <button type="submit">{saving ? "Saving..." : existingJob ? "Save Job Changes" : "Post Job"}</button>
      </fieldset></form>}
    {error && <p role="alert">{error}</p>}
    {needsProfile && <button onClick={onProfile}>Create Company Profile</button>}
  </section>;
}
