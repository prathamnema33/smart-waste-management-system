"""Authentication and development operations-account tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")

from fastapi import HTTPException
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auth import ALGORITHM, SECRET_KEY, require_role, require_roles
from main import create_user, login
from models import User, Worker
from schemas import LoginRequest, UserCreate
from seed_data import (
    DEVELOPMENT_PASSWORD_CONTEXT,
    ensure_development_operations_account,
)


class OperationsAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        User.__table__.create(self.engine)
        Worker.__table__.create(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def make_user(self, role: str, user_id: int = 1) -> User:
        return User(
            user_id=user_id,
            name="Test Account",
            email=f"{role.lower()}@example.test",
            password_hash=DEVELOPMENT_PASSWORD_CONTEXT.hash("TestPassword123!"),
            role=role,
        )

    def test_admin_is_allowed_on_monitor_only_routes(self) -> None:
        admin = self.make_user("ADMIN")
        require_role("MONITOR")(admin)
        require_roles("WORKER", "MONITOR")(admin)

    def test_worker_and_citizen_are_denied_from_monitor_routes(self) -> None:
        for role in ("WORKER", "CITIZEN"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    require_role("MONITOR")(self.make_user(role))
                self.assertEqual(raised.exception.status_code, 403)

    def test_login_accepts_email_and_user_id(self) -> None:
        account = self.make_user("ADMIN", user_id=23)
        worker_account = self.make_user("WORKER", user_id=1042)
        worker = Worker(worker_id=13, user_id=worker_account.user_id, assigned_area=1)
        self.db.add(account)
        self.db.add(worker_account)
        self.db.add(worker)
        self.db.commit()

        for credentials in (
            LoginRequest(email=account.email, password="TestPassword123!"),
            LoginRequest(user_id=account.user_id, password="TestPassword123!"),
            LoginRequest(identifier=str(account.user_id), password="TestPassword123!"),
            LoginRequest(worker_id=worker.worker_id, password="TestPassword123!"),
            LoginRequest(identifier=f"W:{worker.worker_id}", password="TestPassword123!"),
        ):
            with self.subTest(credentials=credentials):
                response = login(credentials, self.db)
                payload = jwt.decode(
                    response["access_token"],
                    SECRET_KEY,
                    algorithms=[ALGORITHM],
                )
                expected_user = (
                    worker_account
                    if credentials.worker_id is not None
                    or credentials.identifier == f"W:{worker.worker_id}"
                    else account
                )
                self.assertEqual(payload["user_id"], expected_user.user_id)
                self.assertEqual(payload["role"], expected_user.role)

    def test_login_accepts_worker_id(self) -> None:
        account = self.make_user("WORKER", user_id=1042)
        self.db.add(account)
        self.db.add(Worker(worker_id=13, user_id=account.user_id, assigned_area=1))
        self.db.commit()

        response = login(
            LoginRequest(worker_id=13, password="TestPassword123!"),
            self.db,
        )
        payload = jwt.decode(
            response["access_token"],
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        self.assertEqual(payload["user_id"], account.user_id)
        self.assertEqual(payload["role"], "WORKER")

    def test_public_user_creation_cannot_grant_operations_roles(self) -> None:
        for role in ("ADMIN", "MONITOR"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    create_user(
                        UserCreate(
                            name="Unprivileged User",
                            email=f"{role.lower()}@example.test",
                            password="UserPassword123!",
                            role=role,
                        ),
                        self.db,
                    )
                self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.db.query(User).count(), 0)

    def test_development_seed_hashes_password_and_is_idempotent(self) -> None:
        email = "operations@example.test"
        password = "UniqueTestPassword123!"
        with patch.dict(
            os.environ,
            {
                "MONITOR_ADMIN_EMAIL": email,
                "MONITOR_ADMIN_PASSWORD": password,
                "MONITOR_ADMIN_ROLE": "MONITOR",
            },
            clear=True,
        ):
            self.assertTrue(ensure_development_operations_account(self.db))
            seeded = self.db.query(User).filter(User.email == email).one()
            self.assertEqual(seeded.role, "MONITOR")
            self.assertNotEqual(seeded.password_hash, password)
            self.assertTrue(
                DEVELOPMENT_PASSWORD_CONTEXT.verify(password, seeded.password_hash)
            )
            self.assertFalse(ensure_development_operations_account(self.db))
            self.assertEqual(self.db.query(User).count(), 1)

    def test_development_seed_does_not_promote_existing_non_operations_user(self) -> None:
        self.db.add(self.make_user("CITIZEN"))
        self.db.commit()
        with patch.dict(
            os.environ,
            {
                "MONITOR_ADMIN_EMAIL": "citizen@example.test",
                "MONITOR_ADMIN_PASSWORD": "UniqueTestPassword123!",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                ensure_development_operations_account(self.db)
        self.assertEqual(self.db.query(User).count(), 1)
        self.assertEqual(self.db.query(User).one().role, "CITIZEN")


if __name__ == "__main__":
    unittest.main()
