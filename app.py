from datetime import datetime, timedelta
from functools import wraps
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template, request, session, url_for
)
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from sqlalchemy import func, or_
from werkzeug.middleware.proxy_fix import ProxyFix
from .matching import rank_matches
from .models import (
    AvailabilitySlot, DirectMessage, ExchangeRequest, LearningSession,
    Notification, Report, Review, SavedSkill, SavedStudent, SessionChangeProposal,
    Skill, User, UserPreferences, UserSkill, db,
)


SKILL_DIRECTORY = (
    ("Python", "Programming"), ("Java", "Programming"),
    ("C and C++", "Programming"), ("HTML and CSS", "Web Development"),
    ("JavaScript", "Web Development"), ("Web Development", "Web Development"),
    ("Database Management", "Technology"), ("SQL", "Technology"),
    ("Data Structures and Algorithms", "Computer Science"),
    ("Graphic Design", "Creative"), ("Video Editing", "Creative"),
    ("Photography", "Creative"), ("Public Speaking", "Communication"),
    ("Communication Skills", "Communication"), ("Microsoft Excel", "Productivity"),
    ("Presentation Design", "Creative"),
)


def valid_email(email):
    if len(email) > 254 or any(character.isspace() for character in email):
        return False
    if email.count("@") != 1:
        return False
    domain = email.rsplit("@", 1)[1]
    domain_parts = domain.split(".")
    return (
        bool(email.split("@", 1)[0])
        and len(domain_parts) >= 2
        and all(domain_parts)
    )


