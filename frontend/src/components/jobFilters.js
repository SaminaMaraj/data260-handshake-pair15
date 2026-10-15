export const emptyFilters = { title: "", location: "", category: "", remote: "" };

export function filterJobs(jobs, filters) {
  return jobs.filter((job) =>
    job.title.toLowerCase().includes(filters.title.trim().toLowerCase()) &&
    job.location.toLowerCase().includes(filters.location.trim().toLowerCase()) &&
    (!filters.category || job.category === filters.category) &&
    (!filters.remote || job.is_remote === (filters.remote === "remote"))
  );
}
