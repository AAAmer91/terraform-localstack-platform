"""Unit tests for Lambda handler behavior without requiring LocalStack.

The production handlers expose module-level AWS clients for Lambda reuse. These
tests replace those clients with small fakes so the assertions focus on payload
translation, persistence intent, and response shape.
"""

import importlib
import json
import os
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
# Import handlers the same way Lambda does: by module name inside the package
# archive, rather than through a test-only package path.
sys.path.insert(0, str(APP_DIR))


class FakeSqsClient:
    """Capture outbound SQS messages for assertions."""

    def __init__(self):
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


class FakeS3Client:
    """Capture archived objects without touching S3 or LocalStack."""

    def __init__(self):
        self.objects = []

    def put_object(self, **kwargs):
        self.objects.append(kwargs)
        return {"ETag": '"etag"'}


class FakeTable:
    """Capture DynamoDB items written by the processor."""

    def __init__(self):
        self.items = []

    def put_item(self, **kwargs):
        self.items.append(kwargs["Item"])
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class FakeDynamoResource:
    """Mimic the boto3 resource API used by the processor handler."""

    def __init__(self, table):
        self.table = table

    def Table(self, name):
        self.table.name = name
        return self.table


class HandlerTests(unittest.TestCase):
    def test_ingest_handler_enqueues_github_webhook(self):
        """Ingest should acknowledge the webhook only after SQS enqueue."""
        os.environ["QUEUE_URL"] = "http://localhost:4566/000000000000/events"
        ingest_handler = importlib.import_module("ingest_handler")
        fake_sqs = FakeSqsClient()
        ingest_handler.sqs_client = fake_sqs

        event = {
            "headers": {
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "delivery-123",
            },
            "body": json.dumps(
                {
                    "repository": {"full_name": "AAAmer91/terraform-localstack-platform"},
                    "ref": "refs/heads/main",
                }
            ),
            "isBase64Encoded": False,
        }

        response = ingest_handler.handler(event, None)

        self.assertEqual(response["statusCode"], 202)
        response_body = json.loads(response["body"])
        self.assertEqual(response_body["event_id"], "delivery-123")
        self.assertEqual(response_body["event_type"], "push")
        self.assertEqual(response_body["repository"], "AAAmer91/terraform-localstack-platform")
        self.assertEqual(response_body["status"], "queued")

        self.assertEqual(len(fake_sqs.messages), 1)
        message = json.loads(fake_sqs.messages[0]["MessageBody"])
        self.assertEqual(message["event_id"], "delivery-123")
        self.assertEqual(message["event_type"], "push")
        self.assertEqual(message["repository"], "AAAmer91/terraform-localstack-platform")
        self.assertEqual(message["payload"]["ref"], "refs/heads/main")

    def test_processor_handler_archives_event_and_indexes_metadata(self):
        """Processor should archive raw payloads and index searchable metadata."""
        os.environ["BUCKET_NAME"] = "localstack-platform-dev-events"
        os.environ["TABLE_NAME"] = "localstack-platform-dev-events"
        processor_handler = importlib.import_module("processor_handler")
        fake_s3 = FakeS3Client()
        fake_table = FakeTable()
        processor_handler.s3_client = fake_s3
        processor_handler.dynamodb_resource = FakeDynamoResource(fake_table)

        message = {
            "event_id": "delivery-123",
            "event_type": "push",
            "repository": "AAAmer91/terraform-localstack-platform",
            "received_at": 1710000000,
            "payload": {"ref": "refs/heads/main"},
        }
        event = {
            "Records": [
                {
                    "messageId": "message-1",
                    "body": json.dumps(message),
                }
            ]
        }

        response = processor_handler.handler(event, None)

        self.assertEqual(response, {"batchItemFailures": []})
        self.assertEqual(len(fake_s3.objects), 1)
        archived = fake_s3.objects[0]
        self.assertEqual(archived["Bucket"], "localstack-platform-dev-events")
        self.assertEqual(archived["Key"], "events/push/delivery-123.json")
        self.assertEqual(json.loads(archived["Body"])["ref"], "refs/heads/main")

        self.assertEqual(len(fake_table.items), 1)
        item = fake_table.items[0]
        self.assertEqual(item["event_id"], "delivery-123")
        self.assertEqual(item["event_type"], "push")
        self.assertEqual(item["repository"], "AAAmer91/terraform-localstack-platform")
        self.assertEqual(item["s3_key"], "events/push/delivery-123.json")
        self.assertEqual(item["status"], "processed")


if __name__ == "__main__":
    unittest.main()
