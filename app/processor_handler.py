"""SQS Lambda processor for accepted webhook events.

Each SQS message is treated as the durable handoff from the ingest path. The
processor archives the raw payload in S3, writes searchable metadata to
DynamoDB, and reports per-record failures so SQS redrive can move poison
messages to the DLQ.
"""

import json
import os
import time

try:
    import boto3
except ModuleNotFoundError:
    boto3 = None


# Clients are cached for Lambda reuse and replaced by fakes in unit tests.
s3_client = None
dynamodb_resource = None


def _s3_client():
    """Return a cached S3 client, creating it lazily inside Lambda."""
    global s3_client
    if s3_client is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required when no S3 client is injected")
        s3_client = boto3.client("s3")
    return s3_client


def _dynamodb_resource():
    """Return a cached DynamoDB resource, creating it lazily inside Lambda."""
    global dynamodb_resource
    if dynamodb_resource is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required when no DynamoDB resource is injected")
        dynamodb_resource = boto3.resource("dynamodb")
    return dynamodb_resource


def _object_key(message):
    """Create a human-readable archive key partitioned by webhook event type."""
    return f"events/{message['event_type']}/{message['event_id']}.json"


def _log(message, **fields):
    """Emit structured logs that CI can query with CloudWatch Logs APIs."""
    print(json.dumps({"message": message, **fields}, sort_keys=True))


def _process_message(message):
    """Persist one decoded SQS message to S3 and DynamoDB."""
    processed_at = int(time.time())
    s3_key = _object_key(message)

    # S3 keeps the original webhook payload replayable without bloating the
    # DynamoDB item that supports quick operational lookups.
    _s3_client().put_object(
        Bucket=os.environ["BUCKET_NAME"],
        Key=s3_key,
        Body=json.dumps(message["payload"], sort_keys=True),
        ContentType="application/json",
    )

    table = _dynamodb_resource().Table(os.environ["TABLE_NAME"])
    table.put_item(
        Item={
            "event_id": message["event_id"],
            "event_type": message["event_type"],
            "repository": message["repository"],
            "received_at": message["received_at"],
            "processed_at": processed_at,
            "s3_key": s3_key,
            "status": "processed",
        }
    )

    _log(
        "event_processed",
        event_id=message["event_id"],
        event_type=message["event_type"],
        repository=message["repository"],
        s3_key=s3_key,
    )


def handler(event, context):
    """Process an SQS batch and return partial failures for safe redrive."""
    batch_item_failures = []

    for record in event.get("Records", []):
        try:
            _process_message(json.loads(record["body"]))
        except Exception as exc:
            _log(
                "event_processing_failed",
                message_id=record.get("messageId", "unknown"),
                error=str(exc),
            )
            batch_item_failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": batch_item_failures}
