"""API Gateway Lambda entrypoint for GitHub-style webhook ingestion.

The handler keeps the synchronous request path intentionally small: parse the
incoming webhook, capture stable routing metadata, and hand the full payload to
SQS for asynchronous processing.
"""

import base64
import json
import os
import time
import uuid

try:
    import boto3
except ModuleNotFoundError:
    boto3 = None


# The client is module-level for Lambda connection reuse, but tests replace it
# with a fake so handler behavior can be verified without AWS or LocalStack.
sqs_client = None


def _sqs_client():
    """Return a cached SQS client, creating it lazily inside Lambda."""
    global sqs_client
    if sqs_client is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required when no SQS client is injected")
        sqs_client = boto3.client("sqs")
    return sqs_client


def _json_response(status_code, body):
    """Build the API Gateway proxy response shape used by REST integrations."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _headers(event):
    """Normalize API Gateway headers because clients vary header casing."""
    return {key.lower(): value for key, value in (event.get("headers") or {}).items()}


def _payload(event):
    """Decode the API Gateway body and return the JSON webhook payload."""
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _repository_name(payload):
    """Extract the repository identifier used for indexing and logs."""
    return payload.get("repository", {}).get("full_name", "unknown")


def _log(message, **fields):
    """Emit a single-line JSON log for CloudWatch filtering in CI and ops."""
    print(json.dumps({"message": message, **fields}, sort_keys=True))


def handler(event, context):
    """Accept a webhook request and enqueue it for asynchronous processing."""
    try:
        payload = _payload(event)
    except json.JSONDecodeError:
        return _json_response(400, {"error": "request body must be valid JSON"})

    headers = _headers(event)
    event_type = headers.get("x-github-event", "unknown")
    event_id = headers.get("x-github-delivery") or str(uuid.uuid4())
    repository = _repository_name(payload)
    received_at = int(time.time())

    # The delivery id is stable for GitHub webhooks and gives CI a deterministic
    # key to assert across API Gateway, SQS, S3, DynamoDB, and logs.
    message = {
        "event_id": event_id,
        "event_type": event_type,
        "repository": repository,
        "received_at": received_at,
        "payload": payload,
    }

    _sqs_client().send_message(
        QueueUrl=os.environ["QUEUE_URL"],
        MessageBody=json.dumps(message),
        MessageAttributes={
            "event_type": {"DataType": "String", "StringValue": event_type},
            "repository": {"DataType": "String", "StringValue": repository},
        },
    )

    _log(
        "event_enqueued",
        event_id=event_id,
        event_type=event_type,
        repository=repository,
    )

    return _json_response(
        202,
        {
            "event_id": event_id,
            "event_type": event_type,
            "repository": repository,
            "status": "queued",
        },
    )
