from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    college = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    bio = db.Column(db.String(500), nullable=False, default="")
    role = db.Column(db.String(10), nullable=False, default="student")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    __table_args__ = (
        db.CheckConstraint("role IN ('student', 'admin')", name="ck_user_role"),
        db.CheckConstraint("semester BETWEEN 1 AND 12", name="ck_user_semester"),
    )
    user_skills = db.relationship("UserSkill", back_populates="user", cascade="all, delete-orphan")
    preferences = db.relationship(
        "UserPreferences", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    user_skills = db.relationship("UserSkill", back_populates="skill")


class UserSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill.id"), nullable=False)
    skill_type = db.Column(db.String(5), nullable=False)
    proficiency = db.Column(db.String(12), nullable=False, default="Beginner")
    user = db.relationship("User", back_populates="user_skills")
    skill = db.relationship("Skill", back_populates="user_skills")
    __table_args__ = (
        db.UniqueConstraint("user_id", "skill_id", "skill_type", name="uq_user_skill_type"),
        db.CheckConstraint("skill_type IN ('teach', 'learn')", name="ck_user_skill_type"),
        db.CheckConstraint(
            "proficiency IN ('Beginner', 'Intermediate', 'Advanced')",
            name="ck_user_skill_proficiency",
        ),
    )


class UserPreferences(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    campus_location = db.Column(db.String(120), nullable=False, default="")
    preferred_format = db.Column(db.String(12), nullable=False, default="Either")
    languages = db.Column(db.String(200), nullable=False, default="")
    availability_notes = db.Column(db.String(500), nullable=False, default="")
    user = db.relationship("User", back_populates="preferences")
    __table_args__ = (
        db.CheckConstraint(
            "preferred_format IN ('In person', 'Online', 'Either')",
            name="ck_preferences_format",
        ),
    )


class AvailabilitySlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    note = db.Column(db.String(200), nullable=False, default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    user = db.relationship("User")
    __table_args__ = (
        db.CheckConstraint("ends_at > starts_at", name="ck_availability_time"),
    )


class ExchangeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    skill_offered_id = db.Column(db.Integer, db.ForeignKey("skill.id"), nullable=False)
    skill_requested_id = db.Column(db.Integer, db.ForeignKey("skill.id"), nullable=False)
    message = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(10), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    sender = db.relationship("User", foreign_keys=[sender_id])
    receiver = db.relationship("User", foreign_keys=[receiver_id])
    skill_offered = db.relationship("Skill", foreign_keys=[skill_offered_id])
    skill_requested = db.relationship("Skill", foreign_keys=[skill_requested_id])
    __table_args__ = (
        db.CheckConstraint("sender_id <> receiver_id", name="ck_request_distinct_users"),
        db.CheckConstraint(
            "status IN ('Pending', 'Accepted', 'Rejected', 'Cancelled', 'Completed')",
            name="ck_request_status",
        ),
    )


class LearningSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("exchange_request.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(10), nullable=False, default="Scheduled")
    exchange_request = db.relationship("ExchangeRequest")
    reviews = db.relationship("Review", back_populates="learning_session", cascade="all, delete-orphan")
    change_proposals = db.relationship(
        "SessionChangeProposal", back_populates="learning_session",
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        db.CheckConstraint("ends_at > starts_at", name="ck_session_time"),
        db.CheckConstraint(
            "status IN ('Scheduled', 'Completed', 'Cancelled')",
            name="ck_session_status",
        ),
    )


class SessionChangeProposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("learning_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    learning_session = db.relationship("LearningSession", back_populates="change_proposals")
    proposer = db.relationship("User")
    __table_args__ = (
        db.CheckConstraint("ends_at > starts_at", name="ck_change_proposal_time"),
        db.CheckConstraint(
            "status IN ('Pending', 'Accepted', 'Rejected', 'Cancelled')",
            name="ck_change_proposal_status",
        ),
    )


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("learning_session.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    learning_session = db.relationship("LearningSession", back_populates="reviews")
    reviewer = db.relationship("User")
    __table_args__ = (
        db.UniqueConstraint("session_id", "reviewer_id", name="uq_review_once"),
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"),
    )


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    user = db.relationship("User")


class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.String(2000), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
    __table_args__ = (
        db.CheckConstraint("sender_id <> recipient_id", name="ck_message_distinct_users"),
    )


class SavedStudent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    student = db.relationship("User", foreign_keys=[student_id])
    __table_args__ = (
        db.UniqueConstraint("user_id", "student_id", name="uq_saved_student"),
        db.CheckConstraint("user_id <> student_id", name="ck_saved_not_self"),
    )


class SavedSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    skill = db.relationship("Skill")
    __table_args__ = (
        db.UniqueConstraint("user_id", "skill_id", name="uq_saved_skill"),
    )


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="Open")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reported_user = db.relationship("User", foreign_keys=[reported_user_id])
    __table_args__ = (
        db.CheckConstraint("status IN ('Open', 'Reviewed', 'Dismissed')", name="ck_report_status"),
    )
