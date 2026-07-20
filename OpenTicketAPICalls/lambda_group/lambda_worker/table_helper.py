from typing import Any
import pandas as pd
from datetime import datetime, timezone
import logging

pd.set_option("display.max_columns", None)  # force pandas to show all columns
pd.set_option("display.max_colwidth", None)  # show full content in each cell

# ── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # works for lambda
logging.basicConfig(level=logging.INFO)  # works for local

SCHEMA = {
    "receipt_id": "string",  # unique for each ticket submission
    "ticket_number": "string",  # not unique
    "ticket_status": "string",
    "supplier_duns": "string",
    "supplier": "string",  # use supplierParty['name] to link OpenInvoice later
    "buyer": "string",  # use buyerParty['name] to link OpenInvoice later
    "buyer_duns": "string",
    "submitted_timestamp": "datetime",  # aka first submission date, different from first saved date
    "last_submitted_timestamp": "datetime",  # relavant to approved_time when there are disputes
    "approved_timestamp": "datetime",
    "cancelled_timestamp": "datetime",  # generated from actions
    "last_disputed_timestamp": "datetime",  # generated from actions
    "ticket_created_timestamp": "datetime",  # "actionSequence": 0 timestamp, compare with service_enddate
    "ticket_created_action": "string",  # "actionSequence": 0 action
    "ticket_created_name": "string",  # generated from actions
    "ticket_created_email": "string",  # generated from actions
    "last_action_timestamp": "string",  # to determine duplicates
    "service_date_from": "datetime",
    "service_date_to": "datetime",
    "total_amount": "Float64",
    "currency": "string",
    "receipt_type": "receiptType",
    "invoiced_status": "string",
    "invoice_number": "string",
    "submission_source": "string",
    "afe": "string",
    "cost_center": "string",
    "major": "string",
    "minor": "string",
    "gl": "string",
    "href": "string",
    "ingested_at": "datetime",
}


def enforce_schema(df):
    for col, dtype in SCHEMA.items():
        if col not in df.columns:
            df[col] = None  # create missing fields, default to None
        # look at every columni including the newly created missing ones
        if dtype == "Float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        if dtype == "string":
            df[col] = df[col].astype("string")
        if dtype == "datetime":
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df[
        list(SCHEMA.keys())
    ]  # drops any unexpected columns the API might add in future, keeping schema stable.


def extract_actions(actions: list[dict]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "cancelled_timestamp": pd.NA,
        "last_disputed_timestamp": pd.NA,
        "ticket_created_timestamp": pd.NA,
        "ticket_created_action": pd.NA,
        "ticket_created_name": pd.NA,
        "ticket_created_email": pd.NA,
    }

    if not isinstance(actions, list) or len(actions) == 0:
        logger.debug("invalid actions list")
        return result
    disputed = []
    for a in actions:
        action = a.get("action", "")
        sequence = a.get("actionSequence", -1)
        if sequence == 0 and action in ("SAVE", "SUBMIT"):
            result["ticket_created_timestamp"] = a.get("actionDatetime")
            result["ticket_created_action"] = action
            result["ticket_created_name"] = a.get("actionByUserFullName")
            result["ticket_created_email"] = a.get("actionByUserEmailAddress")

        if action == "DISPUTE":
            disputed.append(a)
        if action == "CANCEL":
            result["cancelled_timestamp"] = a.get("actionDatetime")

    if disputed:
        result["last_disputed_timestamp"] = max(
            disputed, key=lambda x: x.get("actionSequence", 0)
        ).get("actionDatetime")

    return result


def create_df(tickets: list[dict], duns: str) -> pd.DataFrame:
    for ticket in tickets:
        ticket["supplier_duns"] = duns

    # pd.json_normalize handles per-row missing fields correctly
    # if row 1 has invoiceNumber but row 5 doesn't, Pandas fills row 5 with NaN automatically.
    #  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    logger.info(
        "Clean Dataframe -------------------------------------------------------------------------"
    )
    df = pd.json_normalize(tickets)

    # df.rename() is safe — it silently ignores columns that don't exist in the dataframe.
    # It will not crash if buyerParty.name is missing. It only renames what it finds.
    df = df.rename(
        columns={
            "itemID": "receipt_id",
            "receiptNumber": "ticket_number",
            "status": "ticket_status",
            "supplierParty.name": "supplier",
            "buyerParty.name": "buyer",
            "buyerParty.partyDUNS": "buyer_duns",
            "submittedDatetime": "submitted_timestamp",
            "lastSubmittedDatetime": "last_submitted_timestamp",
            "lastActionDatetime": "last_action_timestamp",
            "approvedDatetime": "approved_timestamp",
            "totalAmount": "total_amount",
            "currencyCode": "currency",
            "serviceDateFrom": "service_date_from",
            "serviceDateTo": "service_date_to",
            "invoicedStatus": "invoiced_status",
            "invoiceNumber": "invoice_number",
            "submissionSource": "submission_source",
            "receiptType": "receipt_type",
            "afe.number": "afe",
            "costCenter.number": "cost_center",
            "major.code": "major",
            "minor.code": "minor",
            "glCoding": "gl",
        }
    )
    # # check if receipt_id is unique --> primary key
    # logger.info(df['receipt_id'].duplicated(keep=False).any())

    # Extracting second API url from links
    df = df.explode("links", ignore_index=True)
    df["href"] = df["links"].str.get("href")  # if no href --> NaN

    # extract key information from actions and add to df
    # 1. row-by-row transformation on actions column --> return a column of dicts
    # 2. convert every returned dict into a Series, then align them into columns.
    info = pd.DataFrame(df["actions"].apply(extract_actions).tolist())
    # 3. Attach the new info columns horizontally.
    df = pd.concat([df, info], axis=1)

    df["ingested_at"] = datetime.now(timezone.utc).isoformat()
    df = enforce_schema(df)

    # # submission type non-EMIs --> Direct Entry
    df["submission_source"] = df["submission_source"].where(
        df["submission_source"] == "EMI", "Direct Entry"
    )
    # logger.info(df["submission_source"].value_counts(dropna=False))

    # logger.info(df.head(20))

    return df
