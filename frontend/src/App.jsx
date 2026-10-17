import StudentDashboard from "./components/StudentDashboard";

import AppShell from "./components/AppShell";

import EventsPage from "./components/EventsPage";

import DirectoryPage from "./components/DirectoryPage";

import ApplicantsPage from "./components/ApplicantsPage";

import PreferencesPage from "./components/PreferencesPage";

import SavedJobsPage from "./components/SavedJobsPage";

import AssistantChat from "./components/AssistantChat";

import { useCallback, useEffect, useState } from "react";

import "./App.css";

import ProfilePage from "./components/ProfilePage";

import JobPostPage from "./components/JobPostPage";

import JobsPage from "./components/JobsPage";

import JobDetailsPage from "./components/JobDetailsPage";

import CompanyJobsPage from "./components/CompanyJobsPage";

import ApplicationsPage from "./components/ApplicationsPage";

import { emptyFilters } from "./components/jobFilters";



const API_URL = "http://127.0.0.1:9150";



function App() {

  const [editingJob,setEditingJob]=useState(null);

  const [applicantJobId,setApplicantJobId]=useState("");

  const [jobId, setJobId] = useState(null);

  const [eventId, setEventId] = useState(null);

  const [filters, setFilters] = useState({ ...emptyFilters });

  const [page, setPage] = useState("dashboard");

  const [mode, setMode] = useState("login");

  const [email, setEmail] = useState("");

  const [password, setPassword] = useState("");

  const [role, setRole] = useState("student");

  const [message, setMessage] = useState("");

  const [currentUser, setCurrentUser] = useState(null);

  const [backendStatus, setBackendStatus] = useState("Connecting...");



  useEffect(() => {

    const controller = new AbortController();

    fetch(`${API_URL}/`, { signal: controller.signal })

      .then((response) => {

        if (!response.ok) {

          throw new Error("Backend request failed");

        }

        return response.json();

      })

      .then((data) => setBackendStatus(data.message))

      .catch((error) => {

        if (error.name !== "AbortError") {

          setBackendStatus("Could not connect to FastAPI");

        }
      });
    return () => controller.abort();
  }, []);


  const handleSubmit = async (event) => {
    event.preventDefault();
    setMessage("");

    const endpoint =
      mode === "signup" ? "/users/register" : "/users/login";

    const body =
      mode === "signup"
        ? { email, password, role }
        : { email, password };

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      const data = await response.json();

      if (!response.ok) {
        setMessage(typeof data.detail === "string" ? data.detail : "Please check your input.");
        return;
      }

      if (mode === "signup") {
        setMessage("Account created successfully! You can now log in.");
        setMode("login");
        setPassword("");
      } else {
        const dashboardPath = data.role === "student"
          ? "/students/me/dashboard" : "/companies/me/dashboard";
        const dashboardResponse = await fetch(`${API_URL}${dashboardPath}`, {
          headers: { Authorization: `Bearer ${data.access_token}` },
        });
        if (!dashboardResponse.ok) {
          setMessage("Could not authenticate your dashboard. Please log in again.");
          return;
        }
        const verifiedUser = await dashboardResponse.json();
        // Keep the token in memory; logout and page reload clear it.
        setCurrentUser({ ...verifiedUser, access_token: data.access_token });
        setPassword("");
        setMessage("");
      }
    } catch {
      setMessage("Could not connect to the backend.");
    }
  };

  const handleLogout = () => {
    setFilters({ ...emptyFilters });
    setJobId(null);
    setEventId(null);
    setPage("dashboard");
    setCurrentUser(null);
    setEmail("");
    setPassword("");
    setMessage("");
    setMode("login");
  };

  const handleUnauthorized = useCallback(() => {
    setCurrentUser(null);
    setPage("dashboard");
    setPassword("");
    setMode("login");
    setMessage("Your session expired or is invalid. Please log in again.");
  }, []);

  function showJob(id) { setJobId(id); setPage("job-details"); }

  function navigate(page) {
    if (page === "events") setEventId(null);
    if (page === "post-job") setEditingJob(null);
    if (page === "applicants") setApplicantJobId("");
    setPage(page);
  }
  const shell = { user: currentUser, page, onNavigate: navigate, onLogout: handleLogout };


  if (currentUser && ["events","directory","applicants","preferences","saved"].includes(page)) {
    const shared={user:currentUser,onUnauthorized:handleUnauthorized,onBack:()=>setPage("dashboard")};
    return <AppShell {...shell}>
        {page==="events" && <EventsPage {...shared} initialEventId={eventId} />}
        {page==="directory" && <DirectoryPage {...shared} />}
        {page==="applicants" && currentUser.role==="company" && <ApplicantsPage {...shared} initialJobId={applicantJobId} />}
        {page==="preferences" && currentUser.role==="student" && <PreferencesPage {...shared} />}
        {page==="saved" && currentUser.role==="student" && <SavedJobsPage {...shared} onDetails={showJob} />}
      </AppShell>;
  }

  if (currentUser?.role === "company" && page === "company-jobs") {
    return <AppShell {...shell}><CompanyJobsPage user={currentUser} onUnauthorized={handleUnauthorized}
        onBack={() => setPage("dashboard")} onPost={() => {setEditingJob(null);setPage("post-job");}}
        onEdit={job=>{setEditingJob(job);setPage("post-job");}} onApplicants={id=>{setApplicantJobId(id);setPage("applicants");}} /></AppShell>;
  }

  if (currentUser?.role === "student" && ["jobs", "job-details", "applications"].includes(page)) {
    const shared = { user: currentUser, onUnauthorized: handleUnauthorized };
    return <AppShell {...shell}>
        {page === "jobs" ? <JobsPage {...shared} filters={filters} setFilters={setFilters}
          onBack={() => setPage("dashboard")} onDetails={showJob} /> :
          page === "job-details" ? <JobDetailsPage key={jobId} {...shared} jobId={jobId}
            onBack={() => setPage("jobs")} onApplications={() => setPage("applications")}
            onProfile={() => setPage("profile")} /> :
            <ApplicationsPage {...shared} onBack={() => setPage("dashboard")}
              onBrowse={() => setPage("jobs")} onDetails={showJob} />}
      </AppShell>;
  }

  if (currentUser && ((page === "profile" && ["student", "company"].includes(currentUser.role)) ||
      (page === "post-job" && currentUser.role === "company"))) {
    return <AppShell {...shell}>
        {page === "profile" ? <ProfilePage user={currentUser} onUnauthorized={handleUnauthorized}
          onBack={() => setPage("dashboard")} /> :
          <JobPostPage key={editingJob?.id || "new"} existingJob={editingJob} user={currentUser} onUnauthorized={handleUnauthorized}
            onBack={() => setPage("dashboard")} onProfile={() => setPage("profile")} />}
      </AppShell>;
  }

  if (currentUser?.role === "student") {
    return <AppShell {...shell}>
      <StudentDashboard user={currentUser} onUnauthorized={handleUnauthorized}
        onNavigate={navigate} onDetails={showJob}
        onEvent={id => { setEventId(id); setPage("events"); }} />
    </AppShell>;
  }

  if (currentUser?.role === "company") {
    return (
      <AppShell {...shell}>
          <div className="dashboard-header">
            <h1>Company Dashboard</h1>
            <p>Welcome, {currentUser.email}</p>
          </div>

          <div className="dashboard-grid">
            <div className="dashboard-card">
              <h3>Company Profile</h3>
              <p>View and manage your company information.</p>
              <button onClick={() => setPage("profile")}>View Profile</button>
            </div>

            <div className="dashboard-card">
              <h3>Post a Job</h3>
              <p>Create a new job or internship opportunity.</p>
              <button onClick={() => {setEditingJob(null);setPage("post-job");}}>Post Job</button>
            </div>

            <div className="dashboard-card">
              <h3>My Job Posts</h3>
              <p>View and manage your active job postings.</p>
              <button onClick={() => setPage("company-jobs")}>View Jobs</button>
            </div>

            <div className="dashboard-card">
              <h3>Applicants</h3>
              <p>Review students who applied to your opportunities.</p>
              <button onClick={()=>{setApplicantJobId("");setPage("applicants");}}>View Applicants</button>
            </div>
          </div>
          <div className="d-flex flex-wrap gap-3 mt-3">
            <button onClick={()=>setPage("events")}>Events</button>
            <button onClick={()=>setPage("directory")}>Student Directory</button>
            {currentUser.role==="student"&&<button onClick={()=>setPage("preferences")}>Job Preferences</button>}
          </div>
          <AssistantChat user={currentUser} onUnauthorized={handleUnauthorized} />
        </AppShell>
    );
  }

  return (
    <div className="app">
      <div className="auth-card">
        <h1>Handshake</h1>
        <p className="subtitle">Pair 15 Career Platform</p>
        <p role="status">{backendStatus}</p>

        <div className="tabs">
          <button
            className={mode === "login" ? "active" : ""}
            onClick={() => {
              setMode("login");
              setMessage("");
            }}
          >
            Login
          </button>

          <button
            className={mode === "signup" ? "active" : ""}
            onClick={() => {
              setMode("signup");
              setMessage("");
            }}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <label htmlFor="auth-email">Email</label>
          <input
            id="auth-email"
            type="email"
            placeholder="Enter your email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          {mode === "signup" && (
            <>
              <label htmlFor="auth-role">Account Type</label>
              <select
                id="auth-role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                <option value="student">Student</option>
                <option value="company">Company</option>
              </select>
            </>
          )}

          <button className="submit-button" type="submit">
            {mode === "signup" ? "Create Account" : "Login"}
          </button>
        </form>

        {message && <p className="message">{message}</p>}
      </div>
    </div>
  );
}

export default App;