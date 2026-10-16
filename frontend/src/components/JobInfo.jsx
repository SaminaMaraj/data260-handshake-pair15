export default function JobInfo({ job }) {
  return <dl className="job-info">
    <dt>Company ID</dt><dd>{job.company_id}</dd>
    <dt>Location</dt><dd>{job.location}</dd>
    <dt>Category</dt><dd>{job.category.replaceAll("_", " ")}</dd>
    <dt>Work arrangement</dt><dd>{job.is_remote ? "Remote" : "Onsite"}</dd>
    <dt>Posting date</dt><dd>{job.posting_date}</dd>
    <dt>Deadline</dt><dd>{job.deadline}</dd>
    <dt>Salary</dt><dd>{job.salary ?? "Not specified"}</dd>
  </dl>;
}
