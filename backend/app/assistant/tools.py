import json
from datetime import date

from sqlalchemy import String, cast, or_, select

from app.assistant.confirm import confirm_action
from app.database import SessionLocal
from app.models.additional import Event, SavedItem, StudentPreference
from app.models.core import Company, Job, Student


VALID_CATEGORIES = [
    "full_time",
    "part_time",
    "on_campus",
    "internship",
]


def _json(data) -> str:
    return json.dumps(data, default=str)


def get_student_preferences(student_id: int) -> str:
    db = SessionLocal()

    try:
        preference = db.get(StudentPreference, student_id)

        if preference is None:
            return "No preferences are saved for this student."

        return _json(
            {
                "student_id": preference.student_id,
                "preferred_city": preference.preferred_city,
                "preferred_category": preference.preferred_category,
                "minimum_salary": preference.minimum_salary,
                "preferred_skills": preference.preferred_skills_json,
                "remote_only": preference.remote_only,
            }
        )

    except Exception as error:
        return f"Preference lookup error: {error}"

    finally:
        db.close()


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
    db = SessionLocal()

    try:
        statement = (
            select(Job, Company)
            .join(Company, Job.company_id == Company.user_id)
        )

        if title:
            statement = statement.where(
                Job.title.ilike(f"%{title}%")
            )

        if company:
            statement = statement.where(
                Company.company_name.ilike(f"%{company}%")
            )

        if category:
            if category not in VALID_CATEGORIES:
                return (
                    "Invalid category. Use one of: "
                    "full_time, part_time, on_campus, internship."
                )

            statement = statement.where(Job.category == category)

        if city:
            statement = statement.where(
                Job.location.ilike(f"%{city}%")
            )

        if salary_min is not None:
            statement = statement.where(Job.salary >= salary_min)

        if skill:
            requested_skills = [
                item.strip()
                for item in skill.split(",")
                if item.strip()
            ]

            skill_filters = [
                cast(Job.skills_json, String).ilike(
                    f"%{requested_skill}%"
                )
                for requested_skill in requested_skills
            ]

            if skill_filters:
                statement = statement.where(or_(*skill_filters))

        if deadline_before:
            try:
                parsed_deadline = date.fromisoformat(deadline_before)
            except ValueError:
                return "deadline_before must use YYYY-MM-DD format."

            statement = statement.where(
                Job.deadline <= parsed_deadline
            )

        if remote_only is True:
            statement = statement.where(
                Job.is_remote.is_(True)
            )

        statement = statement.order_by(Job.deadline.asc())

        rows = db.execute(statement).all()

        if not rows:
            return "No matching jobs were found."

        results = []

        for job, company_record in rows[:20]:
            results.append(
                {
                    "job_id": job.id,
                    "title": job.title,
                    "company": company_record.company_name,
                    "location": job.location,
                    "category": job.category,
                    "salary": job.salary,
                    "deadline": job.deadline,
                    "is_remote": job.is_remote,
                    "skills": job.skills_json,
                }
            )

        # Put the real IDs on their own line so the model does not
        # confuse them with numbers inside company names or titles.
        job_ids = [item["job_id"] for item in results]

        return (
            f"JOB_IDS: {job_ids}\n"
            f"JOBS: {_json(results)}"
        )

    except Exception as error:
        return f"Job search error: {error}"

    finally:
        db.close()


def rank_jobs(
    job_ids: list[int],
    limit: int = 5,
) -> str:
    """
    Sort the given jobs by salary, highest first.

    Values are read from the database and returned unchanged.
    """
    db = SessionLocal()

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

        rows = db.execute(
            select(Job, Company)
            .join(Company, Job.company_id == Company.user_id)
            .where(Job.id.in_(unique_ids))
        ).all()

        if not rows:
            return "No matching jobs were found for those IDs."

        rows = sorted(
            rows,
            key=lambda row: (
                row[0].salary is None,
                -float(row[0].salary or 0),
            ),
        )

        results = [
            {
                "job_id": job.id,
                "title": job.title,
                "company": company_record.company_name,
                "location": job.location,
                "category": job.category,
                "salary": job.salary,
                "deadline": job.deadline,
                "is_remote": job.is_remote,
                "skills": job.skills_json,
            }
            for job, company_record in rows[:limit]
        ]

        found_ids = {job.id for job, _ in rows}
        missing_ids = [
            job_id for job_id in unique_ids if job_id not in found_ids
        ]

        output = {
            "ranked_by": "salary, highest first",
            "jobs": results,
        }

        if missing_ids:
            output["not_found_ids"] = missing_ids

        return _json(output)

    except Exception as error:
        return f"Job ranking error: {error}"

    finally:
        db.close()


