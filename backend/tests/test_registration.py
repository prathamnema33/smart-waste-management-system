"""Public account registration API tests."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app, pwd_context
from models import User


class RegistrationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        User.__table__.create(self.engine)

        def override_get_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()

    @staticmethod
    def registration_payload(**overrides: str) -> dict[str, str]:
        payload = {
            "name": "New Citizen",
            "email": "New.Citizen@Example.test",
            "phone_number": "+91 (98765) 43210",
            "password": "RegistrationPass123!",
        }
        payload.update(overrides)
        return payload

    def test_registration_login_and_role_protected_routes(self) -> None:
        registration = self.client.post("/register", json=self.registration_payload())
        self.assertEqual(registration.status_code, 201)
        user_data = registration.json()
        self.assertEqual(user_data["role"], "CITIZEN")
        self.assertEqual(user_data["email"], "new.citizen@example.test")
        self.assertNotIn("password", user_data)
        self.assertNotIn("password_hash", user_data)

        with Session(self.engine) as db:
            account = db.query(User).one()
            self.assertEqual(account.phone_number, "+919876543210")
            self.assertTrue(
                pwd_context.verify("RegistrationPass123!", account.password_hash)
            )
            self.assertNotEqual(account.password_hash, "RegistrationPass123!")

        login = self.client.post(
            "/login",
            json={
                "email": "new.citizen@example.test",
                "identifier": "NEW.CITIZEN@EXAMPLE.TEST",
                "password": "RegistrationPass123!",
            },
        )
        self.assertEqual(login.status_code, 200)
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        self.assertEqual(self.client.get("/users/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/citizen/dashboard", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/worker/dashboard", headers=headers).status_code, 403)
        self.assertEqual(
            self.client.get("/monitor/monitoring", headers=headers).status_code,
            403,
        )
        self.assertIn(
            self.client.get("/monitor/monitoring").status_code,
            (401, 403),
        )

    def test_duplicate_email_is_rejected_case_insensitively(self) -> None:
        self.assertEqual(
            self.client.post("/register", json=self.registration_payload()).status_code,
            201,
        )
        duplicate = self.client.post(
            "/register",
            json=self.registration_payload(email="NEW.CITIZEN@EXAMPLE.TEST"),
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_invalid_email_and_phone_are_rejected(self) -> None:
        invalid_email = self.client.post(
            "/register",
            json=self.registration_payload(email="invalid-email"),
        )
        self.assertEqual(invalid_email.status_code, 422)

        invalid_phone = self.client.post(
            "/register",
            json=self.registration_payload(phone_number="123-45"),
        )
        self.assertEqual(invalid_phone.status_code, 422)

    def test_worker_and_operations_roles_cannot_be_self_registered(self) -> None:
        public_user_create = self.client.post(
            "/users",
            json={
                "name": "Worker User",
                "email": "worker@example.test",
                "password": "RegistrationPass123!",
                "role": "WORKER",
            },
        )
        self.assertIn(public_user_create.status_code, (401, 403))

        worker = self.client.post(
            "/register",
            json=self.registration_payload(role="WORKER"),
        )
        self.assertEqual(worker.status_code, 403)

        for role in ("ADMIN", "MONITOR"):
            with self.subTest(role=role):
                response = self.client.post(
                    "/register",
                    json=self.registration_payload(role=role),
                )
                self.assertEqual(response.status_code, 422)

        with Session(self.engine) as db:
            self.assertEqual(db.query(User).count(), 0)

    def test_registration_rejects_password_over_bcrypt_limit(self) -> None:
        response = self.client.post(
            "/register",
            json=self.registration_payload(password="é" * 37),
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
