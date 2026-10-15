import { useCallback, useState } from "react";
import "./App.css";
import ProfilePage from "./components/ProfilePage";
import JobPostPage from "./components/JobPostPage";
import JobsPage from "./components/JobsPage";
import JobDetailsPage from "./components/JobDetailsPage";
import ApplicationsPage from "./components/ApplicationsPage";
import { emptyFilters } from "./components/jobFilters";

const API_URL = "http://127.0.0.1:9150";

function App() {
  const [jobId, setJobId] = useState(null);
  const [filters, setFilters] = useState({ ...emptyFilters });
  const [page, setPage] = useState("dashboard");
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("student");
  const [message, setMessage] = useState("");
  const [currentUser, setCurrentUser] = useState(null);

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

  if (currentUser?.role === "student" && ["jobs", "job-details", "applications"].includes(page)) {
    const shared = { user: currentUser, onUnauthorized: handleUnauthorized };
    return <div className="dashboard-page">
      <nav className="dashboard-nav"><h2>Handshake</h2><button onClick={handleLogout}>Logout</button></nav>
      <main className="dashboard">
        {page === "jobs" ? <JobsPage {...shared} filters={filters} setFilters={setFilters}
          onBack={() => setPage("dashboard")} onDetails={showJob} /> :
          page === "job-details" ? <JobDetailsPage key={jobId} {...shared} jobId={jobId}
            onBack={() => setPage("jobs")} onApplications={() => setPage("applications")}
            onProfile={() => setPage("profile")} /> :
            <ApplicationsPage {...shared} onBack={() => setPage("dashboard")}
              onBrowse={() => setPage("jobs")} onDetails={showJob} />}
      </main>
    </div>;
  }

  if (currentUser && ((page === "profile" && ["student", "company"].includes(currentUser.role)) ||
      (page === "post-job" && currentUser.role === "company"))) {
    return <div className="dashboard-page">
      <nav className="dashboard-nav"><h2>Handshake</h2><button onClick={handleLogout}>Logout</button></nav>
      <main className="dashboard">
        {page === "profile" ? <ProfilePage user={currentUser} onUnauthorized={handleUnauthorized}
          onBack={() => setPage("dashboard")} /> :
          <JobPostPage user={currentUser} onUnauthorized={handleUnauthorized}
            onBack={() => setPage("dashboard")} onProfile={() => setPage("profile")} />}
      </main>
    </div>;
  }

  if (currentUser?.role === "student") {
    return (
      <div className="dashboard-page">
        <nav className="dashboard-nav">
          <div>
            <h2>Handshake</h2>
            <span>Student Portal</span>
          </div>

          <button onClick={handleLogout}>Logout</button>
        </nav>

        <main className="dashboard">
          <div className="dashboard-header">
            <h1>Student Dashboard</h1>
            <p>Welcome, {currentUser.email}</p>
          </div>

          <div className="dashboard-grid">
            <div className="dashboard-card">
              <h3>My Profile</h3>
              <p>View and manage your student profile and skills.</p>
              <button onClick={() => setPage("profile")}>View Profile</button>
            </div>

            <div className="dashboard-card">
              <h3>Browse Jobs</h3>
              <p>Explore internships, part-time and full-time opportunities.</p>
              <button onClick={() => setPage("jobs")}>Browse Jobs</button>
            </div>

            <div className="dashboard-card">
              <h3>Applications</h3>
              <p>Track the jobs you have applied to.</p>
              <button onClick={() => setPage("applications")}>My Applications</button>
            </div>

            <div className="dashboard-card">
              <h3>Saved Jobs</h3>
              <p>Review opportunities you saved for later.</p>
              <button>Saved Jobs</button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (currentUser?.role === "company") {
    return (
      <div className="dashboard-page">
        <nav className="dashboard-nav">
          <div>
            <h2>Handshake</h2>
            <span>Company Portal</span>
          </div>

          <button onClick={handleLogout}>Logout</button>
        </nav>

        <main className="dashboard">
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
              <button onClick={() => setPage("post-job")}>Post Job</button>
            </div>

            <div className="dashboard-card">
              <h3>My Job Posts</h3>
              <p>View and manage your active job postings.</p>
              <button>View Jobs</button>
            </div>

            <div className="dashboard-card">
              <h3>Applicants</h3>
              <p>Review students who applied to your opportunities.</p>
              <button>View Applicants</button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="auth-card">
        <h1>Handshake</h1>
        <p className="subtitle">Pair 15 Career Platform</p>

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
          <label>Email</label>
          <input
            type="email"
            placeholder="Enter your email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <label>Password</label>
          <input
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          {mode === "signup" && (
            <>
              <label>Account Type</label>
              <select
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