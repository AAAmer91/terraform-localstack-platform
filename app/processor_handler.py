import json
import os
import time

try:
    import boto3
except ModuleNotFoundError:
    boto3 = None


s3_client = None
dynamodb_resource = None


def _s3_client():
    global s3_client
    if s3_client is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required when no S3 client is injected")
        s3_client = boto3.client("s3")
    return s3_client


def _dynamodb_resource():
    global dynamodb_resource
    if dynamodb_resource is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required when no DynamoDB resource is injected")
        dynamodb_resource = boto3.resource("dynamodb")
    return dynamodb_resource


def _object_key(message):
    return f"events/{message['event_type']}/{message['event_id']}.json"


def _log(message, **fields):
    print(json.dumps({"message": message, **fields}, sort_keys=True))


def _process_message(message):
    processed_at = int(time.time())
    s3_key = _object_key(message)

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
