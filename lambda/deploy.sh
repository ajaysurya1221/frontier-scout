#!/usr/bin/env bash
# Deploy the Frontier Scout Slack interactivity Lambda.
#
# Runs locally (with AWS credentials in env) or in the `deploy-lambda` custom
# GitHub Actions workflow (credentials from repository secrets).
#
# Required env:
#   AWS_REGION            — e.g. us-east-1
#   LAMBDA_FUNCTION_NAME  — e.g. frontier-scout-slack
#
# Optional:
#   PYTHON_BIN            — defaults to python3.11 to match Lambda runtime

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
AWS_REGION="${AWS_REGION:?must set AWS_REGION}"
LAMBDA_FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:?must set LAMBDA_FUNCTION_NAME}"

LAMBDA_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$(mktemp -d)"
ZIP_PATH="${BUILD_DIR}/lambda.zip"

echo "→ Building Lambda zip at ${ZIP_PATH}"

# Install dependencies into the build dir (Lambda needs them bundled)
pip install \
    --target "${BUILD_DIR}/pkg" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    -r "${LAMBDA_DIR}/requirements.txt"

# Copy our handler code on top
cp "${LAMBDA_DIR}"/*.py "${BUILD_DIR}/pkg/"

# Zip everything (cd into pkg/ so paths inside the zip are relative)
(cd "${BUILD_DIR}/pkg" && zip -qr "${ZIP_PATH}" .)

SIZE_MB=$(du -m "${ZIP_PATH}" | cut -f1)
echo "→ Built zip: ${SIZE_MB} MB"

# Lambda has a 50MB direct-upload limit; >50MB requires S3 upload + reference.
if [ "${SIZE_MB}" -gt 50 ]; then
    echo "Zip exceeds 50MB; uploading via S3 instead..."
    : "${LAMBDA_DEPLOY_BUCKET:?must set LAMBDA_DEPLOY_BUCKET when zip > 50MB}"
    S3_KEY="lambda-deploy/$(date +%Y%m%d-%H%M%S).zip"
    aws s3 cp "${ZIP_PATH}" "s3://${LAMBDA_DEPLOY_BUCKET}/${S3_KEY}" --region "${AWS_REGION}"
    aws lambda update-function-code \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --s3-bucket "${LAMBDA_DEPLOY_BUCKET}" \
        --s3-key "${S3_KEY}" \
        --region "${AWS_REGION}"
else
    aws lambda update-function-code \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --zip-file "fileb://${ZIP_PATH}" \
        --region "${AWS_REGION}"
fi

echo "✅ Deployed to ${LAMBDA_FUNCTION_NAME} in ${AWS_REGION}"
rm -rf "${BUILD_DIR}"
