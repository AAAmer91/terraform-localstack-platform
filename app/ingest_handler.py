import base64
import json
import os
import time
import uuid

try:
    import boto3
except ModuleNotFoundError:
    boto3 = None


sqs_client = None


def _sqs_client():
    global sqs_client
    if sqs_client is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required when no SQS client is injected")
        sqs_client = boto3.client("sqs")
    return sqs_client


def _json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _headers(event):
    return {key.lower(): value for key, value in (event.get("headers") or {}).items()}


def _payload(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _repository_name(payload):
    return payload.get("repository", {}).get("full_name", "unknown")


def _log(message, **fields):
    print(json.dumps({"message": message, **fields}, sort_keys=True))


def handler(event, context):
    try:
        payload = _payload(event)
    except json.JSONDecodeError:
        return _json_response(400, {"error": "request body must be valid JSON"})

    headers = _headers(event)
    event_type = headers.get("x-github-event", "unknown")
    event_id = headers.get("x-github-delivery") or str(uuid.uuid4())
    repository = _repository_name(payload)
    received_at = int(time.time())

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
