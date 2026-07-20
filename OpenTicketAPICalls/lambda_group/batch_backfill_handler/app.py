import boto3
import json
import os

sqs = boto3.client("sqs")
s3 = boto3.client("s3")

BUCKET = "emi-v3"
PREFIX = "openticket_api_json/"
QUEUE_URL = os.environ["QUEUE_URL"]


def lambda_handler(event, context):
    paginator = s3.get_paginator("list_objects_v2")

    batch = []

    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for i, obj in enumerate(page.get("Contents", [])):
            key = obj["Key"]

            batch.append(
                {
                    "Id": str(i),  # must be unique per batch
                    "MessageBody": json.dumps({"bucket": BUCKET, "key": key}),
                }
            )
            if len(batch) == 10:
                sqs.send_message_batch(QueueUrl=QUEUE_URL, Entries=batch)
                batch = []

    if batch:
        sqs.send_message_batch(QueueUrl=QUEUE_URL, Entries=batch)
