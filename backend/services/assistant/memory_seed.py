"""The 60+ entry learned-memory fixture for the consolidation test (Lab 2 Part 3).

62 entries for one student, written the way memory accumulates over many
sessions: the same 27 facts restated in different words, with:

  * 4 groups of EXACT duplicates (same text; one also differs in case and
    punctuation): code merges these before the model runs
  * many paraphrases of the same fact: the model should merge them
  * 5 deliberate CONTRADICTIONS, where an older fact is replaced by a newer one

A correct consolidation keeps one entry per fact (about 27, well under 40)
and, for each contradiction, only the newer fact. CHECKS below verify that
automatically; scripts/memory_consolidation_report.py prints the result.
"""
import re

E = [  # (fact number, date, category, description)
    # F1 program (exact duplicates)
    (1, "2026-08-03", "education", "Studying for an MS in Applied Data Intelligence at SJSU."),
    (1, "2026-08-03", "education", "Studying for an MS in Applied Data Intelligence at SJSU."),
    (1, "2026-09-14", "education", "Is a master's student in Applied Data Intelligence at San Jose State."),
    # F2 graduation (contradiction C4: May -> December 2027)
    (2, "2026-08-03", "education", "Expects to graduate in May 2027."),
    (2, "2026-08-21", "education", "Planned graduation date is May 2027."),
    (2, "2026-10-20", "education", "Graduation moved to December 2027 after adding a thesis."),
    # F3 location (contradiction C1: Sunnyvale -> Palo Alto)
    (3, "2026-08-03", "location", "Lives in Sunnyvale."),
    (3, "2026-08-25", "location", "Based in Sunnyvale and wants jobs near home."),
    (3, "2026-10-02", "location", "Moved to Palo Alto; now lives there."),
    (3, "2026-10-15", "location", "Current city is Palo Alto."),
    # F4 job type (contradiction C2: internships only -> full-time)
    (4, "2026-08-03", "preference", "Looking for internships only."),
    (4, "2026-08-17", "preference", "Only wants internship roles right now."),
    (4, "2026-09-02", "preference", "Interested in internships, not full-time jobs."),
    (4, "2026-10-12", "preference", "No longer wants internships; now looking for full-time roles."),
    (4, "2026-10-22", "preference", "Wants full-time positions starting after graduation."),
    # F5 remote (contradiction C3: on-site only -> open to remote)
    (5, "2026-08-05", "preference", "Prefers on-site work and does not want remote jobs."),
    (5, "2026-08-30", "preference", "Prefers in-office roles over remote ones."),
    (5, "2026-10-18", "preference", "Is now open to fully remote jobs."),
    # F6 salary (contradiction C5: 70,000 -> 85,000)
    (6, "2026-08-05", "preference", "Minimum acceptable salary is 70,000 dollars."),
    (6, "2026-09-10", "preference", "Will not consider roles paying under 70,000 dollars a year."),
    (6, "2026-10-24", "preference", "Raised minimum salary to 85,000 dollars."),
    # F7 Python (exact duplicates, one with different case and punctuation)
    (7, "2026-08-03", "skill", "Strong in Python."),
    (7, "2026-08-11", "skill", "strong in python"),
    (7, "2026-09-20", "skill", "Uses Python for most data analysis work."),
    # F8 SQL
    (8, "2026-08-03", "skill", "Knows SQL well."),
    (8, "2026-09-05", "skill", "Comfortable writing complex SQL queries."),
    # F9 Tableau
    (9, "2026-08-11", "skill", "Builds dashboards in Tableau."),
    (9, "2026-09-28", "skill", "Has Tableau dashboard experience."),
    # F10 Spark
    (10, "2026-09-01", "goal", "Currently learning Apache Spark."),
    (10, "2026-10-06", "goal", "Is learning Spark for big data processing."),
    # F11 career goal
    (11, "2026-08-03", "goal", "Wants to become a data engineer."),
    (11, "2026-08-27", "goal", "Long-term goal is a data engineering role."),
    (11, "2026-10-09", "goal", "Aims for a career in data engineering."),
    # F12 domain
    (12, "2026-08-14", "preference", "Interested in healthcare analytics."),
    (12, "2026-09-22", "preference", "Would like to work on healthcare data."),
    # F13 not sales (exact duplicates)
    (13, "2026-08-14", "constraint", "Not interested in sales roles."),
    (13, "2026-09-03", "constraint", "Not interested in sales roles."),
    # F14 availability
    (14, "2026-08-19", "availability", "Available about 20 hours a week during the semester."),
    (14, "2026-09-16", "availability", "Can work roughly 20 hours per week while classes are in session."),
    # F15 commute
    (15, "2026-08-19", "constraint", "Needs jobs reachable by Caltrain."),
    (15, "2026-09-29", "constraint", "Commutes by Caltrain, so the office must be near a station."),
    # F16 company size
    (16, "2026-08-22", "preference", "Prefers companies with fewer than 500 employees."),
    (16, "2026-10-01", "preference", "Likes smaller companies, under 500 people."),
    # F17 TA experience
    (17, "2026-08-08", "experience", "Teaching assistant for an introductory statistics course."),
    (17, "2026-09-12", "experience", "Works as a TA for intro statistics."),
    # F18 Kafka project (exact duplicates)
    (18, "2026-09-08", "experience", "Built a Kafka data pipeline for a course project."),
    (18, "2026-09-08", "experience", "Built a Kafka data pipeline for a course project."),
    # F19 resume events
    (19, "2026-08-24", "preference", "Wants to attend resume review events."),
    (19, "2026-09-25", "preference", "Interested in resume workshops and review sessions."),
    # F20 evening events
    (20, "2026-08-24", "availability", "Prefers events in the evening."),
    (20, "2026-09-25", "availability", "Can only attend events after 5 pm."),
    # F21 attended session
    (21, "2026-09-30", "experience", "Attended a Data Analytics information session in Cupertino."),
    # F22 portfolio
    (22, "2026-08-28", "experience", "Keeps a portfolio of projects on GitHub."),
    # F23 MLOps
    (23, "2026-09-07", "goal", "Interested in MLOps."),
    (23, "2026-10-11", "goal", "Wants to learn more about deploying machine learning models (MLOps)."),
    # F24 mentorship
    (24, "2026-09-19", "preference", "Values mentorship programs at employers."),
    # F25 unpaid
    (25, "2026-08-12", "constraint", "Will not take unpaid positions."),
    (25, "2026-09-21", "constraint", "Avoids unpaid internships and roles."),
    # F26 Python over R
    (26, "2026-08-30", "skill", "Prefers Python over R for analysis."),
    (26, "2026-10-04", "skill", "Chooses Python rather than R for analytics work."),
    # F27 Bay Area
    (27, "2026-08-06", "location", "Wants to stay in the Bay Area."),
    (27, "2026-10-16", "location", "Plans to keep working in the San Francisco Bay Area."),
]

