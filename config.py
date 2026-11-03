import os
import re
from dotenv import load_dotenv

load_dotenv()

PLATFORM_FEE_PERCENT = float(os.getenv("PLATFORM_FEE_PERCENT", "0.10"))
PLATFORM_TREASURY_EMAIL = os.getenv("PLATFORM_TREASURY_EMAIL", "treasury@milestoneescrow.com")


def validate_config():
    """
    Validates that essential platform settings are set and valid.
    """
    email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not PLATFORM_TREASURY_EMAIL or not re.match(email_regex, PLATFORM_TREASURY_EMAIL):
        raise ValueError(
            f"PLATFORM_TREASURY_EMAIL must be set to a valid email address. Received: '{PLATFORM_TREASURY_EMAIL}'"
        )
    if PLATFORM_FEE_PERCENT < 0 or PLATFORM_FEE_PERCENT > 1:
        raise ValueError(f"PLATFORM_FEE_PERCENT must be between 0.0 and 1.0. Received: {PLATFORM_FEE_PERCENT}")


# Run validation on module import
validate_config()

