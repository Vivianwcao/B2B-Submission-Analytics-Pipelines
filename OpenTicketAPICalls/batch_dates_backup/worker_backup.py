import json
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime, timezone
import logging
import awswrangler as wr
from api_helper import get_tickets, get_ssl_credentials
from table_helper import create_tables
from sql_helper import write_into_DB

ssm = boto3.client('ssm')
s3 = boto3.client('s3')

# ── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # works for lambda
logging.basicConfig(level=logging.INFO) # works for local

def lambda_handler(event, context):
    try:
        records = event.get('Records')
        if not records:
            logger.warning('No Records in event.')
            return # These will never succeed. no retries, no DLQ

        record = records[0]
        
        body_str = record.get('body')
        
        if not body_str:
            logger.warning("Missing body in SQS record")

        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            logger.error("Invalid JSON")
            return # no SQS retry and eventually DLQ

        duns = body.get('duns')

        if not duns:
            logger.info('Supplier DUNS not provided.')
            return # These will never succeed. no retries, no DLQ
        #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
        # get tickets from API

        print('EVENT:', event)
        cert = get_ssl_credentials(ssm)
        print("cert paths:", cert)

        # for batch API call 
        start_date = body.get('start_date') 
        end_date = body.get('end_date')
        res = get_tickets(duns, cert, start_date, end_date)

        # for regular call
        # res = get_tickets(duns, cert)
        
        tickets = res.get("receipts")

        #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
        # # use local json file for testing

        # try:
        #     with open('../../batch_dates_backup/aes.json', 'r', encoding='utf-8') as f:
        #         payload = json.load(f)
        # except (FileNotFoundError, json.JSONDecodeError) as e:
        #     logger.error(f'Failed loading payload: {e}')
        #     return
        
        # tickets = payload.get("receipts")

        #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
        # Save tickets data in s3
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        try: 
            s3.put_object(
                Body=json.dumps(tickets), 
                Bucket="emi-v3", 
                Key=f"openticket_api_json/{duns}-{timestamp}.json",
                ContentType="application/json"
            )
        except (ClientError, BotoCoreError) as e:
            logger.warning(
                "S3 upload failed",
                extra={
                    "bucket": "emi-v3",
                    "key": f"openticket_api_json/{duns}-{timestamp}.json",
                    "error": str(e)
                }
            )

        #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
        # Clean and process tickets data

        if not (tickets and isinstance(tickets, list)):
            print(f"No tickets returned for ({duns}) - empty or not a list")
            return  # nothing to process, exit cleanly --> message deleted, disappears quietly, no DLQ
        
        df = create_tables(tickets, duns)

        #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
        # Write into RDS DB
        write_into_DB(df)

        #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
        # # Write into parquet files and create/update data catelogue
        # wr.s3.to_parquet(
        #     df=df,
        #     path="s3://emi-v3/openticket_parquets/",
        #     dataset=True,          # treats the path as a dataset folder
        #     database="openticket_data",    # manually created in Glue database
        #     table="tickets",   # Glue table name - will get auto-created
        #     mode="append"      # a new Parquet file is added to the S3 folder. It does NOT modify existing files and does NOT change the Glue table schema.
        # )

    except Exception:
        logger.exception("Failed") # logger.exception automatically includes trackback (only inside except block)
        raise #report a failure to CloudWatch and EventBridge
    
    
if __name__ == "__main__":
    lambda_handler(
        {"Records": 
            [
                { 
                    "body": "{\"duns\":\"078430362\"}"
                }
            ]
        }, None
    )