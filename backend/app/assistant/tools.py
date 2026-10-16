import json
from datetime import date

from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from app.assistant.confirm import confirm_action
from app.database import SessionLocal
from app.models.additional import Event, SavedItem, StudentPreference
from app.models.core import Company, Job, Student


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
            statement = statement.where(Job.category == category)

        if city:
            statement = statement.where(
                Job.location.ilike(f"%{city}%")
            )

        if salary_min is not None:
            statement = statement.where(Job.salary >= salary_min)

        if skill:
            statement = statement.where(
                cast(Job.skills_json, String).ilike(f"%{skill}%")
            )

        if deadline_before:
            statement = statement.where(
                Job.deadline <= deadline_before
            )

        if remote_only is True:
            statement = statement.where(Job.is_remote.is_(True))

        statement = statement.order_by(Job.deadline.asc())

        rows = db.execute(statement).all()

        if not rows:
            return "No matching jobs were found."

        results = []

        for job, company_record in rows[:20]:
            results.append(
                {
                    "id": job.id,
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

        return _json(results)

    except Exception as error:
        return f"Job search error: {error}"

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
            statement = statement.where(
                Event.event_date >= date_from
            )
        else:
            statement = statement.where(
                Event.event_date >= date.today()
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
    confirmed: bool = False,
) -> str:
    db = SessionLocal()

    try:
        if (job_id is None) == (event_id is None):
            return "Provide exactly one job_id or event_id."

        confirmation_arguments = {
            "student_id": student_id,
            "job_id": job_id,
            "event_id": event_id,
            "confirmed": confirmed,
        }

        if not confirm_action(
            "save_job_or_event",
            confirmation_arguments,
        ):
            item_type = "job" if job_id is not None else "event"
            item_id = job_id if job_id is not None else event_id

            return (
                f"Confirmation required before saving {item_type} "
                f"{item_id}."
            )

        if db.get(Student, student_id) is None:
            return "Student does not exist."

        if job_id is not None:
            if db.get(Job, job_id) is None:
                return "Job does not exist."

            existing = db.scalar(
                select(SavedItem).where(
                    SavedItem.student_id == student_id,
                    SavedItem.job_id == job_id,
                )
            )

            if existing is not None:
                return "This job is already saved."

        if event_id is not None:
            if db.get(Event, event_id) is None:
                return "Event does not exist."

            existing = db.scalar(
                select(SavedItem).where(
                    SavedItem.student_id == student_id,
                    SavedItem.event_id == event_id,
                )
            )

            if existing is not None:
                return "This event is already saved."

        saved_item = SavedItem(
            student_id=student_id,
            job_id=job_id,
            event_id=event_id,
        )

        db.add(saved_item)
        db.commit()
        db.refresh(saved_item)

        return f"Saved successfully. Saved item id is {saved_item.id}."

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
                "Use this first when the student asks for jobs "
                "based on their saved preferences."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "integer",
                        "description": "The current student's ID.",
                    }
                },
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": (
                "Use this to search jobs by title, company, category, "
                "city, salary, skill, deadline, or remote status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "category": {"type": "string"},
                    "city": {"type": "string"},
                    "salary_min": {"type": "number"},
                    "skill": {"type": "string"},
                    "deadline_before": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format.",
                    },
                    "remote_only": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": (
                "Use this when the student requests details about "
                "one specific job."
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
                "Use this to search upcoming events by name, city, "
                "date, or eligibility."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "city": {"type": "string"},
                    "date_from": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format.",
                    },
                    "eligibility": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_job_or_event",
            "description": (
                "Use this only after the student explicitly confirms "
                "saving a job or event."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer"},
                    "job_id": {"type": "integer"},
                    "event_id": {"type": "integer"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["student_id"],
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "get_student_preferences": get_student_preferences,
    "search_jobs": search_jobs,
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