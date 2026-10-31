"""Assistant tools on MongoDB (Lab 2).

Same names, arguments and result strings as Lab 1, so the loop, the
validation rules and the evidence runners are unchanged. Every tool
returns a string in all cases and never raises.
"""
import json
from datetime import date

from services.assistant.agent.confirm import confirm_action
from services.common import repo
from services.common.mongo import (
    COMPANIES, EVENTS, JOBS, PREFERENCES, SAVED_ITEMS, STUDENTS, database, from_mongo)


VALID_CATEGORIES = [
    "full_time",
    "part_time",
    "on_campus",
    "internship",
]


def _json(data) -> str:
    return json.dumps(from_mongo(data), default=str)


def _job_summary(job: dict) -> dict:
    return {
        "job_id": job["_id"],
        "title": job["title"],
        "company": job.get("company_name"),
        "location": job["location"],
        "category": job["category"],
        "salary": job.get("salary"),
        "deadline": job["deadline"],
        "is_remote": job.get("is_remote", False),
        "skills": job.get("skills_json"),
    }


def get_student_preferences(student_id: int) -> str:
    try:
        preference = database()[PREFERENCES].find_one({"_id": student_id})

        if preference is None:
            return "No preferences are saved for this student."

        return _json(
            {
                "student_id": preference["_id"],
                "preferred_city": preference.get("preferred_city"),
                "preferred_category": preference.get("preferred_category"),
                "minimum_salary": preference.get("minimum_salary"),
                "preferred_skills": preference.get("preferred_skills_json"),
                "remote_only": preference.get("remote_only", False),
                "event_preferences": {
                    "preferred_majors": preference.get("preferred_event_majors_json"),
                    "preferred_city": preference.get("preferred_event_city"),
                },
            }
        )

    except Exception as error:
        return f"Preference lookup error: {error}"


def search_jobs(
    title: str | None = None,
    company: str | None = None,
    category: str | None = None,
    city: str | None = None,
    salary_min: float | None = None,
    skill: str | None = None,
    deadline_before: str | None = None,
    remote_only: bool | None = None,
) -> str:
    try:
        query: dict = {}

        if title:
            query["title"] = repo.ci_contains(title)

        if company:
            # Each job carries its company's name, so no join is needed.
            query["company_name"] = repo.ci_contains(company)

        if category:
            if category not in VALID_CATEGORIES:
                return (
                    "Invalid category. Use one of: "
                    "full_time, part_time, on_campus, internship."
                )
            query["category"] = category

        if city:
            query["location"] = repo.ci_contains(city)

        if salary_min is not None:
            query["salary"] = {"$gte": float(salary_min)}

        if skill:
            requested_skills = [
                item.strip() for item in skill.split(",") if item.strip()
            ]
            if requested_skills:
                # Any listed skill may match (Lab 1: OR of text matches).
                query["$or"] = [
                    {"skills_json": repo.ci_contains(s)} for s in requested_skills
                ]

        if deadline_before:
            try:
                parsed_deadline = date.fromisoformat(deadline_before)
            except ValueError:
                return "deadline_before must use YYYY-MM-DD format."
            query["deadline"] = {"$lte": parsed_deadline.isoformat()}

        if remote_only is True:
            query["is_remote"] = True

        jobs = list(
            database()[JOBS].find(query).sort([("deadline", 1), ("_id", 1)]).limit(20)
        )

        if not jobs:
            return "No matching jobs were found."

        results = [_job_summary(job) for job in jobs]

        # Put the real IDs on their own line so the model does not
        # confuse them with numbers inside company names or titles.
        job_ids = [item["job_id"] for item in results]

        return (
            f"JOB_IDS: {job_ids}\n"
            f"JOBS: {_json(results)}"
        )

    except Exception as error:
        return f"Job search error: {error}"


def rank_jobs(
    job_ids: list[int],
    limit: int = 5,
) -> str:
    """
    Sort the given jobs by salary, highest first.

    Values are read from the database and returned unchanged.
    """
    try:
        if not job_ids:
            return "No job IDs were provided."

        unique_ids = []
        for job_id in job_ids:
            if job_id not in unique_ids:
                unique_ids.append(job_id)

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        jobs = [from_mongo(j) for j in database()[JOBS].find({"_id": {"$in": unique_ids}})]

        if not jobs:
            return "No matching jobs were found for those IDs."

        jobs.sort(key=lambda job: (job.get("salary") is None,
                                   -float(job.get("salary") or 0)))

        found_ids = {job["_id"] for job in jobs}
        missing_ids = [job_id for job_id in unique_ids if job_id not in found_ids]

        output = {
            "ranked_by": "salary, highest first",
            "jobs": [_job_summary(job) for job in jobs[:limit]],
        }

        if missing_ids:
            output["not_found_ids"] = missing_ids

        return _json(output)

    except Exception as error:
        return f"Job ranking error: {error}"


