from getpass import getpass

from passlib.context import CryptContext


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def main():
    password = getpass("Enter password: ")

    if not password:
        print("Error: password cannot be empty.")
        return

    hashed_password = pwd_context.hash(password)

    print("\nPassword Hash:")
    print(hashed_password)


if __name__ == "__main__":
    main()
