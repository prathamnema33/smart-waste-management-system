"""Public, read-only demonstration account definitions."""

from dataclasses import dataclass


DEMO_EMAIL_DOMAIN = "demo.invalid"


@dataclass(frozen=True)
class DemoAccount:
    identifier: str
    name: str
    role: str
    password: str

    @property
    def email(self) -> str:
        return f"{self.identifier}@{DEMO_EMAIL_DOMAIN}"


DEMO_ACCOUNTS = (
    DemoAccount("demo_admin", "Admin Demo", "ADMIN", "Admin@Demo2026!"),
    DemoAccount("demo_monitor", "Monitoring Demo", "MONITOR", "Monitor@Demo2026!"),
    DemoAccount("demo_worker", "Worker Demo", "WORKER", "Worker@Demo2026!"),
    DemoAccount("demo_citizen", "Citizen Demo", "CITIZEN", "Citizen@Demo2026!"),
)

DEMO_ACCOUNT_EMAILS = frozenset(account.email for account in DEMO_ACCOUNTS)


def is_demo_email(email: str) -> bool:
    return email.casefold() in DEMO_ACCOUNT_EMAILS
