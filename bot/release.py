"""Release metadata and lightweight runtime information for Rooze Ziba."""
APP_NAME = "Rooze Ziba / ALIMJ"
VERSION = "30.5.11"
RELEASE_CHANNEL = "production"


def version_string() -> str:
    return f"{APP_NAME} {VERSION} ({RELEASE_CHANNEL})"
