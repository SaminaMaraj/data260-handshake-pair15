# METRICS.md

## Pair configuration

| Parameter | Value |
|---|---|
| Pair | 15 |
| Port base | 9150 |
| Database prefix | p15 |
| Seed | 15 |
| Cities | Sunnyvale, Cupertino, Palo Alto |
| Database | handshake_pair15 |

## Seed data counts

| Entity | Count |
|---|---:|
| Students | 200 |
| Companies | 50 |
| Jobs | 300 |
| Applications | 1,500 |
| Events | 100 |
| Resumes | 200 |
| Student preferences | 200 |

## Backend verification

| Feature | Result |
|---|---|
| Database health endpoint | Passed |
| User registration | Passed |
| User login | Passed |
| Student profiles | Passed |
| Company profiles | Passed |
| Job creation and retrieval | Passed |
| Job search and filtering | Passed |
| Event search and filtering | Passed |
| Event registration | Passed |
| Resume upload | Passed |
| Job application creation | Passed |
| Application status update | Passed |
| Student preferences | Passed |
| Saved jobs/events | Passed |

## Assistant verification

| Test | Result |
|---|---|
| Internship in the student's city | Passed |
| Remote data-science internship | Passed |
| Computer-science event next month | Passed |
| Higher-paying follow-up | Passed |
| Missing company/category no-match response | Passed |

## Assistant loop measurements

| Metric | Result |
|---|---:|
| Maximum loop iterations | 6 |
| Tool calls in preference-based search | 2 |
| Tool calls in remote internship search | 1 |
| Tool calls in event search | 1 |
| Tool calls in higher-paying follow-up | 0 |
| Tool calls in no-match search | 1 |

## Reliability notes

The assistant was tested through the five required scenarios. Several incorrect tool arguments were detected and corrected:

- Incorrect student ID
- Incorrect city and salary preference
- Invalid job category
- Incorrect event date

The assistant returned no-match responses instead of inventing database records.

A separate 20-turn reliability measurement covering malformed arguments, unknown tools, text responses when tools were required, and lost multi-step chains remains to be completed if required by the final grading checklist.