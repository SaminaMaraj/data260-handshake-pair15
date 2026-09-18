# Lab 1 Database Schema

## Configuration

- Pair: 15
- Database: handshake_pair15
- Database prefix: p15
- Application port: 9150
- Random seed: 15
- City set: To be confirmed from Canvas

## Tables

### users

Stores login credentials and the user's role.

- Primary key: `id`
- Important fields: `email`, `password_hash`, `role`

### students

Stores student profile information.

- Primary key and foreign key: `user_id`
- References: `users.id`

### companies

Stores company profile information.

- Primary key and foreign key: `user_id`
- References: `users.id`

### jobs

Stores company job postings.

- Primary key: `id`
- Foreign key: `company_id`
- References: `companies.user_id`

### resumes

Stores uploaded student resume file information.

- Primary key: `id`
- Foreign key: `student_id`
- References: `students.user_id`

### applications

Connects students with jobs.

- Primary key: `id`
- Foreign keys: `job_id`, `student_id`, and `resume_id`
- A student cannot apply to the same job more than once.

### events

Stores company events.

- Primary key: `id`
- Foreign key: `company_id`
- References: `companies.user_id`

### event_registrations

Connects students with events.

- Primary key: `id`
- Foreign keys: `event_id` and `student_id`
- A student cannot register for the same event more than once.

### student_preferences

Stores job and event preferences for each student.

- Primary key and foreign key: `student_id`
- References: `students.user_id`

### saved_items

Stores jobs or events saved by students.

- Primary key: `id`
- Foreign keys: `student_id`, `job_id`, and `event_id`
- Each saved item must refer to either a job or an event.

## Main Relationships

```text
users
├── students
└── companies

companies ───< jobs
students ───< applications >─── jobs
students ───< resumes
companies ───< events
students ───< event_registrations >─── events
students ─── student_preferences
students ───< saved_items
