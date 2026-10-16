export const emptyFilters = { title: "", location: "", category: "", remote: "" };

export function filterJobs(jobs, filters) {
  return jobs.filter((job) =>
    job.title.toLowerCase().includes(filters.title.trim().toLowerCase()) &&
    job.location.toLowerCase().includes(filters.location.trim().toLowerCase()) &&
    (!filters.category || job.category === filters.category) &&
    (!filters.remote || job.is_remote === (filters.remote === "remote"))
  );
}

export function jobSearchPath(filters) {
  const query = new URLSearchParams();
  if (filters.title.trim()) query.set("q", filters.title.trim());
  if (filters.location.trim()) query.set("location", filters.location.trim());
  if (filters.category) query.set("category", filters.category);
  if (filters.remote) query.set("is_remote", String(filters.remote === "remote"));
  const encoded = query.toString();
  return `/jobs/search${encoded ? `?${encoded}` : ""}`;
}

export function companyJobs(jobs, companyId) {
  return jobs.filter((job) => job.company_id === companyId).sort((a, b) => b.id - a.id);
}
