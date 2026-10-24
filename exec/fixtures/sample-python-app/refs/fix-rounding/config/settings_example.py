"""Example settings (fixture). Credentials come from the environment, never from source."""

import os

AWS_REGION = "eu-central-1"
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
