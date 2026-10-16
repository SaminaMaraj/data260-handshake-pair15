import random
from datetime import date, datetime, time, timedelta

from passlib.context import CryptContext
from sqlalchemy import select

from app.database import SessionLocal
from app.models.additional import (
    Application,
    Event,
    Resume,
    StudentPreference,
)
from app.models.core import Company, Job, Student, User


SEED = 15
CITIES = ["Sunnyvale", "Cupertino", "Palo Alto"]
CATEGORIES = ["full_time", "part_time", "on_campus", "internship"]

random_generator = random.Random(SEED)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def make_seed_data():
    db = SessionLocal()

    try:
        print("Starting Pair 15 seed generation...")

        # Reuse one password hash for generated accounts.
        seed_password_hash = pwd_context.hash("Pair15SeedPassword!")

        # ------------------------------------------------------------
        # 1. Create student users and student profiles
        # ------------------------------------------------------------
        students = db.scalars(select(Student)).all()
        student_users = db.scalars(
            select(User).where(User.role == "student")
        ).all()

        student_user_by_email = {
            user.email: user for user in student_users
        }

        student_number = len(students) + 1

        while len(students) < 200:
            email = f"p15.student.{student_number:04d}@example.com"

            if email not in student_user_by_email:
                user = User(
                    email=email,
                    password_hash=seed_password_hash,
                    role="student",
                    is_active=True,
                )
                db.add(user)
                db.flush()

                student = Student(
                    user_id=user.id,
                    full_name=f"Pair 15 Student {student_number:04d}",
                    college_name="San Jose State University",
                    career_objective="Seeking a data and technology opportunity.",
                    city=random_generator.choice(CITIES),
                    state="California",
                    country="USA",
                    degree="MS",
                    major=random_generator.choice(
                        [
                            "Data Analytics",
                            "Computer Science",
                            "Information Systems",
                        ]
                    ),
                    graduation_year=random_generator.choice([2026, 2027, 2028]),
                    cgpa=round(
                        random_generator.uniform(3.0, 4.0),
                        2,
                    ),
                    experience="Coursework and project experience.",
                    phone=f"408-555-{student_number:04d}",
                    skills_json=random_generator.sample(
                        [
                            "Python",
                            "SQL",
                            "React",
                            "FastAPI",
                            "MySQL",
                            "Statistics",
                            "Machine Learning",
                        ],
                        k=3,
                    ),
                )

                db.add(student)
                students.append(student)
                student_user_by_email[email] = user

            student_number += 1

        db.commit()
        students = db.scalars(select(Student)).all()

        # ------------------------------------------------------------
        # 2. Create company users and company profiles
        # ------------------------------------------------------------
        companies = db.scalars(select(Company)).all()
        company_users = db.scalars(
            select(User).where(User.role == "company")
        ).all()

        company_user_by_email = {
            user.email: user for user in company_users
        }

        company_number = len(companies) + 1

        while len(companies) < 50:
            email = f"p15.company.{company_number:04d}@example.com"

            if email not in company_user_by_email:
                user = User(
                    email=email,
                    password_hash=seed_password_hash,
                    role="company",
                    is_active=True,
                )
                db.add(user)
                db.flush()

                company = Company(
                    user_id=user.id,
                    company_name=f"Pair 15 Company {company_number:04d}",
                    location=random_generator.choice(CITIES),
                    description=(
                        "A seeded Pair 15 company offering "
                        "career opportunities."
                    ),
                    contact_phone=f"650-555-{company_number:04d}",
                )

                db.add(company)
                companies.append(company)
                company_user_by_email[email] = user

            company_number += 1

        db.commit()
        companies = db.scalars(select(Company)).all()

        # ------------------------------------------------------------
        # 3. Create one seed resume for students that do not have one
        # ------------------------------------------------------------
        existing_resumes = db.scalars(select(Resume)).all()
        resume_by_student = {}

        for resume in existing_resumes:
            resume_by_student.setdefault(resume.student_id, resume)

        for student in students:
            if student.user_id not in resume_by_student:
                resume = Resume(
                    student_id=student.user_id,
                    original_filename=(
                        f"p15_resume_{student.user_id}.pdf"
                    ),
                    stored_filename=(
                        f"p15_resume_{student.user_id}.pdf"
                    ),
                    file_path=(
                        f"backend/uploads/"
                        f"p15_resume_{student.user_id}.pdf"
                    ),
                )
                db.add(resume)
                db.flush()
                resume_by_student[student.user_id] = resume

        db.commit()

        # ------------------------------------------------------------
        # 4. Create jobs until the database has at least 300 jobs
        # ------------------------------------------------------------
        jobs = db.scalars(select(Job)).all()
        today = date.today()
        job_number = len(jobs) + 1

        while len(jobs) < 300:
            company = random_generator.choice(companies)
            category = random_generator.choice(CATEGORIES)

            job = Job(
                company_id=company.user_id,
                title=random_generator.choice(
                    [
                        "Data Analyst",
                        "Software Engineer",
                        "Business Analyst",
                        "Machine Learning Intern",
                        "Research Assistant",
                        "Product Analyst",
                    ]
                ),
                posting_date=today - timedelta(
                    days=random_generator.randint(0, 90)
                ),
                deadline=today + timedelta(
                    days=random_generator.randint(15, 120)
                ),
                location=random_generator.choice(CITIES),
                salary=round(
                    random_generator.uniform(45000, 145000),
                    2,
                ),
                description=(
                    f"Seeded Pair 15 {category} opportunity "
                    f"number {job_number}."
                ),
                category=category,
                is_remote=random_generator.choice([True, False]),
                skills_json=random_generator.sample(
                    [
                        "Python",
                        "SQL",
                        "React",
                        "FastAPI",
                        "MySQL",
                        "Statistics",
                        "Machine Learning",
                    ],
                    k=3,
                ),
            )

            db.add(job)
            jobs.append(job)
            job_number += 1

        db.commit()
        jobs = db.scalars(select(Job)).all()

        # ------------------------------------------------------------
        # 5. Create preferences for students that do not have any
        # ------------------------------------------------------------
        existing_preferences = db.scalars(
            select(StudentPreference)
        ).all()

        preference_student_ids = {
            preference.student_id
            for preference in existing_preferences
        }

        for student in students:
            if student.user_id not in preference_student_ids:
                preference = StudentPreference(
                    student_id=student.user_id,
                    preferred_city=random_generator.choice(CITIES),
                    preferred_category=random_generator.choice(
                        CATEGORIES
                    ),
                    minimum_salary=60000,
                    preferred_skills_json=["Python", "SQL"],
                    remote_only=False,
                )
                db.add(preference)

        db.commit()

        # ------------------------------------------------------------
        # 6. Create applications until there are at least 1,500
        # ------------------------------------------------------------
        applications = db.scalars(select(Application)).all()

        existing_pairs = {
            (application.job_id, application.student_id)
            for application in applications
        }

        while len(applications) < 1500:
            job = random_generator.choice(jobs)
            student = random_generator.choice(students)
            pair = (job.id, student.user_id)

            if pair in existing_pairs:
                continue

            status = random_generator.choice(
                ["pending", "pending", "reviewed", "declined"]
            )

            application = Application(
                job_id=job.id,
                student_id=student.user_id,
                resume_id=resume_by_student[student.user_id].id,
                status=status,
                reviewed_at=(
                    datetime.utcnow()
                    if status != "pending"
                    else None
                ),
            )

            db.add(application)
            applications.append(application)
            existing_pairs.add(pair)

        db.commit()

        # ------------------------------------------------------------
        # 7. Create events until there are at least 100
        # ------------------------------------------------------------
        events = db.scalars(select(Event)).all()
        event_number = len(events) + 1

        while len(events) < 100:
            company = random_generator.choice(companies)

            event = Event(
                company_id=company.user_id,
                event_name=random_generator.choice(
                    [
                        "Career Workshop",
                        "Technology Networking Event",
                        "Data Analytics Information Session",
                        "Resume Review Event",
                        "Employer Information Session",
                    ]
                )
                + f" {event_number}",
                description=(
                    "A Pair 15 career and recruiting event "
                    "for students."
                ),
                event_date=today + timedelta(
                    days=random_generator.randint(1, 120)
                ),
                event_time=time(
                    hour=random_generator.choice([10, 12, 14, 16])
                ),
                location=random_generator.choice(CITIES),
                eligibility=random_generator.choice(
                    [
                        "Data Analytics students",
                        "Computer Science students",
                        "All enrolled students",
                    ]
                ),
            )

            db.add(event)
            events.append(event)
            event_number += 1

        db.commit()

        # ------------------------------------------------------------
        # Final counts
        # ------------------------------------------------------------
        print("Seed generation completed.")
        print(f"Students: {db.query(Student).count()}")
        print(f"Companies: {db.query(Company).count()}")
        print(f"Jobs: {db.query(Job).count()}")
        print(f"Applications: {db.query(Application).count()}")
        print(f"Events: {db.query(Event).count()}")
        print(f"Resumes: {db.query(Resume).count()}")
        print(
            "Student preferences: "
            f"{db.query(StudentPreference).count()}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    make_seed_data()