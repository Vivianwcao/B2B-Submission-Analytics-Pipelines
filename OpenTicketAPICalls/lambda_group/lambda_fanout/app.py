import boto3
import json
import os

sqs = boto3.client("sqs")

QUEUE_URL = os.environ["QUEUE_URL"]

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
    "041754536",  # Flying V
    "884798380",  # Fireside Minerals
    "CT0051757",  # WPW
    "CT0879489",  # Terrafirma Resources
    "243264209",  # Eco-Green
    "205246320",  # Kings Energy Services
    "11-722-3270",  # The Wellboss Company LLC
]


def lambda_handler(event, context):
    for duns in DUNS_LIST:
        try:
            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"duns": duns}))
            print(f"Queued: {duns}")

        except Exception as e:
            print(f"Failed to queue {duns}: {str(e)}")
