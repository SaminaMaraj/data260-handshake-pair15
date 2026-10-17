import { useEffect, useState } from "react";
import { apiFile, apiRequest } from "../api";
import "./StudentAccount.css";

export function Photo({ url, user }) {
  const [blob, setBlob] = useState("");
  useEffect(() => {
    let active = true, objectUrl;
    if (url?.startsWith("/media/profile/")) apiFile(url, { token: user.access_token })
      .then(data => { objectUrl = URL.createObjectURL(data); if (active) setBlob(objectUrl); })
      .catch(() => {});
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url, user.access_token]);
  const source = url?.startsWith("/media/profile/") ? blob : /^https?:\/\//.test(url || "") ? url : "";
  return source ? <img src={source} alt="Profile" className="profile-photo" /> : null;
}

export function Upload({ user, onUnauthorized, kind = "resume", onUploaded }) {
  const [file, setFile] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const photo = kind === "picture";
  async function submit(event) {
    event.preventDefault(); if (!file) return;
    setBusy(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await apiRequest(photo ? "/profiles/me/picture" : "/resumes", {
        method: "POST", token: user.access_token, onUnauthorized, body,
      });
      onUploaded(result); setFile(null); event.target.reset();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className={photo ? "my-3 border rounded p-3" : "resume-upload-panel"}>
    {!photo && <div className="resume-upload-heading"><span className="resume-document-icon" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 3H5v18h14V8z M14 3v5h5 M8 12h8 M8 16h6" /></svg></span><div><h3>Add a resume</h3><p>Upload a PDF to use with your applications.</p></div></div>}
    <label htmlFor={`upload-${kind}`}>{photo ? "Profile picture (PNG/JPEG, up to 3 MB)" : "PDF resume (up to 5 MB)"}</label>
    <input className="form-control" id={`upload-${kind}`} type="file" accept={photo ? "image/png,image/jpeg" : "application/pdf,.pdf"}
      required onChange={e => setFile(e.target.files[0] || null)} />
    {!photo && file && <p className="resume-selected-file" role="status">Selected: <strong>{file.name}</strong></p>}
    <button className={photo ? "btn btn-primary mt-2" : "resume-upload-button"} disabled={busy || !file}>{busy ? "Uploading..." : photo ? "Upload Picture" : "Upload Resume"}</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}

export function PdfPreview({ resumeId, user, onUnauthorized }) {
  const [url, setUrl] = useState(""), [error, setError] = useState("");
  useEffect(() => {
    let active = true, objectUrl;
    apiFile(`/resumes/${resumeId}/file`, { token: user.access_token, onUnauthorized })
      .then(data => { objectUrl = URL.createObjectURL(data); if (active) setUrl(objectUrl); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [resumeId, user.access_token, onUnauthorized]);
  return error ? <p role="alert">{error}</p> : url ? <>
    <a href={url} target="_blank" rel="noreferrer">Open PDF resume in a new tab</a>
    <iframe title="Applicant PDF resume" src={url} className="pdf-preview" />
  </> : <p role="status">Loading PDF...</p>;
}
