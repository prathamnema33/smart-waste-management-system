"""Create or refresh only the four public demonstration accounts.

Run from the backend directory with:
    python seed_demo_accounts.py

This command never deletes records or changes accounts outside the fixed demo
email addresses. Demo account passwords are stored as bcrypt hashes.
"""

from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import SessionLocal
from demo_accounts import DEMO_ACCOUNTS
from models import User


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def ensure_demo_accounts(db: Session) -> tuple[int, int]:
    created = 0
    updated = 0

    for account in DEMO_ACCOUNTS:
        user = db.query(User).filter(User.email == account.email).first()
        if user is None:
            db.add(
                User(
                    name=account.name,
                    email=account.email,
                    password_hash=password_context.hash(account.password),
                    role=account.role,
                    created_at=datetime.now(),
                )
            )
            created += 1
            continue

        if user.role != account.role:
            raise RuntimeError(
                f"Refusing to change role for the reserved demo ID "
                f"{account.identifier}."
            )

        if not password_context.verify(account.password, user.password_hash):
            user.password_hash = password_context.hash(account.password)
            updated += 1

    db.commit()
    return created, updated


def main() -> None:
    db = SessionLocal()
    try:
        created, updated = ensure_demo_accounts(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        f"Demo account setup complete: {created} created, {updated} password "
        "hashes refreshed. No other accounts or records were changed."
    )


if __name__ == "__main__":
    main()