def normalize_database_url(database_url):
    if database_url and database_url.startswith("mysql://"):
        return database_url.replace("mysql://", "mysql+pymysql://", 1)
    return database_url


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    railway_environment = bool(os.environ.get("RAILWAY_ENVIRONMENT_NAME"))
    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("MYSQL_URL")
    )
    database_url = normalize_database_url(database_url)
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=database_url or "sqlite:///campus_skill_exchange.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get(
            "COOKIE_SECURE", "1" if railway_environment else "0"
        ) == "1",
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if railway_environment and not database_url and not test_config:
        raise RuntimeError("Set DATABASE_URL to the Railway MySQL service URL.")
    secret_key = app.config.get("SECRET_KEY")
    if (not isinstance(secret_key, str) or len(secret_key) < 32
            or secret_key == "replace-with-a-long-random-secret"):
        raise RuntimeError(
            "Set SECRET_KEY to a private random value of at least 32 characters."
        )

    db.init_app(app)
    CSRFProtect(app)
    if railway_environment:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.context_processor
    def inject_template_helpers():
        user = current_user()
        unread_count = (
            Notification.query.filter_by(user_id=user.id, is_read=False).count()
            if user else 0
        )
        unread_message_count = (
            DirectMessage.query.filter_by(recipient_id=user.id, is_read=False).count()
            if user else 0
        )
        return {
            "current_user": user,
            "unread_count": unread_count,
            "unread_message_count": unread_message_count,
            "csrf_token": generate_csrf,
        }

    @app.before_request
    def enforce_active_account():
        user_id = session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if user is None or not user.is_active:
                session.clear()
                flash("Your account is unavailable. Please contact an administrator.", "error")

    @app.errorhandler(CSRFError)
    def csrf_error(_error):
        flash("Your form expired or could not be verified. Please try again.", "error")
        return render_template("message.html", title="Form verification failed"), 400

    with app.app_context():
        db.create_all()
        if Skill.query.count() == 0:
            db.session.add_all(
                Skill(name=name, category=category) for name, category in SKILL_DIRECTORY
            )
            db.session.commit()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user():
                flash("Please log in to continue.", "error")
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if user.role != "admin":
                abort(403)
            return view(*args, **kwargs)
        return wrapped

    @app.route("/")
    def home():
        return render_template("home.html", skill_count=Skill.query.filter_by(is_active=True).count())

    @app.route("/healthz")
    def health_check():
        db.session.execute(db.select(1))
        return {"status": "ok"}, 200

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            college = request.form.get("college", "").strip()
            department = request.form.get("department", "").strip()
            semester_text = request.form.get("semester", "").strip()
            bio = request.form.get("bio", "").strip()
            errors = []
            if not all((name, email, password, confirm, college, department, semester_text)):
                errors.append("Complete all required fields.")
            if not valid_email(email):
                errors.append("Enter a valid college email address.")
            if len(password) < 8:
                errors.append("Password must contain at least 8 characters.")
            if password != confirm:
                errors.append("Passwords do not match.")
            try:
                semester = int(semester_text)
                if semester < 1 or semester > 12:
                    raise ValueError
            except ValueError:
                semester = 0
                errors.append("Semester must be a number between 1 and 12.")
            if len(name) > 100 or len(college) > 150 or len(department) > 100 or len(bio) > 500:
                errors.append("One or more fields exceed the allowed length.")
            if email and User.query.filter(func.lower(User.email) == email).first():
                errors.append("An account with that email already exists.")
            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                user = User(
                    full_name=name, email=email, college=college,
                    department=department, semester=semester, bio=bio,
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))
        return render_template("auth.html", mode="register")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter(func.lower(User.email) == email).first()
            if user and user.is_active and user.check_password(password):
                session.clear()
                session["user_id"] = user.id
                flash(f"Welcome back, {user.full_name}.", "success")
                destination = request.args.get("next")
                if destination and destination.startswith("/") and not destination.startswith("//"):
                    return redirect(destination)
                return redirect(url_for("dashboard"))
            flash("Email or password is incorrect.", "error")
        return render_template("auth.html", mode="login")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("home"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        return render_template(
            "dashboard.html",
            teach_count=UserSkill.query.filter_by(user_id=user.id, skill_type="teach").count(),
            learn_count=UserSkill.query.filter_by(user_id=user.id, skill_type="learn").count(),
            sent_count=ExchangeRequest.query.filter_by(sender_id=user.id).count(),
            session_count=LearningSession.query.join(ExchangeRequest).filter(
                or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id)
            ).count(),
            matches=matches_for(user)[:3],
        )

    @app.route("/profile")
    @login_required
    def profile():
        user = current_user()
        return render_template(
            "profile.html", profile_user=user,
            preferences=user.preferences or UserPreferences(user_id=user.id),
            is_saved=False,
            available_slots=AvailabilitySlot.query.filter(
                AvailabilitySlot.user_id == user.id,
                AvailabilitySlot.ends_at > datetime.now(),
                AvailabilitySlot.is_active.is_(True),
            ).order_by(AvailabilitySlot.starts_at).all(),
            review_summary=review_summary(user.id),
        )

    @app.route("/students/<int:user_id>")
    @login_required
    def student_profile(user_id):
        profile_user = db.session.get(User, user_id)
        if not profile_user or not profile_user.is_active:
            abort(404)
        is_saved = SavedStudent.query.filter_by(
            user_id=current_user().id, student_id=profile_user.id
        ).first() is not None
        return render_template(
            "profile.html", profile_user=profile_user,
            preferences=profile_user.preferences or UserPreferences(user_id=profile_user.id),
            is_saved=is_saved,
            available_slots=AvailabilitySlot.query.filter(
                AvailabilitySlot.user_id == profile_user.id,
                AvailabilitySlot.ends_at > datetime.now(),
                AvailabilitySlot.is_active.is_(True),
            ).order_by(AvailabilitySlot.starts_at).all(),
            review_summary=review_summary(profile_user.id),
        )

    def review_summary(user_id):
        return db.session.query(
            func.count(Review.id), func.avg(Review.rating)
        ).join(LearningSession).join(ExchangeRequest).filter(
            Review.reviewer_id != user_id,
            or_(
                ExchangeRequest.sender_id == user_id,
                ExchangeRequest.receiver_id == user_id,
            ),
        ).one()

    @app.route("/profile/edit", methods=["GET", "POST"])
    @login_required
    def edit_profile():
        user = current_user()
        preferences = user.preferences or UserPreferences(user_id=user.id)
        if request.method == "POST":
            name = request.form.get("full_name", "").strip()
            college = request.form.get("college", "").strip()
            department = request.form.get("department", "").strip()
            bio = request.form.get("bio", "").strip()
            campus_location = request.form.get("campus_location", "").strip()
            preferred_format = request.form.get("preferred_format", "")
            languages = request.form.get("languages", "").strip()
            availability_notes = request.form.get("availability_notes", "").strip()
            try:
                semester = int(request.form.get("semester", ""))
            except ValueError:
                semester = 0
            if not name or not college or not department or semester not in range(1, 13):
                flash("Enter a name, college, department, and semester from 1 to 12.", "error")
            elif len(name) > 100 or len(college) > 150 or len(department) > 100 or len(bio) > 500:
                flash("One or more fields exceed the allowed length.", "error")
            elif (len(campus_location) > 120 or preferred_format not in ("In person", "Online", "Either")
                    or len(languages) > 200 or len(availability_notes) > 500):
                flash("Check your location, learning format, languages, and availability note.", "error")
            else:
                user.full_name, user.college = name, college
                user.department, user.semester, user.bio = department, semester, bio
                preferences.campus_location = campus_location
                preferences.preferred_format = preferred_format
                preferences.languages = languages
                preferences.availability_notes = availability_notes
                if not user.preferences:
                    db.session.add(preferences)
                db.session.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("profile"))
        return render_template(
            "profile_edit.html", profile_user=user, preferences=preferences
        )

    @app.route("/availability", methods=["GET", "POST"])
    @login_required
    def availability():
        user = current_user()
        if request.method == "POST":
            if request.form.get("action") == "delete":
                try:
                    slot_id = int(request.form.get("slot_id", ""))
                except ValueError:
                    abort(400)
                slot = db.session.get(AvailabilitySlot, slot_id)
                if not slot or slot.user_id != user.id:
                    abort(404)
                db.session.delete(slot)
                db.session.commit()
                flash("Availability removed.", "success")
                return redirect(url_for("availability"))
            try:
                starts = datetime.strptime(request.form.get("starts_at", ""), "%Y-%m-%dT%H:%M")
                ends = datetime.strptime(request.form.get("ends_at", ""), "%Y-%m-%dT%H:%M")
            except (ValueError, TypeError):
                flash("Enter a valid availability date and time.", "error")
                return redirect(url_for("availability"))
            note = request.form.get("note", "").strip()
            overlap = AvailabilitySlot.query.filter(
                AvailabilitySlot.user_id == user.id,
                AvailabilitySlot.is_active.is_(True),
                AvailabilitySlot.starts_at < ends,
                AvailabilitySlot.ends_at > starts,
            ).first()
            if starts <= datetime.now() or ends <= starts:
                flash("Availability must start in the future and end after it starts.", "error")
            elif len(note) > 200:
                flash("Availability notes must be under 200 characters.", "error")
            elif overlap:
                flash("This time overlaps another availability slot you shared.", "error")
            else:
                db.session.add(AvailabilitySlot(
                    user_id=user.id, starts_at=starts, ends_at=ends, note=note,
                ))
                db.session.commit()
                flash("Availability shared with other signed-in students.", "success")
                return redirect(url_for("availability"))
        slots = AvailabilitySlot.query.filter_by(user_id=user.id).filter(
            AvailabilitySlot.ends_at > datetime.now()
        ).order_by(AvailabilitySlot.starts_at).all()
        return render_template("availability.html", slots=slots)

    @app.route("/skills", methods=["GET", "POST"])
    @login_required
    def skills():
        user = current_user()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                try:
                    skill_id = int(request.form.get("skill_id", ""))
                except ValueError:
                    skill_id = 0
                skill_type = request.form.get("skill_type", "")
                proficiency = request.form.get("proficiency", "Beginner")
                skill = db.session.get(Skill, skill_id)
                if (not skill or not skill.is_active
                        or skill_type not in ("teach", "learn")
                        or proficiency not in ("Beginner", "Intermediate", "Advanced")):
                    flash("Choose a valid skill, skill type, and proficiency.", "error")
                elif UserSkill.query.filter_by(
                    user_id=user.id, skill_id=skill.id, skill_type=skill_type
                ).first():
                    flash("That skill is already in your list for this type.", "error")
                else:
                    db.session.add(UserSkill(
                        user_id=user.id, skill_id=skill.id,
                        skill_type=skill_type, proficiency=proficiency,
                    ))
                    db.session.commit()
                    flash("Skill added to your profile.", "success")
                    return redirect(url_for("skills"))
            elif action == "delete":
                try:
                    entry_id = int(request.form.get("entry_id", ""))
                except ValueError:
                    entry_id = 0
                entry = db.session.get(UserSkill, entry_id)
                if not entry or entry.user_id != user.id:
                    abort(404)
                db.session.delete(entry)
                db.session.commit()
                flash("Skill removed.", "success")
                return redirect(url_for("skills"))
        entries = UserSkill.query.filter_by(user_id=user.id).join(Skill).order_by(
            UserSkill.skill_type, Skill.name
        ).all()
        return render_template(
            "skills.html", entries=entries,
            available_skills=Skill.query.filter_by(is_active=True).order_by(Skill.name).all(),
        )

    def matches_for(user):
        rows = db.session.query(UserSkill, User).join(User, User.id == UserSkill.user_id).join(
            Skill, Skill.id == UserSkill.skill_id
        ).filter(User.is_active.is_(True), Skill.is_active.is_(True)).all()
        skill_data = [
            {
                "student_id": user_skill.user_id,
                "student": peer.full_name,
                "skill_name": user_skill.skill.name,
                "skill_type": user_skill.skill_type,
            }
            for user_skill, peer in rows
        ]
        return rank_matches({"id": user.id, "student": user.full_name}, skill_data)

    @app.route("/explore")
    @login_required
    def explore():
        query = request.args.get("q", "").strip()
        student_name = request.args.get("student", "").strip()
        college = request.args.get("college", "").strip()
        category = request.args.get("category", "").strip()
        proficiency = request.args.get("proficiency", "").strip()
        sort = request.args.get("sort", "skill")
        listing = UserSkill.query.join(User).join(Skill).filter(
            User.id != current_user().id,
            User.is_active.is_(True),
            Skill.is_active.is_(True),
            UserSkill.skill_type == "teach",
        )
        if query:
            listing = listing.filter(Skill.name.ilike(f"%{query}%"))
        if student_name:
            listing = listing.filter(User.full_name.ilike(f"%{student_name}%"))
        if college:
            listing = listing.filter(User.college.ilike(f"%{college}%"))
        if category:
            listing = listing.filter(Skill.category == category)
        if proficiency in ("Beginner", "Intermediate", "Advanced"):
            listing = listing.filter(UserSkill.proficiency == proficiency)
        ordering = {
            "skill": (Skill.name, User.full_name),
            "student": (User.full_name, Skill.name),
            "level": (UserSkill.proficiency, User.full_name),
        }.get(sort, (Skill.name, User.full_name))
        results = listing.order_by(*ordering).all()
        saved_student_ids = {
            row.student_id for row in SavedStudent.query.filter_by(user_id=current_user().id).all()
        }
        saved_skill_ids = {
            row.skill_id for row in SavedSkill.query.filter_by(user_id=current_user().id).all()
        }
        return render_template(
            "explore.html", results=results, query=query, category=category,
            proficiency=proficiency, student_name=student_name, college=college, sort=sort,
            saved_student_ids=saved_student_ids, saved_skill_ids=saved_skill_ids,
            categories=[row[0] for row in db.session.query(Skill.category).filter_by(
                is_active=True
            ).distinct().order_by(Skill.category).all()],
        )

    @app.route("/suggestions")
    @login_required
    def skill_suggestions():
        user = current_user()
        own_skill_ids = {
            row[0] for row in db.session.query(UserSkill.skill_id).filter_by(user_id=user.id).all()
        }
        interest_categories = {
            row[0] for row in db.session.query(Skill.category)
            .join(UserSkill, UserSkill.skill_id == Skill.id)
            .filter(UserSkill.user_id == user.id).distinct().all()
        }
        popularity = dict(
            db.session.query(
                UserSkill.skill_id,
                func.count(func.distinct(UserSkill.user_id)),
            ).join(User, User.id == UserSkill.user_id).filter(
                User.is_active.is_(True), UserSkill.skill_type == "teach"
            ).group_by(UserSkill.skill_id).all()
        )
        skill_rows = Skill.query.filter(
            Skill.is_active.is_(True), ~Skill.id.in_(own_skill_ids or {-1})
        ).order_by(Skill.name).all()
        suggestions = [
            {
                "skill": skill,
                "teachers": popularity.get(skill.id, 0),
                "related": skill.category in interest_categories,
            }
            for skill in skill_rows
        ]
        suggestions.sort(
            key=lambda item: (-int(item["related"]), -item["teachers"], item["skill"].name.casefold())
        )
        saved_skill_ids = {
            row.skill_id for row in SavedSkill.query.filter_by(user_id=user.id).all()
        }
        return render_template(
            "suggestions.html", suggestions=suggestions,
            interest_categories=sorted(interest_categories),
            saved_skill_ids=saved_skill_ids,
        )

    @app.route("/matches")
    @login_required
    def matches():
        saved_student_ids = {
            row.student_id for row in SavedStudent.query.filter_by(user_id=current_user().id).all()
        }
        return render_template(
            "matches.html", matches=matches_for(current_user()),
            saved_student_ids=saved_student_ids,
        )

    @app.route("/saved")
    @login_required
    def saved_items():
        user = current_user()
        saved_students = SavedStudent.query.filter_by(user_id=user.id).join(
            User, SavedStudent.student_id == User.id
        ).filter(User.is_active.is_(True)).order_by(User.full_name).all()
        saved_skills = SavedSkill.query.filter_by(user_id=user.id).join(Skill).filter(
            Skill.is_active.is_(True)
        ).order_by(Skill.category, Skill.name).all()
        return render_template(
            "saved.html", saved_students=saved_students, saved_skills=saved_skills
        )

    @app.route("/saved/students/<int:student_id>", methods=["POST"])
    @login_required
    def toggle_saved_student(student_id):
        user = current_user()
        student = db.session.get(User, student_id)
        if not student or not student.is_active or student.id == user.id:
            abort(404)
        saved = SavedStudent.query.filter_by(
            user_id=user.id, student_id=student.id
        ).first()
        if saved:
            db.session.delete(saved)
            flash("Student removed from your saved list.", "success")
        else:
            db.session.add(SavedStudent(user_id=user.id, student_id=student.id))
            flash("Student saved for later.", "success")
        db.session.commit()
        return redirect(url_for("saved_items"))

    @app.route("/saved/skills/<int:skill_id>", methods=["POST"])
    @login_required
    def toggle_saved_skill(skill_id):
        skill = db.session.get(Skill, skill_id)
        if not skill or not skill.is_active:
            abort(404)
        saved = SavedSkill.query.filter_by(
            user_id=current_user().id, skill_id=skill.id
        ).first()
        if saved:
            db.session.delete(saved)
            flash("Skill removed from your saved list.", "success")
        else:
            db.session.add(SavedSkill(user_id=current_user().id, skill_id=skill.id))
            flash("Skill saved for later.", "success")
        db.session.commit()
        return redirect(url_for("saved_items"))

    @app.route("/messages")
    @login_required
    def messages_inbox():
        user = current_user()
        messages = DirectMessage.query.filter(
            or_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user.id)
        ).order_by(DirectMessage.created_at.desc()).all()
        conversations = {}
        for item in messages:
            peer_id = item.recipient_id if item.sender_id == user.id else item.sender_id
            if peer_id not in conversations:
                conversations[peer_id] = {
                    "peer": item.recipient if item.sender_id == user.id else item.sender,
                    "latest": item,
                    "unread": 0,
                }
            if item.recipient_id == user.id and not item.is_read:
                conversations[peer_id]["unread"] += 1
        return render_template(
            "messages.html",
            conversations=sorted(
                conversations.values(),
                key=lambda row: row["latest"].created_at,
                reverse=True,
            ),
        )

    @app.route("/messages/<int:other_user_id>", methods=["GET", "POST"])
    @login_required
    def conversation(other_user_id):
        user = current_user()
        peer = db.session.get(User, other_user_id)
        if not peer or not peer.is_active or peer.id == user.id:
            abort(404)
        if request.method == "POST":
            body = request.form.get("body", "").strip()
            if not body or len(body) > 2000:
                flash("Write a message of 1–2000 characters.", "error")
            else:
                db.session.add(DirectMessage(
                    sender_id=user.id, recipient_id=peer.id, body=body,
                ))
                db.session.add(Notification(
                    user_id=peer.id, message=f"You have a new private message from {user.full_name}."
                ))
                db.session.commit()
                return redirect(url_for("conversation", other_user_id=peer.id))
        incoming = DirectMessage.query.filter_by(
            sender_id=peer.id, recipient_id=user.id, is_read=False
        ).all()
        for item in incoming:
            item.is_read = True
        if incoming:
            db.session.commit()
        thread = DirectMessage.query.filter(or_(
            (DirectMessage.sender_id == user.id) & (DirectMessage.recipient_id == peer.id),
            (DirectMessage.sender_id == peer.id) & (DirectMessage.recipient_id == user.id),
        )).order_by(DirectMessage.created_at).all()
        return render_template("conversation.html", peer=peer, messages=thread)

    @app.route("/requests")
    @login_required
    def requests_list():
        user = current_user()
        sent = ExchangeRequest.query.filter_by(sender_id=user.id).order_by(
            ExchangeRequest.created_at.desc()
        ).all()
        received = ExchangeRequest.query.filter_by(receiver_id=user.id).order_by(
            ExchangeRequest.created_at.desc()
        ).all()
        return render_template("requests.html", sent=sent, received=received)

    @app.route("/requests/<int:request_id>")
    @login_required
    def request_detail(request_id):
        exchange = db.session.get(ExchangeRequest, request_id)
        if not exchange:
            abort(404)
        if current_user().id not in (exchange.sender_id, exchange.receiver_id):
            abort(403)
        learning_session = LearningSession.query.filter_by(request_id=exchange.id).first()
        return render_template(
            "request_detail.html", exchange=exchange, learning_session=learning_session
        )

    @app.route("/requests/new/<int:receiver_id>", methods=["GET", "POST"])
    @login_required
    def new_request(receiver_id):
        sender = current_user()
        receiver = db.session.get(User, receiver_id)
        if not receiver or not receiver.is_active or receiver.id == sender.id:
            abort(404)
        if request.method == "POST":
            try:
                offered_id = int(request.form.get("skill_offered_id", ""))
                requested_id = int(request.form.get("skill_requested_id", ""))
            except ValueError:
                offered_id = requested_id = 0
            sender_offer = UserSkill.query.filter_by(
                user_id=sender.id, skill_id=offered_id, skill_type="teach"
            ).first()
            receiver_offer = UserSkill.query.filter_by(
                user_id=receiver.id, skill_id=requested_id, skill_type="teach"
            ).first()
            message = request.form.get("message", "").strip()
            if not sender_offer or not receiver_offer or len(message) > 500:
                flash("Select skills you teach and the student teaches; message must be under 500 characters.", "error")
            else:
                exchange = ExchangeRequest(
                    sender_id=sender.id, receiver_id=receiver.id,
                    skill_offered_id=offered_id, skill_requested_id=requested_id,
                    message=message,
                )
                db.session.add(exchange)
                db.session.add(Notification(
                    user_id=receiver.id,
                    message=f"{sender.full_name} sent you a skill exchange request.",
                ))
                db.session.commit()
                flash("Exchange request sent.", "success")
                return redirect(url_for("requests_list"))
        sender_skills = UserSkill.query.filter_by(user_id=sender.id, skill_type="teach").all()
        receiver_skills = UserSkill.query.filter_by(user_id=receiver.id, skill_type="teach").all()
        return render_template(
            "request_new.html", receiver=receiver,
            sender_skills=sender_skills, receiver_skills=receiver_skills,
        )

    @app.route("/requests/<int:request_id>/action", methods=["POST"])
    @login_required
    def request_action(request_id):
        exchange = db.session.get(ExchangeRequest, request_id)
        if not exchange:
            abort(404)
        user = current_user()
        action = request.form.get("action")
        allowed = (
            (action in ("accept", "reject") and exchange.receiver_id == user.id)
            or (action == "cancel" and exchange.sender_id == user.id)
        )
        if not allowed or exchange.status != "Pending":
            abort(403)
        exchange.status = {"accept": "Accepted", "reject": "Rejected", "cancel": "Cancelled"}[action]
        other_user_id = exchange.sender_id if user.id == exchange.receiver_id else exchange.receiver_id
        db.session.add(Notification(
            user_id=other_user_id,
            message=f"Your exchange request was {exchange.status.lower()}.",
        ))
        db.session.commit()
        flash(f"Request {exchange.status.lower()}.", "success")
        return redirect(url_for("requests_list"))

    @app.route("/sessions", methods=["GET", "POST"])
    @login_required
    def sessions_list():
        user = current_user()
        if request.method == "POST":
            slot_text = request.form.get("availability_slot_id", "").strip()
            try:
                request_id = int(request.form.get("request_id", ""))
                slot_id = int(slot_text) if slot_text else None
            except ValueError:
                flash("Enter a valid session date and time.", "error")
                return redirect(url_for("sessions_list"))
            exchange = db.session.get(ExchangeRequest, request_id)
            location = request.form.get("location", "").strip()
            notes = request.form.get("notes", "").strip()
            if (not exchange or user.id not in (exchange.sender_id, exchange.receiver_id)
                    or exchange.status != "Accepted"):
                abort(403)
            selected_slot = None
            if slot_id:
                selected_slot = db.session.get(AvailabilitySlot, slot_id)
                if (not selected_slot or not selected_slot.is_active
                        or selected_slot.user_id not in (exchange.sender_id, exchange.receiver_id)
                        or selected_slot.starts_at <= datetime.now()):
                    abort(403)
                starts, ends = selected_slot.starts_at, selected_slot.ends_at
            else:
                try:
                    starts = datetime.strptime(request.form.get("starts_at", ""), "%Y-%m-%dT%H:%M")
                    ends = datetime.strptime(request.form.get("ends_at", ""), "%Y-%m-%dT%H:%M")
                except (ValueError, TypeError):
                    flash("Enter valid session times or choose a shared availability slot.", "error")
                    return redirect(url_for("sessions_list"))
            if LearningSession.query.filter_by(request_id=exchange.id).first():
                flash("A session is already scheduled for this request.", "error")
            elif starts <= datetime.now() or ends <= starts or not location or len(location) > 200:
                flash("Choose a future start time, a later end time, and a valid location.", "error")
            elif len(notes) > 500:
                flash("Notes must be under 500 characters.", "error")
            else:
                conflicting_session = LearningSession.query.join(ExchangeRequest).filter(
                    LearningSession.status == "Scheduled",
                    LearningSession.starts_at < ends,
                    LearningSession.ends_at > starts,
                    or_(
                        ExchangeRequest.sender_id.in_((exchange.sender_id, exchange.receiver_id)),
                        ExchangeRequest.receiver_id.in_((exchange.sender_id, exchange.receiver_id)),
                    ),
                ).first()
                if conflicting_session:
                    flash("This time overlaps another session for one of the students.", "error")
                else:
                    learning_session = LearningSession(
                        request_id=exchange.id, starts_at=starts, ends_at=ends,
                        location=location, notes=notes,
                    )
                    db.session.add(learning_session)
                    other_id = exchange.receiver_id if user.id == exchange.sender_id else exchange.sender_id
                    db.session.add(Notification(
                        user_id=other_id, message=f"{user.full_name} scheduled a skill exchange session."
                    ))
                    if selected_slot:
                        selected_slot.is_active = False
                    db.session.commit()
                    flash("Session scheduled.", "success")
                    return redirect(url_for("sessions_list"))
        exchanges = ExchangeRequest.query.filter(
            ExchangeRequest.status == "Accepted",
            or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id),
        ).all()
        schedulable = [
            exchange for exchange in exchanges
            if not LearningSession.query.filter_by(request_id=exchange.id).first()
        ]
        sessions = LearningSession.query.join(ExchangeRequest).filter(
            or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id)
        ).order_by(LearningSession.starts_at).all()
        participant_ids = {
            participant_id
            for exchange in schedulable
            for participant_id in (exchange.sender_id, exchange.receiver_id)
        }
        available_slots = AvailabilitySlot.query.filter(
            AvailabilitySlot.user_id.in_(participant_ids or {-1}),
            AvailabilitySlot.is_active.is_(True),
            AvailabilitySlot.starts_at > datetime.now(),
        ).order_by(AvailabilitySlot.starts_at).all()
        pending_changes = SessionChangeProposal.query.join(LearningSession).join(
            ExchangeRequest
        ).filter(
            SessionChangeProposal.status == "Pending",
            or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id),
        ).order_by(SessionChangeProposal.created_at.desc()).all()
        return render_template(
            "sessions.html", schedulable=schedulable, sessions=sessions,
            available_slots=available_slots, pending_changes=pending_changes,
        )

    @app.route("/calendar")
    @login_required
    def calendar():
        user = current_user()
        today = datetime.now()
        end_date = today + timedelta(days=30)
        events = LearningSession.query.join(ExchangeRequest).filter(
            LearningSession.status == "Scheduled",
            LearningSession.starts_at >= today,
            LearningSession.starts_at < end_date,
            or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id),
        ).order_by(LearningSession.starts_at).all()
        return render_template("calendar.html", events=events, today=today, end_date=end_date)

    @app.route("/sessions/<int:session_id>/reschedule", methods=["POST"])
    @login_required
    def propose_reschedule(session_id):
        learning_session = db.session.get(LearningSession, session_id)
        if not learning_session:
            abort(404)
        user = current_user()
        exchange = learning_session.exchange_request
        if user.id not in (exchange.sender_id, exchange.receiver_id):
            abort(403)
        if learning_session.status != "Scheduled":
            abort(403)
        try:
            starts = datetime.strptime(request.form.get("starts_at", ""), "%Y-%m-%dT%H:%M")
            ends = datetime.strptime(request.form.get("ends_at", ""), "%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            flash("Enter valid proposed dates and times.", "error")
            return redirect(url_for("sessions_list"))
        location = request.form.get("location", "").strip()
        if starts <= datetime.now() or ends <= starts or not location or len(location) > 200:
            flash("Choose a future start, a later end, and a valid location.", "error")
        elif SessionChangeProposal.query.filter_by(
            session_id=learning_session.id, status="Pending"
        ).first():
            flash("A rescheduling proposal is already waiting for a response.", "error")
        else:
            db.session.add(SessionChangeProposal(
                session_id=learning_session.id, proposer_id=user.id,
                starts_at=starts, ends_at=ends, location=location,
            ))
            other_id = exchange.receiver_id if user.id == exchange.sender_id else exchange.sender_id
            db.session.add(Notification(
                user_id=other_id,
                message=f"{user.full_name} proposed a new time for your session.",
            ))
            db.session.commit()
            flash("Rescheduling proposal sent. The other student must accept it.", "success")
        return redirect(url_for("sessions_list"))

    @app.route("/session-changes/<int:proposal_id>/action", methods=["POST"])
    @login_required
    def session_change_action(proposal_id):
        proposal = db.session.get(SessionChangeProposal, proposal_id)
        if not proposal:
            abort(404)
        user = current_user()
        exchange = proposal.learning_session.exchange_request
        action = request.form.get("action")
        is_participant = user.id in (exchange.sender_id, exchange.receiver_id)
        if (not is_participant or proposal.status != "Pending"
                or proposal.learning_session.status != "Scheduled"):
            abort(403)
        if action == "cancel" and proposal.proposer_id == user.id:
            proposal.status = "Cancelled"
        elif action in ("accept", "reject") and proposal.proposer_id != user.id:
            if action == "accept":
                other_scheduled_session = LearningSession.query.join(ExchangeRequest).filter(
                    LearningSession.id != proposal.learning_session.id,
                    LearningSession.status == "Scheduled",
                    LearningSession.starts_at < proposal.ends_at,
                    LearningSession.ends_at > proposal.starts_at,
                    or_(
                        ExchangeRequest.sender_id.in_((exchange.sender_id, exchange.receiver_id)),
                        ExchangeRequest.receiver_id.in_((exchange.sender_id, exchange.receiver_id)),
                    ),
                ).first()
                if other_scheduled_session:
                    flash("That time now conflicts with another scheduled session.", "error")
                    return redirect(url_for("sessions_list"))
                learning_session = proposal.learning_session
                learning_session.starts_at = proposal.starts_at
                learning_session.ends_at = proposal.ends_at
                learning_session.location = proposal.location
                proposal.status = "Accepted"
            else:
                proposal.status = "Rejected"
        else:
            abort(403)
        other_id = exchange.receiver_id if user.id == exchange.sender_id else exchange.sender_id
        db.session.add(Notification(
            user_id=other_id, message=f"A session time proposal was {proposal.status.lower()}."
        ))
        db.session.commit()
        flash(f"Rescheduling proposal {proposal.status.lower()}.", "success")
        return redirect(url_for("sessions_list"))

    @app.route("/sessions/<int:session_id>/status", methods=["POST"])
    @login_required
    def session_status(session_id):
        learning_session = db.session.get(LearningSession, session_id)
        if not learning_session:
            abort(404)
        exchange = learning_session.exchange_request
        if current_user().id not in (exchange.sender_id, exchange.receiver_id):
            abort(403)
        new_status = request.form.get("status")
        if learning_session.status != "Scheduled" or new_status not in ("Completed", "Cancelled"):
            abort(403)
        learning_session.status = new_status
        if new_status == "Completed":
            exchange.status = "Completed"
        else:
            exchange.status = "Cancelled"
        pending_proposals = SessionChangeProposal.query.filter_by(
            session_id=learning_session.id, status="Pending"
        ).all()
        for proposal in pending_proposals:
            proposal.status = "Cancelled"
        other_id = exchange.receiver_id if current_user().id == exchange.sender_id else exchange.sender_id
        db.session.add(Notification(user_id=other_id, message=f"A learning session was marked {new_status.lower()}."))
        db.session.commit()
        flash(f"Session marked {new_status.lower()}.", "success")
        return redirect(url_for("sessions_list"))

    @app.route("/notifications", methods=["GET", "POST"])
    @login_required
    def notifications():
        if request.method == "POST":
            try:
                notification_id = int(request.form.get("notification_id", ""))
            except ValueError:
                abort(400)
            notification = db.session.get(Notification, notification_id)
            if not notification or notification.user_id != current_user().id:
                abort(404)
            notification.is_read = True
            db.session.commit()
            return redirect(url_for("notifications"))
        items = Notification.query.filter_by(user_id=current_user().id).order_by(
            Notification.created_at.desc()
        ).all()
        return render_template("notifications.html", items=items)

    @app.route("/reviews", methods=["GET", "POST"])
    @login_required
    def reviews():
        user = current_user()
        if request.method == "POST":
            try:
                session_id = int(request.form.get("session_id", ""))
                rating = int(request.form.get("rating", ""))
            except ValueError:
                abort(400)
            text = request.form.get("review_text", "").strip()
            learning_session = db.session.get(LearningSession, session_id)
            if (not learning_session or learning_session.status != "Completed"
                    or user.id not in (
                        learning_session.exchange_request.sender_id,
                        learning_session.exchange_request.receiver_id,
                    )):
                abort(403)
            if rating not in range(1, 6) or len(text) > 1000:
                flash("Choose a rating from 1 to 5 and keep the review under 1000 characters.", "error")
            elif Review.query.filter_by(session_id=session_id, reviewer_id=user.id).first():
                flash("You have already reviewed this session.", "error")
            else:
                db.session.add(Review(
                    session_id=session_id, reviewer_id=user.id,
                    rating=rating, review_text=text,
                ))
                db.session.commit()
                flash("Thank you for your feedback.", "success")
                return redirect(url_for("reviews"))
        sessions = LearningSession.query.join(ExchangeRequest).filter(
            LearningSession.status == "Completed",
            or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id),
        ).all()
        reviews_received = Review.query.join(LearningSession).join(ExchangeRequest).filter(
            or_(ExchangeRequest.sender_id == user.id, ExchangeRequest.receiver_id == user.id),
            Review.reviewer_id != user.id,
        ).order_by(Review.created_at.desc()).all()
        return render_template("reviews.html", sessions=sessions, reviews_received=reviews_received, user_id=user.id)

    @app.route("/reports/new/<int:user_id>", methods=["POST"])
    @login_required
    def report_user(user_id):
        reason = request.form.get("reason", "").strip()
        reported = db.session.get(User, user_id)
        if not reported or reported.id == current_user().id:
            abort(404)
        if not reason or len(reason) > 500:
            flash("Enter a reason of up to 500 characters.", "error")
        else:
            db.session.add(Report(
                reporter_id=current_user().id, reported_user_id=user_id, reason=reason,
            ))
            db.session.commit()
            flash("Report submitted for administrator review.", "success")
        return redirect(request.referrer or url_for("explore"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        popular_skills = db.session.query(
            Skill.name, func.count(func.distinct(UserSkill.user_id)).label("student_count")
        ).join(UserSkill, UserSkill.skill_id == Skill.id).join(
            User, User.id == UserSkill.user_id
        ).filter(
            Skill.is_active.is_(True), User.is_active.is_(True)
        ).group_by(Skill.id, Skill.name).order_by(
            func.count(func.distinct(UserSkill.user_id)).desc(), Skill.name
        ).limit(5).all()
        review_count, average_rating = db.session.query(
            func.count(Review.id), func.avg(Review.rating)
        ).one()
        return render_template(
            "admin.html",
            user_count=User.query.filter_by(role="student").count(),
            active_user_count=User.query.filter_by(role="student", is_active=True).count(),
            skill_count=Skill.query.count(),
            request_count=ExchangeRequest.query.count(),
            pending_count=ExchangeRequest.query.filter_by(status="Pending").count(),
            accepted_count=ExchangeRequest.query.filter_by(status="Accepted").count(),
            completed_count=LearningSession.query.filter_by(status="Completed").count(),
            open_reports=Report.query.filter_by(status="Open").count(),
            review_count=review_count,
            average_rating=round(average_rating, 1) if average_rating else None,
            popular_skills=popular_skills,
        )

    @app.route("/admin/users", methods=["GET", "POST"])
    @admin_required
    def admin_users():
        if request.method == "POST":
            try:
                user_id = int(request.form.get("user_id", ""))
            except ValueError:
                abort(400)
            target = db.session.get(User, user_id)
            if not target or target.id == current_user().id or target.role == "admin":
                abort(403)
            target.is_active = not target.is_active
            db.session.commit()
            flash("Student account status updated.", "success")
            return redirect(url_for("admin_users"))
        query = request.args.get("q", "").strip()
        listing = User.query.filter_by(role="student")
        if query:
            listing = listing.filter(or_(
                User.full_name.ilike(f"%{query}%"), User.email.ilike(f"%{query}%")
            ))
        return render_template("admin_users.html", users=listing.order_by(User.full_name).all(), query=query)

    @app.route("/admin/skills", methods=["GET", "POST"])
    @admin_required
    def admin_skills():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "toggle":
                try:
                    skill_id = int(request.form.get("skill_id", ""))
                except ValueError:
                    abort(400)
                skill = db.session.get(Skill, skill_id)
                if not skill:
                    abort(404)
                skill.is_active = not skill.is_active
                db.session.commit()
                flash("Skill availability updated.", "success")
                return redirect(url_for("admin_skills"))
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            if not name or not category or len(name) > 100 or len(category) > 80:
                flash("Enter a skill name and category within the length limits.", "error")
            elif Skill.query.filter(func.lower(Skill.name) == name.lower()).first():
                flash("That skill already exists.", "error")
            else:
                db.session.add(Skill(name=name, category=category))
                db.session.commit()
                flash("Skill added to the directory.", "success")
                return redirect(url_for("admin_skills"))
        return render_template("admin_skills.html", skills=Skill.query.order_by(Skill.category, Skill.name).all())

    @app.route("/admin/requests")
    @admin_required
    def admin_requests():
        items = ExchangeRequest.query.order_by(ExchangeRequest.created_at.desc()).all()
        return render_template("admin_requests.html", items=items)

    @app.route("/admin/reports", methods=["GET", "POST"])
    @admin_required
    def admin_reports():
        if request.method == "POST":
            try:
                report_id = int(request.form.get("report_id", ""))
            except ValueError:
                abort(400)
            report = db.session.get(Report, report_id)
            status = request.form.get("status")
            if not report or report.status != "Open" or status not in ("Reviewed", "Dismissed"):
                abort(403)
            report.status = status
            db.session.commit()
            flash("Report status updated.", "success")
            return redirect(url_for("admin_reports"))
        return render_template(
            "admin_reports.html",
            reports=Report.query.order_by(Report.created_at.desc()).all(),
        )

    @app.cli.command("init-db")
    def init_db():
        """Create tables and seed the skill directory."""
        db.create_all()
        for name, category in SKILL_DIRECTORY:
            if not Skill.query.filter(func.lower(Skill.name) == name.lower()).first():
                db.session.add(Skill(name=name, category=category))
        db.session.commit()
        print("Database initialized and skill directory verified.")

    @app.cli.command("create-admin")
    def create_admin():
        """Create the first administrator from environment variables."""
        name = os.environ.get("ADMIN_NAME", "").strip()
        email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not name or not valid_email(email) or len(password) < 12:
            raise RuntimeError(
                "Set ADMIN_NAME, a valid ADMIN_EMAIL, and an ADMIN_PASSWORD of at least 12 characters."
            )
        if User.query.filter_by(role="admin").first():
            raise RuntimeError("An administrator account already exists.")
        if User.query.filter(func.lower(User.email) == email).first():
            raise RuntimeError("An account with that email already exists.")
        admin = User(
            full_name=name, email=email, password_hash="",
            college="Platform Administration", department="Administration",
            semester=1, role="admin",
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"Administrator account created for {email}.")

    def current_user():
        user_id = session.get("user_id")
        return db.session.get(User, user_id) if user_id else None

    return app
