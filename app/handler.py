import json
import os
import time
import uuid

import boto3


s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]


def handler(event, context):
    # Keep every request traceable with a generated event id.
    event_id = str(uuid.uuid4())
    created_at = int(time.time())

    payload = event

    object_key = f"events/{event_id}.json"

    # Store the raw event first so it can be inspected or replayed later.
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=object_key,
        Body=json.dumps(payload),
        ContentType="application/json",
    )

    table = dynamodb.Table(TABLE_NAME)

    # Store lightweight metadata separately from the raw payload.
    table.put_item(
        Item={
            "event_id": event_id,
            "created_at": created_at,
            "s3_key": object_key,
        }
    )

    return {
        "statusCode": 201,
        "event_id": event_id,
        "s3_key": object_key,
    }