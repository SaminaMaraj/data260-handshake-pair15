import { useEffect, useState } from "react";
import { apiRequest } from "../api";

export default function useApiData(path, user, onUnauthorized) {
  const [state, setState] = useState({ data: null, loading: true, error: "" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest(path, { token: user.access_token, onUnauthorized })
      .then((data) => { if (active) setState({ data, loading: false, error: "" }); })
      .catch((error) => { if (active) setState({ data: null, loading: false, error: error.message }); });
    return () => { active = false; };
  }, [path, user.access_token, onUnauthorized, attempt]);
  function retry() {
    setState({ data: null, loading: true, error: "" });
    setAttempt((value) => value + 1);
  }
  return { ...state, retry };
}
