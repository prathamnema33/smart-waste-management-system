"""Public demo account seeding and access-control tests."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")

from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth import ALGORITHM, SECRET_KEY
from database import get_db
from demo_accounts import DEMO_ACCOUNTS
from main import app
from models import User
from seed_demo_accounts import ensure_demo_accounts, password_context


class DemoAccountTests(unittest.TestCase):
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
        with Session(self.engine) as db:
            ensure_demo_accounts(db)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()

    def test_seed_creates_hashed_accounts_and_is_idempotent(self) -> None:
        with Session(self.engine) as db:
            users = db.query(User).all()
            self.assertEqual(len(users), 4)
            for account in DEMO_ACCOUNTS:
                user = db.query(User).filter(User.email == account.email).one()
                self.assertEqual(user.role, account.role)
                self.assertNotEqual(user.password_hash, account.password)
                self.assertTrue(
                    password_context.verify(account.password, user.password_hash)
                )
            self.assertEqual(ensure_demo_accounts(db), (0, 0))
            self.assertEqual(db.query(User).count(), 4)

    def test_each_public_identifier_logs_in_with_expected_role(self) -> None:
        for account in DEMO_ACCOUNTS:
            with self.subTest(role=account.role):
                response = self.client.post(
                    "/login",
                    json={"email": account.identifier, "password": account.password},
                )
                self.assertEqual(response.status_code, 200)
                payload = jwt.decode(
                    response.json()["access_token"],
                    SECRET_KEY,
                    algorithms=[ALGORITHM],
                )
                self.assertEqual(payload["role"], account.role)
                self.assertTrue(payload["is_demo"])
                headers = {
                    "Authorization": f"Bearer {response.json()['access_token']}"
                }
                current_user = self.client.get("/users/me", headers=headers)
                self.assertEqual(current_user.status_code, 200)
                self.assertEqual(current_user.json()["role"], account.role)
                self.assertNotIn("password_hash", current_user.json())

    def test_demo_role_dashboard_routes_enforce_roles(self) -> None:
        endpoints = {
            "ADMIN": ("/admin/dashboard", "/monitor/dashboard"),
            "MONITOR": ("/monitor/dashboard",),
            "WORKER": ("/worker/dashboard",),
            "CITIZEN": ("/citizen/dashboard",),
        }
        for account in DEMO_ACCOUNTS:
            login = self.client.post(
                "/login",
                json={"email": account.identifier, "password": account.password},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            for path in (
                "/admin/dashboard",
                "/monitor/dashboard",
                "/worker/dashboard",
                "/citizen/dashboard",
            ):
                with self.subTest(role=account.role, path=path):
                    response = self.client.get(path, headers=headers)
                    if path in endpoints[account.role]:
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertEqual(response.status_code, 403)

    def test_demo_accounts_cannot_read_live_records_or_write(self) -> None:
        login = self.client.post(
            "/login",
            json={
                "email": "demo_admin",
                "password": "Admin@Demo2026!",
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        self.assertEqual(self.client.get("/users", headers=headers).status_code, 403)
        self.assertEqual(
            self.client.get("/monitor/complaints", headers=headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/users",
                headers=headers,
                json={
                    "name": "Unauthorized",
                    "email": "unauthorized@example.test",
                    "password": "RegistrationPass123!",
                    "role": "CITIZEN",
                },
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete("/users/1", headers=headers).status_code, 403)

    def test_reserved_demo_identifiers_cannot_be_claimed_by_public_signup(self) -> None:
        response = self.client.post(
            "/register",
            json={
                "name": "Someone Else",
                "email": "demo_admin@demo.invalid",
                "phone_number": "9876543210",
                "password": "RegistrationPass123!",
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_existing_account_with_reserved_demo_email_is_not_promoted(self) -> None:
        with Session(self.engine) as db:
            account = DEMO_ACCOUNTS[0]
            db.query(User).filter(User.email == account.email).delete()
            db.commit()
            db.add(
                User(
                    name="Existing Citizen",
                    email=account.email,
                    password_hash=password_context.hash("ExistingPassword123!"),
                    role="CITIZEN",
                )
            )
            db.commit()
            with self.assertRaises(RuntimeError):
                ensure_demo_accounts(db)
            self.assertEqual(db.query(User).filter(User.email == account.email).one().role, "CITIZEN")


if __name__ == "__main__":
    unittest.main()
