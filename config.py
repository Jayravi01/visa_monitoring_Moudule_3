"""Central configuration, read from environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LIVE_DIR = DATA_DIR / "live"          # real collected records (JSON Lines, partitioned by dt=)
SAMPLE_DIR = DATA_DIR / "sample"      # synthetic demo records, never uploaded to AWS
SNAPSHOT_DIR = DATA_DIR / "snapshots" # page hashes for change detection
REPORT_DIR = BASE_DIR / "reports"

USER_AGENT = os.getenv(
    "USER_AGENT",
    "OSHC-Capstone-Visa-Monitor/0.1 (university project; set USER_AGENT in .env)",
)
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "2"))
ROBOTS_FAIL_OPEN = os.getenv("ROBOTS_FAIL_OPEN", "false").lower() == "true"

REGION = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "visa_changes")
ATHENA_DATABASE = os.getenv("ATHENA_DATABASE", "dashboard_db")
ATHENA_TABLE = os.getenv("ATHENA_TABLE", "visa_changes")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT", f"s3://{S3_BUCKET}/athena-results/")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")  # alternative to the file (CI)

SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")


def require_aws_settings() -> None:
    if not S3_BUCKET:
        raise SystemExit("S3_BUCKET is not set. Copy .env.example to .env and fill it in.")
