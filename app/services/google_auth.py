"""One-time Google Calendar OAuth2 setup. Run: python -m app.services.google_auth"""

from google_auth_oauthlib.flow import InstalledAppFlow
from app.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main():
    if not GOOGLE_CREDENTIALS_FILE.exists():
        print(f"Missing credentials file: {GOOGLE_CREDENTIALS_FILE}")
        print("Copy credentials.json from Google Cloud Console to that path.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    GOOGLE_TOKEN_FILE.write_text(creds.to_json())
    print(f"Token saved to {GOOGLE_TOKEN_FILE}")
    print("Google Calendar is now configured for PAM.")


if __name__ == "__main__":
    main()