DISTINCT_FACTS = 27
EXACT_DUPLICATE_GROUPS = [
    "Studying for an MS in Applied Data Intelligence at SJSU.",
    "Strong in Python.",
    "Not interested in sales roles.",
    "Built a Kafka data pipeline for a course project.",
]

# (name, pattern that must be GONE, pattern that must REMAIN) - case-insensitive
CONTRADICTIONS = [
    ("C1 city: Sunnyvale -> Palo Alto", r"sunnyvale", r"palo alto"),
    ("C2 job type: internships only -> full-time",
     r"internships? only|only wants internship|not full-time", r"full-time"),
    ("C3 remote: on-site only -> open to remote",
     r"does not want remote|in-office roles over remote", r"remote"),
    ("C4 graduation: May 2027 -> December 2027", r"may 2027", r"december 2027"),
    ("C5 minimum salary: 70,000 -> 85,000", r"70,000|70000", r"85,000|85000"),
]


def seed(db, student_id: int) -> int:
    """Replace the student's memory with the fixture; returns the count."""
    from services.common.mongo import STUDENT_MEMORY, utcnow
    db[STUDENT_MEMORY].delete_many({"student_id": student_id})
    now = utcnow()
    db[STUDENT_MEMORY].insert_many([
        {"student_id": student_id, "date": d, "category": c, "description": text,
         "source": "fixture", "fact": fact, "created_at": now} for fact, d, c, text in E])
    return len(E)


def check(after_lines: list[str]) -> list[tuple[str, bool, str]]:
    """Verify a consolidated memory: [(check, passed, detail)]."""
    from services.assistant.consolidation import normalized
    results = [(f"fewer than 40 entries", len(after_lines) < 40, f"{len(after_lines)} entries")]
    descriptions = [line.split(" | ", 2)[-1] for line in after_lines]
    for text in EXACT_DUPLICATE_GROUPS:
        n = sum(normalized(d) == normalized(text) for d in descriptions)
        results.append((f"duplicate merged: {text[:40]}", n <= 1, f"appears {n} time(s)"))
    joined = "\n".join(descriptions).lower()
    for name, gone, remain in CONTRADICTIONS:
        old = re.findall(gone, joined)
        new = re.search(remain, joined)
        results.append((f"resolved {name}", not old and bool(new),
                        f"old fact present: {bool(old)}, new fact present: {bool(new)}"))
    return results