def get_job_details(job_id: int) -> str:
    try:
        db = database()
        job = db[JOBS].find_one({"_id": job_id})
        company = job and db[COMPANIES].find_one({"_id": job["company_id"]})

        if job is None or company is None:
            return f"No job exists with id {job_id}."

        return _json(
            {
                "id": job["_id"],
                "title": job["title"],
                "company": {
                    "id": company["_id"],
                    "name": company["company_name"],
                    "location": company.get("location"),
                    "description": company.get("description"),
                    "contact_phone": company.get("contact_phone"),
                },
                "job": {
                    "location": job["location"],
                    "category": job["category"],
                    "salary": job.get("salary"),
                    "description": job["description"],
                    "deadline": job["deadline"],
                    "posting_date": job["posting_date"],
                    "is_remote": job.get("is_remote", False),
                    "skills": job.get("skills_json"),
                },
            }
        )

    except Exception as error:
        return f"Job detail error: {error}"


def search_events(
    name: str | None = None,
    city: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    eligibility: str | None = None,
    major: str | None = None,
) -> str:
    try:
        if major is not None:
            if not isinstance(major, str) or len(major.strip()) > 100:
                return "major must be text of at most 100 characters."
            major = major.strip()

        query: dict = {}
        date_range: dict = {}

        if name:
            query["event_name"] = repo.ci_contains(name)

        if city:
            query["location"] = repo.ci_contains(city)

        if date_from:
            try:
                date_range["$gte"] = date.fromisoformat(date_from).isoformat()
            except ValueError:
                return "date_from must use YYYY-MM-DD format."
        else:
            date_range["$gte"] = date.today().isoformat()

        if date_to:
            try:
                date_range["$lte"] = date.fromisoformat(date_to).isoformat()
            except ValueError:
                return "date_to must use YYYY-MM-DD format."

        query["event_date"] = date_range

        # Eligibility is {description, majors, colleges}; a text filter
        # matches any of them, and major matches the description or the
        # listed majors.
        conditions = []
        for text in (eligibility, major):
            if text:
                term = repo.ci_contains(text)
                conditions.append({"$or": [
                    {"eligibility.description": term},
                    {"eligibility.majors": term},
                    {"eligibility.colleges": term},
                ]})
        if conditions:
            query["$and"] = conditions

        events = list(
            database()[EVENTS].find(query).sort([("event_date", 1), ("_id", 1)]).limit(20)
        )

        if not events:
            return "No matching upcoming events were found."

        return _json(
            [
                {
                    "id": event["_id"],
                    "event_name": event["event_name"],
                    "description": event["description"],
                    "event_date": event["event_date"],
                    "event_time": event["event_time"],
                    "location": event["location"],
                    "eligibility": repo.event_rules(event),
                }
                for event in events
            ]
        )

    except Exception as error:
        return f"Event search error: {error}"


