import boto3
import json
from sqlalchemy import create_engine, text
import pandas as pd
import logging
import os
import urllib.parse

pd.set_option("display.max_columns", None)  # force pandas to show all columns
pd.set_option("display.max_colwidth", None)  # show full content in each cell

s3 = boto3.client("s3")
sqs = boto3.client("sqs")

# ── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # works for lambda
logging.basicConfig(level=logging.INFO)  # works for local

# ── Create DB connection  ─────────────────────────────────────────────────────────────────
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]
MANUAL_DLQ_URL = os.environ.get("MANUAL_DLQ_URL")

# local test
# DB_HOST= 'emi-v3.c5gxxy53ipqo.ca-central-1.rds.amazonaws.com'
# DB_USER= 'vivian'
# DB_PASSWORD= '12345vivian'
# DB_NAME= 'submission_analytics'

# Declared globally. It instantiates ONCE per container lifecycle. SQLAlchemy will handle connection pooling under the hood.
engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
    pool_size=1,  # Restricts this container to exactly 1 persistent connection
    max_overflow=0,  # no temp extra DB connection allowed
    pool_pre_ping=True,  # Automatically reconnects if a connection goes stale
)


def lambda_handler(event, context):
    sqs_records = event.get("Records")
    if not sqs_records:
        logger.warning("Missing Records in event")
        return {"statusCode": 200, "body": "No records to process"}

    # Receiver batchsize == 10
    # # Loop through the batch of up to 10 SQS messages
    for record in sqs_records:
        raw_body = record.get("body")

        try:
            body = json.loads(raw_body)

            bucket = body.get("bucket")
            key = body.get("key")

            if not bucket or not key:
                # Skip this specific broken message, keep processing the rest of the batch
                raise ValueError(
                    f"Invalid message payload: missing bucket or key. Body: {body}"
                )

            # Decode the key in case it contains spaces or special characters
            key = urllib.parse.unquote_plus(key)

            res = s3.get_object(Bucket=bucket, Key=key)

            # Read stream and decode from bytes to string
            file_content = res["Body"].read().decode("utf-8")
            data = json.loads(file_content)

            if not data:  # empty file
                logger.info(f"Empty JSON file: {key}")
                continue

            df = pd.json_normalize(data)
            df = df[["itemID", "invoiceNumber"]].convert_dtypes()
            df.columns = ["receipt_id", "invoice_number"]
            df = df[df["invoice_number"].notna()]

            with engine.begin() as connection:
                # reate a staging table as transfer buffer
                # unique name to prevent workers in different containers update the same table at the same time
                staging_table = f"staging_{context.aws_request_id.replace('-', '')}"

                try:
                    df.to_sql(
                        staging_table, con=connection, if_exists="replace", index=False
                    )

                    connection.execute(
                        text(
                            f"""
                        update opentickets ot
                        join {staging_table} s on ot.receipt_id = s.receipt_id
                        set ot.invoice_number = s.invoice_number
                        """
                        )
                    )
                finally:
                    # drop it after
                    connection.execute(text(f"DROP TABLE IF EXISTS {staging_table}"))

            # for invoice_number table
            df_child = df.copy()
            # 1. Split strings into lists
            df_child["invoice_number"] = df_child["invoice_number"].str.split(",")
            # 2. Explode lists into rows
            df_child = df_child.explode("invoice_number")
            # 3. Strip whitespace
            df_child["invoice_number"] = df_child["invoice_number"].str.strip()

            # 4. Remove dup rows after exploding
            df_child.drop_duplicates(
                subset=["receipt_id", "invoice_number"], keep="first"
            )
            # logger.info(df_child.dtypes)
            # logger.info(df_child[df_child['invoice_number'].duplicated(keep=False)])

            child_records = df_child.where(df_child.notna(), None).to_dict(
                orient="records"
            )

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                    INSERT IGNORE INTO invoice_numbers (receipt_id, invoice_number)
                    VALUES (:receipt_id, :invoice_number)
                    """
                    ),
                    child_records,  # type: ignore
                )  # type: ignore

        except Exception as e:
            err_msg = str(e)
            logger.exception("1 batch failed. Shunting to manual DLQ.")

            try:
                sqs.send_message(
                    QueueUrl=MANUAL_DLQ_URL,
                    MessageBody=raw_body,
                    MessageAttributes={
                        "ErrorMessage": {"DataType": "String", "StringValue": err_msg}
                    },
                )
            except Exception:
                logger.exception("Failed to send to Manual DLQ")

            # continue to next json
            continue

    return {"statusCode": 200, "body": "Batch processed successfully."}


if __name__ == "__main__":
    lambda_handler(
        {
            "Records": [
                {
                    "body": '{"bucket":"emi-v3", "key":"openticket_api_json/052152818-20260526-135419"}'
                }
            ]
        },
        None,
    )
