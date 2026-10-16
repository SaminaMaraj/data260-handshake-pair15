import { useEffect, useState } from "react";

function App() {
  const [backendStatus, setBackendStatus] = useState("Connecting...");

  useEffect(() => {
    fetch("http://127.0.0.1:9150/")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Backend request failed");
        }
        return response.json();
      })
      .then((data) => {
        setBackendStatus(data.message);
      })
      .catch(() => {
        setBackendStatus("Could not connect to FastAPI");
      });
  }, []);

  return (
    <div>
      <h1>Handshake - Pair 15</h1>
      <h2>React Frontend</h2>
      <p>Backend Status: {backendStatus}</p>
    </div>
  );
}

export default App;