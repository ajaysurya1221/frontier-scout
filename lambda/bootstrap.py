"""
One-time S3 bucket bootstrap for the Slack interactivity Lambda.

Invoked via direct AWS Lambda invocation (NOT the Function URL) — payload:

    {"action": "bootstrap", "bucket": "frontier-scout-mirror"}

Requires temporary elevated S3 permissions on the Lambda's execution role:

    s3:CreateBucket, s3:PutBucketVersioning, s3:PutBucketEncryption,
    s3:PutBucketPublicAccessBlock, s3:HeadBucket

PRODUCTION GUIDANCE — DO NOT KEEP BROAD PERMISSIONS PERMANENTLY:

  1. Bootstrap-time role:   broad S3 for the duration of the bootstrap invoke.
                            One-time. Attach via a temporary inline policy.
  2. Runtime role:          read-only S3 on the mirror prefix only.
                            Use this for all subsequent Slack interactivity calls.

The simplest pattern: bootstrap with a privileged role, then immediately
update the Lambda execution role to the runtime read-only role:

    aws lambda update-function-configuration \
        --function-name frontier-scout-slack \
        --role arn:aws:iam::ACCOUNT:role/frontier-scout-slack-runtime

SECURITY.md "Operator runbook" documents both roles and the swap.

Idempotent on re-invoke — bucket-already-exists is reported, not an error.
"""

from __future__ import annotations

import json
import os


def handle(event: dict) -> dict:
    """Direct-invocation entry point. Returns a plain dict (no HTTP framing)."""
    action = event.get("action")
    if action != "bootstrap":
        return {"ok": False, "error": f"unknown action: {action!r}"}

    bucket = event.get("bucket") or os.environ.get("S3_MIRROR_BUCKET", "").strip()
    if not bucket:
        return {"ok": False, "error": "bucket name required (event.bucket or S3_MIRROR_BUCKET env)"}

    region = event.get("region") or os.environ.get("AWS_REGION", "us-east-2")

    try:
        import boto3  # type: ignore
        from botocore.exceptions import ClientError  # type: ignore
    except ImportError:
        return {"ok": False, "error": "boto3 unavailable in runtime"}

    s3 = boto3.client("s3", region_name=region)
    log: list[str] = []

    # 1. Create the bucket (idempotent — handle BucketAlreadyOwnedByYou)
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        log.append(f"✅ created bucket {bucket} in {region}")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            log.append(f"ℹ️  bucket {bucket} already exists (owned by this account)")
        else:
            return {"ok": False, "error": f"create_bucket failed: {code}: {e}"}

    # 2. Block all public access (defense in depth)
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        log.append("✅ public access blocked")
    except ClientError as e:
        log.append(f"⚠️  put_public_access_block failed: {e}")

    # 3. Enable versioning
    try:
        s3.put_bucket_versioning(
            Bucket=bucket,
            VersioningConfiguration={"Status": "Enabled"},
        )
        log.append("✅ versioning enabled")
    except ClientError as e:
        log.append(f"⚠️  put_bucket_versioning failed: {e}")

    # 4. Enable AES-256 server-side encryption
    try:
        s3.put_bucket_encryption(
            Bucket=bucket,
            ServerSideEncryptionConfiguration={
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}],
            },
        )
        log.append("✅ AES-256 SSE enabled")
    except ClientError as e:
        log.append(f"⚠️  put_bucket_encryption failed: {e}")

    # 5. Confirm
    try:
        s3.head_bucket(Bucket=bucket)
        log.append(f"✅ head_bucket OK — {bucket} is ready")
    except ClientError as e:
        return {"ok": False, "error": f"head_bucket failed: {e}", "log": log}

    return {
        "ok": True,
        "bucket": bucket,
        "region": region,
        "log": log,
        "next_step": (
            "Set S3_MIRROR_BUCKET=" + bucket + " on the Lambda + in GitHub Actions "
            "Repository Variables. Trigger one Scout run; aws s3 sync will "
            "populate the mirror; /recall will start returning semantic results."
        ),
    }
