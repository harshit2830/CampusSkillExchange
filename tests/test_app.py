import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "04_Python"))

from skill_exchange.app import create_app, normalize_database_url
from skill_exchange.models import (
    AvailabilitySlot, DirectMessage, ExchangeRequest, LearningSession, Notification,
    Review, SavedSkill, SavedStudent, SessionChangeProposal, Skill, User,
    UserPreferences, UserSkill, db,
)


class CampusSkillExchangeTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-value-for-tests-32-chars",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": False,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.alice = self.make_user("Alice")
            self.bob = self.make_user("Bob")
            self.charlie = self.make_user("Charlie")
            self.python = Skill.query.filter_by(name="Python").one()
            self.design = Skill.query.filter_by(name="Graphic Design").one()
            db.session.add_all([
                UserSkill(user_id=self.alice.id, skill_id=self.python.id, skill_type="teach"),
                UserSkill(user_id=self.alice.id, skill_id=self.design.id, skill_type="learn"),
                UserSkill(user_id=self.bob.id, skill_id=self.design.id, skill_type="teach"),
                UserSkill(user_id=self.bob.id, skill_id=self.python.id, skill_type="learn"),
            ])
            db.session.commit()
            self.alice_id, self.bob_id, self.charlie_id = (
                self.alice.id, self.bob.id, self.charlie.id
            )
            self.python_id, self.design_id = self.python.id, self.design.id

    @staticmethod
    def make_user(name):
        user = User(
            full_name=name, email=f"{name.lower()}@college.example",
            password_hash="", college="Example College",
            department="Computer Science", semester=3,
        )
        user.set_password("password-for-tests")
        db.session.add(user)
        db.session.flush()
        return user

    def login_as(self, user_id):
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = user_id

    def test_home_and_protected_route(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        health = self.client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json, {"status": "ok"})
        self.assertEqual(health.headers["X-Content-Type-Options"], "nosniff")
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_railway_mysql_url_is_normalized_for_pymysql(self):
        self.assertEqual(
            normalize_database_url("mysql://user:password@db:3306/campus"),
            "mysql+pymysql://user:password@db:3306/campus",
        )
        self.assertEqual(
            normalize_database_url("mysql+pymysql://user:password@db/campus"),
            "mysql+pymysql://user:password@db/campus",
        )

    def test_railway_enables_secure_session_cookie_and_forwarded_proxy(self):
        with patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_NAME": "production"}):
            app = create_app({
                "TESTING": True,
                "SECRET_KEY": "test-only-secret-value-for-tests-32-chars",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "WTF_CSRF_ENABLED": False,
            })
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
        with app.test_client() as client:
            self.assertEqual(client.get("/healthz").status_code, 200)

    def test_registration_hashes_password_and_ignores_role_input(self):
        response = self.client.post("/register", data={
            "full_name": "New Student", "email": "new@college.example",
            "password": "a-strong-password", "confirm_password": "a-strong-password",
            "college": "Example College", "department": "Design", "semester": "2",
            "bio": "Learning every day.", "role": "admin",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(email="new@college.example").one()
            self.assertEqual(user.role, "student")
            self.assertTrue(user.check_password("a-strong-password"))
            self.assertNotEqual(user.password_hash, "a-strong-password")

    def test_matching_returns_mutual_score(self):
        self.login_as(self.alice_id)
        response = self.client.get("/matches")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Bob", response.data)
        self.assertIn(b"100/100", response.data)

    def test_student_pages_render(self):
        self.login_as(self.alice_id)
        for path in (
            "/dashboard", "/profile", "/profile/edit", "/skills", "/explore",
            "/matches", "/suggestions", "/saved", "/messages", "/requests",
            "/sessions", "/calendar", "/availability", "/notifications", "/reviews",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_exchange_requires_authorized_receiver_and_supports_review(self):
        self.login_as(self.alice_id)
        response = self.client.post(f"/requests/new/{self.bob_id}", data={
            "skill_offered_id": self.python_id,
            "skill_requested_id": self.design_id,
            "message": "Let us exchange skills.",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            exchange = ExchangeRequest.query.one()
            exchange_id = exchange.id
            notification_count = Notification.query.filter_by(user_id=self.bob_id).count()
            self.assertEqual(notification_count, 1)

        self.login_as(self.charlie_id)
        denied = self.client.post(
            f"/requests/{exchange_id}/action", data={"action": "accept"}
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.client.get(f"/requests/{exchange_id}").status_code, 403)

        self.login_as(self.alice_id)
        self.assertEqual(self.client.get(f"/requests/{exchange_id}").status_code, 200)
        self.login_as(self.bob_id)
        accepted = self.client.post(
            f"/requests/{exchange_id}/action", data={"action": "accept"}
        )
        self.assertEqual(accepted.status_code, 302)
        past_start = datetime.now() - timedelta(days=2)
        rejected_schedule = self.client.post("/sessions", data={
            "request_id": exchange_id,
            "starts_at": past_start.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (past_start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "location": "Library",
            "notes": "",
        })
        self.assertEqual(rejected_schedule.status_code, 200)
        self.assertIn(b"future start time", rejected_schedule.data)
        with self.app.app_context():
            self.assertEqual(LearningSession.query.count(), 0)
        starts = datetime.now() + timedelta(days=2)
        ends = starts + timedelta(hours=1)
        scheduled = self.client.post("/sessions", data={
            "request_id": exchange_id,
            "starts_at": starts.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": ends.strftime("%Y-%m-%dT%H:%M"),
            "location": "Library",
            "notes": "Bring a notebook.",
        })
        self.assertEqual(scheduled.status_code, 302)
        with self.app.app_context():
            learning_session = LearningSession.query.one()
            session_id = learning_session.id
        completed = self.client.post(
            f"/sessions/{session_id}/status", data={"status": "Completed"}
        )
        self.assertEqual(completed.status_code, 302)
        feedback = self.client.post("/reviews", data={
            "session_id": session_id, "rating": "5", "review_text": "Great session."
        })
        self.assertEqual(feedback.status_code, 302)
        duplicate = self.client.post("/reviews", data={
            "session_id": session_id, "rating": "4", "review_text": "Duplicate."
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn(b"already reviewed", duplicate.data)
        with self.app.app_context():
            self.assertEqual(Review.query.filter_by(session_id=session_id).count(), 1)
            self.assertEqual(db.session.get(ExchangeRequest, exchange_id).status, "Completed")

    def test_admin_routes_check_role_and_admin_can_monitor(self):
        self.login_as(self.alice_id)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        with self.app.app_context():
            administrator = self.make_user("Administrator")
            administrator.role = "admin"
            db.session.commit()
            administrator_id = administrator.id
        self.login_as(administrator_id)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.get("/admin/requests").status_code, 200)
        self.assertEqual(self.client.get("/admin/skills").status_code, 200)
        created_skill = self.client.post("/admin/skills", data={
            "name": "Digital Illustration", "category": "Digital Arts",
        })
        self.assertEqual(created_skill.status_code, 302)
        dashboard = self.client.get("/admin")
        self.assertIn(b"Popular skills", dashboard.data)
        self.assertEqual(self.client.get("/admin/reports").status_code, 200)

    def test_profile_preferences_discovery_and_skill_suggestions(self):
        self.login_as(self.alice_id)
        saved = self.client.post(f"/saved/students/{self.bob_id}")
        self.assertEqual(saved.status_code, 302)
        saved_skill = self.client.post(f"/saved/skills/{self.python_id}")
        self.assertEqual(saved_skill.status_code, 302)
        response = self.client.get("/saved")
        self.assertIn(b"Bob", response.data)
        self.assertIn(b"Python", response.data)
        self.assertEqual(self.client.get(f"/students/{self.alice_id}").status_code, 200)

        discovery = self.client.get("/explore?student=Bob&college=Example&sort=student")
        self.assertEqual(discovery.status_code, 200)
        self.assertIn(b"Graphic Design", discovery.data)
        self.assertNotIn(b"Charlie", discovery.data)
        suggestions = self.client.get("/suggestions")
        self.assertEqual(suggestions.status_code, 200)
        self.assertIn(b"directory guide", suggestions.data)

        edited = self.client.post("/profile/edit", data={
            "full_name": "Alice", "college": "Example College",
            "department": "Computer Science", "semester": "3",
            "bio": "Learning by sharing.", "campus_location": "North campus",
            "preferred_format": "Online", "languages": "English, Hindi",
            "availability_notes": "Evenings are best.",
        })
        self.assertEqual(edited.status_code, 302)
        with self.app.app_context():
            preferences = UserPreferences.query.filter_by(user_id=self.alice_id).one()
            self.assertEqual(preferences.preferred_format, "Online")
        profile = self.client.get("/profile")
        self.assertIn(b"North campus", profile.data)
        self.assertIn(b"English, Hindi", profile.data)

    def test_private_messages_and_saved_student_ownership(self):
        self.login_as(self.alice_id)
        self.client.post(f"/saved/students/{self.bob_id}")
        self.client.post(f"/saved/skills/{self.python_id}")
        sent = self.client.post(f"/messages/{self.bob_id}", data={
            "body": "Would you like to exchange Python and design lessons?"
        })
        self.assertEqual(sent.status_code, 302)
        with self.app.app_context():
            self.assertEqual(DirectMessage.query.count(), 1)
            self.assertEqual(Notification.query.filter_by(user_id=self.bob_id).count(), 1)
            self.assertEqual(SavedStudent.query.filter_by(
                user_id=self.alice_id, student_id=self.bob_id
            ).count(), 1)

        self.login_as(self.bob_id)
        inbox = self.client.get("/messages")
        self.assertIn(b"Alice", inbox.data)
        thread = self.client.get(f"/messages/{self.alice_id}")
        self.assertIn(b"Would you like to exchange", thread.data)
        with self.app.app_context():
            self.assertTrue(DirectMessage.query.one().is_read)

        self.login_as(self.charlie_id)
        private_thread = self.client.get(f"/messages/{self.alice_id}")
        self.assertEqual(private_thread.status_code, 200)
        self.assertNotIn(b"Would you like to exchange", private_thread.data)
        self.assertEqual(self.client.post(
            f"/saved/students/{self.charlie_id}"
        ).status_code, 404)
        with self.app.app_context():
            self.assertEqual(SavedSkill.query.filter_by(
                user_id=self.alice_id, skill_id=self.python_id
            ).count(), 1)
            self.assertEqual(SavedStudent.query.filter_by(
                user_id=self.alice_id, student_id=self.bob_id
            ).count(), 1)

    def test_shared_availability_scheduling_calendar_and_reschedule_approval(self):
        future_start = datetime.now() + timedelta(days=4)
        future_end = future_start + timedelta(hours=1)
        self.login_as(self.alice_id)
        created = self.client.post("/availability", data={
            "starts_at": future_start.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": future_end.strftime("%Y-%m-%dT%H:%M"),
            "note": "Study room available.",
        })
        self.assertEqual(created.status_code, 302)
        with self.app.app_context():
            slot = AvailabilitySlot.query.filter_by(user_id=self.alice_id).one()
            slot_id = slot.id
            exchange = ExchangeRequest(
                sender_id=self.alice_id, receiver_id=self.bob_id,
                skill_offered_id=self.python_id, skill_requested_id=self.design_id,
                status="Accepted",
            )
            db.session.add(exchange)
            db.session.commit()
            exchange_id = exchange.id
        self.login_as(self.bob_id)
        public_profile = self.client.get(f"/students/{self.alice_id}")
        self.assertIn(b"Study room available.", public_profile.data)
        scheduled = self.client.post("/sessions", data={
            "request_id": exchange_id,
            "availability_slot_id": str(slot_id),
            "location": "North campus library",
            "notes": "",
        })
        self.assertEqual(scheduled.status_code, 302)
        with self.app.app_context():
            slot = db.session.get(AvailabilitySlot, slot_id)
            self.assertFalse(slot.is_active)
            learning_session = LearningSession.query.one()
            session_id = learning_session.id
            overlapping_request = ExchangeRequest(
                sender_id=self.alice_id, receiver_id=self.charlie_id,
                skill_offered_id=self.python_id, skill_requested_id=self.design_id,
                status="Accepted",
            )
            db.session.add(overlapping_request)
            db.session.commit()
            overlapping_request_id = overlapping_request.id
        self.login_as(self.alice_id)
        overlap_response = self.client.post("/sessions", data={
            "request_id": overlapping_request_id,
            "starts_at": future_start.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": future_end.strftime("%Y-%m-%dT%H:%M"),
            "location": "Another campus room",
            "notes": "",
        })
        self.assertEqual(overlap_response.status_code, 200)
        self.assertIn(b"overlaps another session", overlap_response.data)
        with self.app.app_context():
            self.assertEqual(LearningSession.query.count(), 1)
        self.login_as(self.bob_id)
        calendar_view = self.client.get("/calendar")
        self.assertIn(b"North campus library", calendar_view.data)

        proposed_start = datetime.now() + timedelta(days=6)
        proposed_end = proposed_start + timedelta(hours=1)
        proposal_response = self.client.post(
            f"/sessions/{session_id}/reschedule", data={
                "starts_at": proposed_start.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": proposed_end.strftime("%Y-%m-%dT%H:%M"),
                "location": "Arts building",
            }
        )
        self.assertEqual(proposal_response.status_code, 302)
        with self.app.app_context():
            proposal = SessionChangeProposal.query.one()
            proposal_id = proposal.id
        self.login_as(self.charlie_id)
        denied_change = self.client.post(
            f"/session-changes/{proposal_id}/action", data={"action": "accept"}
        )
        self.assertEqual(denied_change.status_code, 403)
        self.login_as(self.alice_id)
        change_page = self.client.get("/sessions")
        self.assertIn(b"Arts building", change_page.data)
        accepted_change = self.client.post(
            f"/session-changes/{proposal_id}/action", data={"action": "accept"}
        )
        self.assertEqual(accepted_change.status_code, 302)
        with self.app.app_context():
            proposal = db.session.get(SessionChangeProposal, proposal_id)
            learning_session = db.session.get(LearningSession, session_id)
            self.assertEqual(proposal.status, "Accepted")
            self.assertEqual(learning_session.location, "Arts building")
            self.assertEqual(learning_session.starts_at, proposal.starts_at)


if __name__ == "__main__":
    unittest.main()
