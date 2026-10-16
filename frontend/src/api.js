const API_URL = "http://127.0.0.1:9150";

export async function apiRequest(path, { token, onUnauthorized, body, ...options } = {}) {
  const multipart = body instanceof FormData;
  let response;

  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        ...(body !== undefined && !multipart ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: multipart ? body : JSON.stringify(body) } : {}),
    });
  } catch {
    throw new Error("Could not connect to the backend. Please try again.");
  }

  if (response.status === 401) onUnauthorized?.();

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc.slice(1).join(".")}: ${item.msg}`).join("; ")
      : data.detail;

    const error = new Error(detail || "Request failed. Please try again.");
    error.status = response.status;
    throw error;
  }

  return data;
}

export async function apiFile(path, { token, onUnauthorized } = {}) {
  let response;
  try { response = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${token}` } }); }
  catch { throw new Error("Could not connect to the backend."); }
  if (response.status === 401) onUnauthorized?.();
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Could not load file.");
  }
  return response.blob();
}
