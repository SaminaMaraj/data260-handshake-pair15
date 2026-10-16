USE handshake_pair15;

CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    role ENUM('student', 'company') NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE students (
    user_id BIGINT UNSIGNED PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    college_name VARCHAR(255),
    career_objective TEXT,
    date_of_birth DATE,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    degree VARCHAR(150),
    major VARCHAR(150),
    graduation_year YEAR,
    cgpa DECIMAL(4,2),
    education TEXT,
    experience TEXT,
    phone VARCHAR(30),
    profile_picture_url VARCHAR(500),
    skills_json JSON,
    CONSTRAINT fk_students_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE companies (
    user_id BIGINT UNSIGNED PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    description TEXT,
    contact_phone VARCHAR(30),
    profile_picture_url VARCHAR(500),
    CONSTRAINT fk_companies_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    posting_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    deadline DATE NOT NULL,
    location VARCHAR(255) NOT NULL,
    salary DECIMAL(12,2),
    description TEXT NOT NULL,
    category ENUM('full_time', 'part_time', 'on_campus', 'internship') NOT NULL,
    is_remote BOOLEAN NOT NULL DEFAULT FALSE,
    skills_json JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_jobs_company
        FOREIGN KEY (company_id) REFERENCES companies(user_id)
        ON DELETE CASCADE,
    INDEX idx_jobs_title (title),
    INDEX idx_jobs_location (location),
    INDEX idx_jobs_category (category),
    INDEX idx_jobs_deadline (deadline)
);

CREATE TABLE resumes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    student_id BIGINT UNSIGNED NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_resumes_student
        FOREIGN KEY (student_id) REFERENCES students(user_id)
        ON DELETE CASCADE
);

CREATE TABLE applications (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NOT NULL,
    resume_id BIGINT UNSIGNED NOT NULL,
    status ENUM('pending', 'reviewed', 'declined') NOT NULL DEFAULT 'pending',
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL,
    CONSTRAINT uq_student_job_application
        UNIQUE (job_id, student_id),
    CONSTRAINT fk_applications_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_applications_student
        FOREIGN KEY (student_id) REFERENCES students(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_applications_resume
        FOREIGN KEY (resume_id) REFERENCES resumes(id)
        ON DELETE RESTRICT,
    INDEX idx_applications_status (status)
);

CREATE TABLE events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    event_date DATE NOT NULL,
    event_time TIME NOT NULL,
    location VARCHAR(255) NOT NULL,
    eligibility TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_events_company
        FOREIGN KEY (company_id) REFERENCES companies(user_id)
        ON DELETE CASCADE,
    INDEX idx_events_name (event_name),
    INDEX idx_events_date (event_date)
);

CREATE TABLE event_registrations (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NOT NULL,
    registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_event_student
        UNIQUE (event_id, student_id),
    CONSTRAINT fk_registrations_event
        FOREIGN KEY (event_id) REFERENCES events(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_registrations_student
        FOREIGN KEY (student_id) REFERENCES students(user_id)
        ON DELETE CASCADE
);

CREATE TABLE student_preferences (
    student_id BIGINT UNSIGNED PRIMARY KEY,
    preferred_city VARCHAR(100),
    preferred_category ENUM(
        'full_time',
        'part_time',
        'on_campus',
        'internship'
    ),
    minimum_salary DECIMAL(12,2),
    preferred_skills_json JSON,
    remote_only BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_preferences_student
        FOREIGN KEY (student_id) REFERENCES students(user_id)
        ON DELETE CASCADE
);

CREATE TABLE saved_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    student_id BIGINT UNSIGNED NOT NULL,
    job_id BIGINT UNSIGNED NULL,
    event_id BIGINT UNSIGNED NULL,
    saved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_saved_student
        FOREIGN KEY (student_id) REFERENCES students(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_saved_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_saved_event
        FOREIGN KEY (event_id) REFERENCES events(id)
        ON DELETE CASCADE,
    CONSTRAINT chk_saved_item_type
        CHECK (
            (job_id IS NOT NULL AND event_id IS NULL)
            OR
            (job_id IS NULL AND event_id IS NOT NULL)
        )
);
