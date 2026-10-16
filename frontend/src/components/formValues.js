export function toForm(data) {
  return { ...data, skills_json: data.skills_json == null ? "" : JSON.stringify(data.skills_json) };
}

export function toPayload(form, fields) {
  return Object.fromEntries(fields.map(([name, label, type]) => {
    let value = form[name] ?? "";
    if (type === "checkbox") value = Boolean(value);
    else if (type === "json") {
      try { value = value.trim() ? JSON.parse(value) : null; }
      catch { throw new Error(`${label}: enter a valid JSON array.`); }
      if (value !== null && !Array.isArray(value)) throw new Error(`${label}: enter a JSON array.`);
    } else if (value === "") value = null;
    else if (type === "year") value = Number(value);
    else if (typeof value === "string") value = value.trim();
    return [name, value];
  }));
}