def save_job_or_event(
    student_id: int,
    job_id: int | None = None,
    event_id: int | None = None,
    auto_approve: bool = False,
) -> str:
    """
    Save a job or event for the student, gated by confirm_action.

    auto_approve is set only by the application after the student
    clicks Yes. The model cannot set it; the loop removes it from
    model arguments.
    """
    try:
        if (job_id is None) == (event_id is None):
            return "Provide exactly one job_id or event_id."

        db = database()

        if db[STUDENTS].find_one({"_id": student_id}, {"_id": 1}) is None:
            return "Student does not exist."

        if job_id is not None:
            item_type, item_id = "job", job_id
            job = db[JOBS].find_one({"_id": job_id})
            if job is None:
                return f"No job exists with id {job_id}."
            label = f"Save job {job['_id']}: {job['title']} at {job.get('company_name')}?"
            existing = db[SAVED_ITEMS].find_one({"student_id": student_id, "job_id": job_id})
        else:
            item_type, item_id = "event", event_id
            event = db[EVENTS].find_one({"_id": event_id})
            if event is None:
                return f"No event exists with id {event_id}."
            label = f"Save event {event['_id']}: {event['event_name']} on {event['event_date']}?"
            existing = db[SAVED_ITEMS].find_one({"student_id": student_id, "event_id": event_id})

        if existing is not None:
            return f"This {item_type} is already saved."

        decision = confirm_action(
            "save_job_or_event",
            {"student_id": student_id, "job_id": job_id, "event_id": event_id},
            auto_approve=auto_approve,
        )

        if decision == "pending":
            return _json(
                {
                    "status": "pending_confirmation",
                    "item_type": item_type,
                    "item_id": item_id,
                    "label": label,
                }
            )

        if decision != "approved":
            return f"Cancelled: the student declined to save {item_type} {item_id}."

        saved_item, _ = repo.save_item(db, student_id=student_id, job_id=job_id,
                                       event_id=event_id)

        return (
            f"Saved successfully: {item_type} {item_id}. "
            f"Saved item id is {saved_item['id']}."
        )

    except repo.DomainError as error:
        return f"Save error: {error.message}"
    except Exception as error:
        return f"Save error: {error}"


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_student_preferences",
            "description": (
                "Return the signed-in student's saved job and event "
                "preferences. Use this first when the student says "
                "'my city', 'my preferences', or similar. The student "
                "ID is supplied automatically; never ask for it."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": (
                "Search jobs by title, company, category, city, "
                "salary, skills, deadline, or remote status. When the "
                "student describes a field of work or study instead of "
                "an exact job title, put the technical skills used in "
                "that field in skill and leave title empty."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "Words that appear in the job title. Use only "
                            "when the student gives an actual job title."
                        ),
                    },
                    "company": {
                        "type": "string",
                        "description": "Words in the company name.",
                    },
                    "category": {
                        "type": "string",
                        "enum": VALID_CATEGORIES,
                        "description": "The job category.",
                    },
                    "city": {
                        "type": "string",
                        "description": "The job city.",
                    },
                    "salary_min": {
                        "type": "number",
                        "description": "Minimum annual salary.",
                    },
                    "skill": {
                        "type": "string",
                        "description": (
                            "Technical skills, comma-separated. A job "
                            "matches if it lists any of them. For a field "
                            "of work, list the skills that field uses "
                            "(for example, web development: React, "
                            "JavaScript)."
                        ),
                    },
                    "deadline_before": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format.",
                    },
                    "remote_only": {
                        "type": "boolean",
                        "description": "Return only remote jobs.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_jobs",
            "description": (
                "Sort jobs from an earlier search_jobs result by "
                "salary, highest first. Use this for follow-ups such as "
                "'higher-paying' or 'rank those'. Copy job IDs exactly "
                "from the most recent search_jobs result; never guess "
                "IDs. Returns exact database values."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_ids": {
                        "type": "array",
                        "items": {
                            "type": "integer",
                        },
                        "description": (
                            "Values copied from the JOB_IDS line of the "
                            "most recent search_jobs result. Numbers in "
                            "company names or titles are not job IDs."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            "Maximum number of jobs to return."
                        ),
                    },
                },
                "required": ["job_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": (
                "Use this when the student requests details "
                "about one specific job."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "integer",
                        "description": "The job ID.",
                    }
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": (
                "Search upcoming events by name, city, date range, "
                "student eligibility, or major."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Words in the event name.",
                    },
                    "city": {
                        "type": "string",
                        "description": "The event city.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": (
                            "First date to include, "
                            "in YYYY-MM-DD format."
                        ),
                    },
                    "date_to": {
                        "type": "string",
                        "description": (
                            "Last date to include, "
                            "in YYYY-MM-DD format."
                        ),
                    },
                    "eligibility": {
                        "type": "string",
                        "description": "Required student eligibility.",
                    },
                    "major": {
                        "type": "string",
                        "description": (
                            "Academic major the event is open to, for "
                            "example \"History\". Matches events whose "
                            "eligibility names that major."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_job_or_event",
            "description": (
                "Save one job or one event for the signed-in student "
                "when they ask to save it. Provide exactly one of "
                "job_id or event_id, copied from earlier tool results. "
                "The application asks the student to confirm before "
                "anything is saved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "integer",
                        "description": "The job ID to save.",
                    },
                    "event_id": {
                        "type": "integer",
                        "description": "The event ID to save.",
                    },
                },
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "get_student_preferences": get_student_preferences,
    "search_jobs": search_jobs,
    "rank_jobs": rank_jobs,
    "get_job_details": get_job_details,
    "search_events": search_events,
    "save_job_or_event": save_job_or_event,
}


def execute_tool(tool_name: str, arguments: dict) -> str:
    try:
        function = TOOL_FUNCTIONS.get(tool_name)

        if function is None:
            return f"Unknown tool: {tool_name}"

        return str(function(**arguments))

    except Exception as error:
        return f"Tool execution error: {error}"