def get_job_details(job_id: int) -> str:
    db = SessionLocal()

    try:
        row = db.execute(
            select(Job, Company)
            .join(Company, Job.company_id == Company.user_id)
            .where(Job.id == job_id)
        ).first()

        if row is None:
            return f"No job exists with id {job_id}."

        job, company = row

        return _json(
            {
                "id": job.id,
                "title": job.title,
                "company": {
                    "id": company.user_id,
                    "name": company.company_name,
                    "location": company.location,
                    "description": company.description,
                    "contact_phone": company.contact_phone,
                },
                "job": {
                    "location": job.location,
                    "category": job.category,
                    "salary": job.salary,
                    "description": job.description,
                    "deadline": job.deadline,
                    "posting_date": job.posting_date,
                    "is_remote": job.is_remote,
                    "skills": job.skills_json,
                },
            }
        )

    except Exception as error:
        return f"Job detail error: {error}"

    finally:
        db.close()


def search_events(
    name: str | None = None,
    city: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    eligibility: str | None = None,
) -> str:
    db = SessionLocal()

    try:
        statement = select(Event)

        if name:
            statement = statement.where(
                Event.event_name.ilike(f"%{name}%")
            )

        if city:
            statement = statement.where(
                Event.location.ilike(f"%{city}%")
            )

        if date_from:
            try:
                parsed_date_from = date.fromisoformat(date_from)
            except ValueError:
                return "date_from must use YYYY-MM-DD format."

            statement = statement.where(
                Event.event_date >= parsed_date_from
            )
        else:
            statement = statement.where(
                Event.event_date >= date.today()
            )

        if date_to:
            try:
                parsed_date_to = date.fromisoformat(date_to)
            except ValueError:
                return "date_to must use YYYY-MM-DD format."

            statement = statement.where(
                Event.event_date <= parsed_date_to
            )

        if eligibility:
            statement = statement.where(
                Event.eligibility.ilike(f"%{eligibility}%")
            )

        statement = statement.order_by(Event.event_date.asc())

        events = db.scalars(statement).all()

        if not events:
            return "No matching upcoming events were found."

        return _json(
            [
                {
                    "id": event.id,
                    "event_name": event.event_name,
                    "description": event.description,
                    "event_date": event.event_date,
                    "event_time": event.event_time,
                    "location": event.location,
                    "eligibility": event.eligibility,
                }
                for event in events[:20]
            ]
        )

    except Exception as error:
        return f"Event search error: {error}"

    finally:
        db.close()


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
    db = SessionLocal()

    try:
        if (job_id is None) == (event_id is None):
            return "Provide exactly one job_id or event_id."

        if db.get(Student, student_id) is None:
            return "Student does not exist."

        if job_id is not None:
            item_type = "job"
            item_id = job_id
            row = db.execute(
                select(Job, Company)
                .join(Company, Job.company_id == Company.user_id)
                .where(Job.id == job_id)
            ).first()

            if row is None:
                return f"No job exists with id {job_id}."

            job, company = row
            label = (
                f"Save job {job.id}: {job.title} at "
                f"{company.company_name}?"
            )

            existing = db.scalar(
                select(SavedItem).where(
                    SavedItem.student_id == student_id,
                    SavedItem.job_id == job_id,
                )
            )

        else:
            item_type = "event"
            item_id = event_id
            event = db.get(Event, event_id)

            if event is None:
                return f"No event exists with id {event_id}."

            label = (
                f"Save event {event.id}: {event.event_name} on "
                f"{event.event_date}?"
            )

            existing = db.scalar(
                select(SavedItem).where(
                    SavedItem.student_id == student_id,
                    SavedItem.event_id == event_id,
                )
            )

        if existing is not None:
            return f"This {item_type} is already saved."

        decision = confirm_action(
            "save_job_or_event",
            {
                "student_id": student_id,
                "job_id": job_id,
                "event_id": event_id,
            },
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
            return (
                f"Cancelled: the student declined to save "
                f"{item_type} {item_id}."
            )

        saved_item = SavedItem(
            student_id=student_id,
            job_id=job_id,
            event_id=event_id,
        )

        db.add(saved_item)
        db.commit()
        db.refresh(saved_item)

        return (
            f"Saved successfully: {item_type} {item_id}. "
            f"Saved item id is {saved_item.id}."
        )

    except Exception as error:
        db.rollback()
        return f"Save error: {error}"

    finally:
        db.close()


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
                "salary, skills, deadline, or remote status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Words in the job title.",
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
                            "One skill or comma-separated skills."
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
                "or student eligibility."
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