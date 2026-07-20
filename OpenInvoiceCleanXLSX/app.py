import json
import pandas as pd
from datetime import datetime, timezone
import boto3
import awswrangler as wr
import io
import urllib.parse
from sql_helper import write_into_DB, get_duns_mapping
import logging

pd.set_option("display.max_columns", None)  # force pandas to show all columns
pd.set_option("display.max_colwidth", None)  # show full content in each cell

# ── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # works for lambda
logging.basicConfig(level=logging.INFO)  # works for local


s3 = boto3.client("s3")

SCHEMA = {
    "invoice_number": "string",
    "invoice_date": "datetime",
    "status": "string",
    "status_date": "datetime",
    "amount": "float64",
    "current_owner": "string",
    "buyer": "string",
    "buyer_duns": "string",
    "supplier": "string",
    "supplier_duns": "string",
    "invoice_type": "string",
    "submission_type": "string",
    "ingested_at": "datetime",
}


def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforces precise target analytical schema constraints on the DataFrame.
    """
    for col, dtype in SCHEMA.items():
        if col not in df.columns:
            df[col] = None
        if dtype == "float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")  # pyright: ignore[reportAttributeAccessIssue]
        if dtype == "string":
            df[col] = df[col].astype("string")
        if dtype == "datetime":
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    return df[list(SCHEMA)]  # type: ignore


def lambda_handler(event, context):
    # # local
    # key='excel.xlsx'

    # s3
    # --- Validation layer (no SNS) ---
    # 1. the outer SQS records
    sqs_records = event.get("Records")
    if not sqs_records:
        logger.warning("Missing Records in event")
        return
    sqs_record = sqs_records[0]  # because BatchSize: 1, 1 sqs message per invocation
    s3_event_wrapper = json.loads(sqs_record["body"])

    # SQS event test messages sent by S3 do not contain the 'Records' key
    records = s3_event_wrapper.get("Records")
    if not records:
        logger.info("Skipping non-S3 execution payload or test message.")

    # The inner S3 payload records
    record = records[0]

    bucket = record.get("s3", {}).get("bucket", {}).get("name")
    key = record.get("s3", {}).get("object", {}).get("key")

    if not bucket or not key:
        logger.warning("Invalid S3 event")
        return
    key = urllib.parse.unquote_plus(key)

    # --- Execution layer (SNS on failure) ---
    try:
        # 1. Ingest Data from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        excel_bytes = response["Body"].read()

        # wrap excel bytes in BytesIO
        excel_buffer = io.BytesIO(excel_bytes)

        sheets = pd.read_excel(
            excel_buffer, sheet_name=["Results", "Search Criteria"], engine="openpyxl"
        )
        df = sheets["Results"]
        df_sheet2 = sheets["Search Criteria"]

        if df.empty or df_sheet2.empty:
            logger.warning("Input file sheets are empty. Skipping execution.")
            return
        raw_supplier_name = str(df_sheet2.iloc[0, 0]).strip()
        df["supplier"] = raw_supplier_name

        df = df.rename(
            columns={
                "Invoice #": "invoice_number",
                "Invoice Date": "invoice_date",
                "Status Date": "status_date",
                "Submission Type": "submission_type",
                "Status": "status",
                "Current Owner": "current_owner",
                "Amount": "amount",
                "Buyer": "buyer",
                "Type": "invoice_type",
            }
        )

        # Match supplier name against the database list dynamically

        duns_mapping = get_duns_mapping()

        df["supplier_duns"] = duns_mapping.get(raw_supplier_name)

        df["buyer"] = (
            df["buyer"]
            .replace(to_replace=r"^\s*$", value=pd.NA, regex=True)
            .fillna("UNKNOWN_BUYER")
        )
        df["buyer_duns"] = df["buyer"].str.strip().map(duns_mapping)

        df["submission_type"] = df["submission_type"].replace("B2B", "EMI")
        df["submission_type"] = df["submission_type"].where(
            df["submission_type"] == "EMI", "Direct Entry"
        )

        df["ingested_at"] = datetime.now(timezone.utc)
        df = enforce_schema(df)

        #  Write into DB
        write_into_DB(df)

        # # Write into data catalog and saves a parquet file
        # wr.s3.to_parquet(
        #     df=df,
        #     path="s3://emi-v3/openinvoice_parquets/",
        #     dataset=True,          # treats the path as a dataset folder
        #     database="openinvoice_data",    # manually created in Glue database
        #     table="invoices",   # Glue table name - will get auto-created
        #     mode="append"      # a new Parquet file is added to the S3 folder. It does NOT modify existing files and does NOT change the Glue table schema.
        # )

        return {"statusCode": 200, "body": json.dumps({"message": "success"})}

    except Exception:
        logger.exception("Failed.")
        raise


if __name__ == "__main__":
    lambda_handler(None, None)
