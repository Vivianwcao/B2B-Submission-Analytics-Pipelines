import boto3
import json
import os
import time

sqs = boto3.client('sqs')

QUEUE_URL = os.environ['QUEUE_URL']

# 26, Sundown account is invalid
DUNS_LIST = [
    "CT1842331",  # Fraction Energy
    "243681538",  # Element
    "203125709",  # MBF
    "819572777",  # Xceed
    "200081618",  # CES
    "052152818",  # Baseline
    "245235523",  # Titanium
    "253889091",  # CFR
    "242371557",  # Keranda
    "078430362",  # AES
    "079358013",  # Oilpatch
    "208237961",  # Benchmark
    "ODX124178",  # Rogers Trucking
    "081310726",  # US ROD
    "036591171",  # Patriot Pump
    "095750395",  # Q2 LLC
    "203526686",  # Q2 ULC
    "ODX110900",  # Tier 1 Energy
    "CT4777750",  # H3M
    "CT3450270",  # 360
    "ODX101260",  # Definitive Optimization
    "243347334",  # Blackstone Projects
    "CT0395812",  # Canada West Land Services
    "202730875",  # Mantl
    "202699559",  # Di-Corp
    "208755902",  # Kinetic
    "041754536",  # Flying V
    "884798380",  # Fireside Minerals
    "CT0051757",  # WPW
]

dates = [
    {"month_start": "2025-01-01", "month_end": "2025-01-31"},
    {"month_start": "2025-02-01", "month_end": "2025-02-28"},
    {"month_start": "2025-03-01", "month_end": "2025-03-31"},
    {"month_start": "2025-04-01", "month_end": "2025-04-30"},
    {"month_start": "2025-05-01", "month_end": "2025-05-31"},
    {"month_start": "2025-06-01", "month_end": "2025-06-30"},
    {"month_start": "2025-07-01", "month_end": "2025-07-31"},
    {"month_start": "2025-08-01", "month_end": "2025-08-31"},
    {"month_start": "2025-09-01", "month_end": "2025-09-30"},
    {"month_start": "2025-10-01", "month_end": "2025-10-31"},
    {"month_start": "2025-11-01", "month_end": "2025-11-30"},
    {"month_start": "2025-12-01", "month_end": "2025-12-31"},
    {"month_start": "2026-01-01", "month_end": "2026-01-31"},
    {"month_start": "2026-02-01", "month_end": "2026-02-28"},
    {"month_start": "2026-03-01", "month_end": "2026-03-31"},
    {"month_start": "2026-04-01", "month_end": "2026-04-30"},
    {"month_start": "2026-05-01", "month_end": "2026-05-25"}
]

def lambda_handler(event, context):
    for duns in DUNS_LIST:
        for date in dates:
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps({
                    'duns': duns,
                    'start_date': date['month_start'],
                    'end_date': date['month_end']
                })
            )
            time.sleep(2)  # 2 seconds between each message
            print(f"Queued: {duns} from {date['month_start']} to {date['month_end']}")


   