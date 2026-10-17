-- MySQL schema for the Flask/SQLAlchemy application.
-- Create or select a local database, then run this script in that database.

CREATE DATABASE IF NOT EXISTS campus_skill_exchange
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE campus_skill_exchange;

CREATE TABLE IF NOT EXISTS `user` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    college VARCHAR(150) NOT NULL,
    department VARCHAR(100) NOT NULL,
    semester INT NOT NULL,
    bio VARCHAR(500) NOT NULL DEFAULT '',
    role VARCHAR(10) NOT NULL DEFAULT 'student',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_user_role CHECK (role IN ('student', 'admin')),
    CONSTRAINT ck_user_semester CHECK (semester BETWEEN 1 AND 12)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS skill (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(80) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_skill (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    skill_id INT NOT NULL,
    skill_type VARCHAR(5) NOT NULL,
    proficiency VARCHAR(12) NOT NULL DEFAULT 'Beginner',
    CONSTRAINT uq_user_skill_type UNIQUE (user_id, skill_id, skill_type),
    CONSTRAINT ck_user_skill_type CHECK (skill_type IN ('teach', 'learn')),
    CONSTRAINT ck_user_skill_proficiency
        CHECK (proficiency IN ('Beginner', 'Intermediate', 'Advanced')),
    CONSTRAINT fk_user_skill_user FOREIGN KEY (user_id)
        REFERENCES `user`(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_skill_skill FOREIGN KEY (skill_id)
        REFERENCES skill(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    campus_location VARCHAR(120) NOT NULL DEFAULT '',
    preferred_format VARCHAR(12) NOT NULL DEFAULT 'Either',
    languages VARCHAR(200) NOT NULL DEFAULT '',
    availability_notes VARCHAR(500) NOT NULL DEFAULT '',
    CONSTRAINT ck_preferences_format
        CHECK (preferred_format IN ('In person', 'Online', 'Either')),
    CONSTRAINT fk_preferences_user FOREIGN KEY (user_id)
        REFERENCES `user`(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS availability_slot (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    note VARCHAR(200) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_availability_time CHECK (ends_at > starts_at),
    CONSTRAINT fk_availability_user FOREIGN KEY (user_id)
        REFERENCES `user`(id) ON DELETE CASCADE,
    INDEX ix_availability_user_time (user_id, starts_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS exchange_request (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    receiver_id INT NOT NULL,
    skill_offered_id INT NOT NULL,
    skill_requested_id INT NOT NULL,
    message VARCHAR(500) NOT NULL DEFAULT '',
    status VARCHAR(10) NOT NULL DEFAULT 'Pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_request_distinct_users CHECK (sender_id <> receiver_id),
    CONSTRAINT ck_request_status
        CHECK (status IN ('Pending', 'Accepted', 'Rejected', 'Cancelled', 'Completed')),
    CONSTRAINT fk_request_sender FOREIGN KEY (sender_id) REFERENCES `user`(id),
    CONSTRAINT fk_request_receiver FOREIGN KEY (receiver_id) REFERENCES `user`(id),
    CONSTRAINT fk_request_offered_skill FOREIGN KEY (skill_offered_id) REFERENCES skill(id),
    CONSTRAINT fk_request_requested_skill FOREIGN KEY (skill_requested_id) REFERENCES skill(id),
    INDEX ix_request_sender_status (sender_id, status),
    INDEX ix_request_receiver_status (receiver_id, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS learning_session (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL UNIQUE,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    location VARCHAR(200) NOT NULL,
    notes VARCHAR(500) NOT NULL DEFAULT '',
    status VARCHAR(10) NOT NULL DEFAULT 'Scheduled',
    CONSTRAINT ck_session_time CHECK (ends_at > starts_at),
    CONSTRAINT ck_session_status CHECK (status IN ('Scheduled', 'Completed', 'Cancelled')),
    CONSTRAINT fk_session_request FOREIGN KEY (request_id)
        REFERENCES exchange_request(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS session_change_proposal (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    proposer_id INT NOT NULL,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    location VARCHAR(200) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'Pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_change_proposal_time CHECK (ends_at > starts_at),
    CONSTRAINT ck_change_proposal_status
        CHECK (status IN ('Pending', 'Accepted', 'Rejected', 'Cancelled')),
    CONSTRAINT fk_change_proposal_session FOREIGN KEY (session_id)
        REFERENCES learning_session(id) ON DELETE CASCADE,
    CONSTRAINT fk_change_proposal_user FOREIGN KEY (proposer_id) REFERENCES `user`(id),
    INDEX ix_change_proposal_status (session_id, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS review (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    reviewer_id INT NOT NULL,
    rating INT NOT NULL,
    review_text VARCHAR(1000) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_review_once UNIQUE (session_id, reviewer_id),
    CONSTRAINT ck_review_rating CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT fk_review_session FOREIGN KEY (session_id)
        REFERENCES learning_session(id) ON DELETE CASCADE,
    CONSTRAINT fk_review_user FOREIGN KEY (reviewer_id) REFERENCES `user`(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notification (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    message VARCHAR(500) NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notification_user FOREIGN KEY (user_id)
        REFERENCES `user`(id) ON DELETE CASCADE,
    INDEX ix_notification_user_read (user_id, is_read)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS direct_message (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    recipient_id INT NOT NULL,
    body VARCHAR(2000) NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_message_distinct_users CHECK (sender_id <> recipient_id),
    CONSTRAINT fk_message_sender FOREIGN KEY (sender_id) REFERENCES `user`(id),
    CONSTRAINT fk_message_recipient FOREIGN KEY (recipient_id) REFERENCES `user`(id),
    INDEX ix_message_thread (sender_id, recipient_id, created_at),
    INDEX ix_message_inbox (recipient_id, is_read, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS saved_student (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    student_id INT NOT NULL,
    CONSTRAINT uq_saved_student UNIQUE (user_id, student_id),
    CONSTRAINT ck_saved_not_self CHECK (user_id <> student_id),
    CONSTRAINT fk_saved_student_owner FOREIGN KEY (user_id)
        REFERENCES `user`(id) ON DELETE CASCADE,
    CONSTRAINT fk_saved_student_target FOREIGN KEY (student_id)
        REFERENCES `user`(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS saved_skill (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    skill_id INT NOT NULL,
    CONSTRAINT uq_saved_skill UNIQUE (user_id, skill_id),
    CONSTRAINT fk_saved_skill_owner FOREIGN KEY (user_id)
        REFERENCES `user`(id) ON DELETE CASCADE,
    CONSTRAINT fk_saved_skill_target FOREIGN KEY (skill_id)
        REFERENCES skill(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reporter_id INT NOT NULL,
    reported_user_id INT NOT NULL,
    reason VARCHAR(500) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'Open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_report_status CHECK (status IN ('Open', 'Reviewed', 'Dismissed')),
    CONSTRAINT fk_report_reporter FOREIGN KEY (reporter_id) REFERENCES `user`(id),
    CONSTRAINT fk_report_reported_user FOREIGN KEY (reported_user_id) REFERENCES `user`(id)
) ENGINE=InnoDB;

INSERT IGNORE INTO skill (name, category) VALUES
    ('Python', 'Programming'),
    ('Java', 'Programming'),
    ('C and C++', 'Programming'),
    ('HTML and CSS', 'Web Development'),
    ('JavaScript', 'Web Development'),
    ('Web Development', 'Web Development'),
    ('Database Management', 'Technology'),
    ('SQL', 'Technology'),
    ('Data Structures and Algorithms', 'Computer Science'),
    ('Graphic Design', 'Creative'),
    ('Video Editing', 'Creative'),
    ('Photography', 'Creative'),
    ('Public Speaking', 'Communication'),
    ('Communication Skills', 'Communication'),
    ('Microsoft Excel', 'Productivity'),
    ('Presentation Design', 'Creative');
