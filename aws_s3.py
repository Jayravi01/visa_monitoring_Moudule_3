"""Create the S3 bucket (if needed) and upload new JSON Lines files.

Only real (live) data is uploaded; the synthetic sample store is never touched.
Keys mirror the local layout:  s3://<bucket>/<S3_PREFIX>/dt=YYYY-MM-DD/changes_HHMMSS.jsonl
"""
import boto3
from botocore.exceptions import ClientError

import config


def ensure_bucket(s3) -> None:
    try:
        s3.head_bucket(Bucket=config.S3_BUCKET)
        print(f"Bucket exists: {config.S3_BUCKET}")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise  # 403 means the name belongs to someone else

    kwargs = {"Bucket": config.S3_BUCKET}
    if config.REGION != "us-east-1":  # us-east-1 must not send a LocationConstraint
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": config.REGION}
    s3.create_bucket(**kwargs)
    s3.put_public_access_block(
        Bucket=config.S3_BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print(f"Created private bucket: {config.S3_BUCKET}")


def _exists(s3, key: str) -> bool:
    try:
        s3.head_object(Bucket=config.S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def sync_to_s3() -> int:
    """Upload every local live JSONL file that is not in S3 yet. Returns the number uploaded."""
    config.require_aws_settings()
    s3 = boto3.client("s3", region_name=config.REGION)
    ensure_bucket(s3)

    uploaded = 0
    for path in sorted(config.LIVE_DIR.glob("dt=*/*.jsonl")):
        key = f"{config.S3_PREFIX}/{path.parent.name}/{path.name}"
        if _exists(s3, key):
            continue
        s3.upload_file(str(path), config.S3_BUCKET, key)
        uploaded += 1
        print(f"  uploaded s3://{config.S3_BUCKET}/{key}")
    print(f"Synced {uploaded} new file(s)")
    return uploaded


if __name__ == "__main__":
    sync_to_s3()
