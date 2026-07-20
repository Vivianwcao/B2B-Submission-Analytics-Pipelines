import os
import pandas as pd
from sqlalchemy import create_engine, text
import logging

pd.set_option("display.max_columns", None)  # force pandas to show all columns
pd.set_option("display.max_colwidth", None)  # show full content in each cell

# ── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # works for lambda
logging.basicConfig(level=logging.INFO)  # works for local

# ── Create DB connection  ─────────────────────────────────────────────────────────────────
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]

# Declared globally. It instantiates ONCE per container lifecycle. SQLAlchemy will handle connection pooling under the hood.
engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
    pool_size=1,  # Restricts this container to exactly 1 persistent connection
    max_overflow=0,  # no temp extra DB connection allowed
    pool_pre_ping=True,  # Automatically reconnects if a connection goes stale
)

# Build upsert SQL - Modern, clean MySQL 8.4 syntax using Row Alias eg. 'AS new_data'
upsert_sql = text("""
    INSERT INTO opentickets (
        receipt_id, ticket_number, supplier, supplier_duns,
        buyer, buyer_duns, ticket_status, last_action_timestamp,
        submitted_timestamp, last_submitted_timestamp, approved_timestamp,
        cancelled_timestamp, last_disputed_timestamp, ticket_created_timestamp,
        service_date_from, service_date_to, ticket_created_action,
        ticket_created_name, ticket_created_email, total_amount,
        receipt_type, currency, invoiced_status, invoice_number,
        submission_source, afe, cost_center, major, minor, gl,
        href, ingested_at
    ) VALUES (
        :receipt_id, :ticket_number, :supplier, :supplier_duns,
        :buyer, :buyer_duns, :ticket_status, :last_action_timestamp,
        :submitted_timestamp, :last_submitted_timestamp, :approved_timestamp,
        :cancelled_timestamp, :last_disputed_timestamp, :ticket_created_timestamp,
        :service_date_from, :service_date_to, :ticket_created_action,
        :ticket_created_name, :ticket_created_email, :total_amount,
        :receipt_type, :currency, :invoiced_status, :invoice_number,
        :submission_source, :afe, :cost_center, :major, :minor, :gl,
        :href, :ingested_at
    ) AS new_data
    ON DUPLICATE KEY UPDATE
        ticket_status = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.ticket_status, opentickets.ticket_status),
        total_amount = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.total_amount, opentickets.total_amount),
        last_action_timestamp = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.last_action_timestamp, opentickets.last_action_timestamp),
        submitted_timestamp = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.submitted_timestamp, opentickets.submitted_timestamp),
        last_submitted_timestamp = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.last_submitted_timestamp, opentickets.last_submitted_timestamp),
        approved_timestamp = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.approved_timestamp, opentickets.approved_timestamp),
        cancelled_timestamp = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.cancelled_timestamp, opentickets.cancelled_timestamp),
        last_disputed_timestamp = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.last_disputed_timestamp, opentickets.last_disputed_timestamp),
        receipt_type = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.receipt_type, opentickets.receipt_type),
        service_date_from = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.service_date_from, opentickets.service_date_from),
        service_date_to = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.service_date_to, opentickets.service_date_to),
        currency = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.currency, opentickets.currency),
        invoiced_status = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.invoiced_status, opentickets.invoiced_status),            
        invoice_number = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.invoice_number, opentickets.invoice_number),
        afe = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.afe, opentickets.afe),
        cost_center = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.cost_center, opentickets.cost_center),
        major = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.major, opentickets.major),
        minor = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.minor, opentickets.minor),
        gl = IF(new_data.last_action_timestamp > opentickets.last_action_timestamp, new_data.gl, opentickets.gl);
""")

# Write to the parties table using INSERT IGNORE (skips if DUNS already exists)
insert_parties_sql = text("""
    INSERT IGNORE INTO parties (duns, name, party_type)
    VALUES (:duns, :name, :party_type);
""")

insert_invoice_numbers = text("""
    insert into invoice_numbers (receipt_id, invoice_number)
    values (:receipt_id, :invoice_number) 
    as new_data
    on duplicate key update
        invoice_number = new_data.invoice_number;
""")


def create_duns_parties_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    create ans return a dataframe for parties table
    """
    # 1. Extract Unique Suppliers
    df_suppliers = (
        df[["supplier_duns", "supplier"]].dropna().drop_duplicates(keep="first")
    )
    df_suppliers.columns = ["duns", "name"]
    df_suppliers["party_type"] = "supplier"

    # 2. Extract Unique Buyers
    df_buyers = df[["buyer_duns", "buyer"]].dropna().drop_duplicates()
    df_buyers.columns = ["duns", "name"]
    df_buyers["party_type"] = "buyer"

    # 3. Combine them into a single list of dictionaries
    df_parties = pd.concat([df_suppliers, df_buyers], axis=0).drop_duplicates(
        subset=["duns"]
    )

    return df_parties


def create_invoice_numbers_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    create and return a dataframe for invoice_numebrs table
    """
    df_in = df[["receipt_id", "invoice_number"]].dropna().drop_duplicates(keep="first")
    # 1. Split strings into lists
    df_in["invoice_number"] = df_in["invoice_number"].str.split(",")
    # 2. Explode lists into rows
    df_in = df_in.explode("invoice_number")
    # 3. Strip whitespace
    df_in["invoice_number"] = df_in["invoice_number"].str.strip()

    # 4. Remove dup rows after exploding
    df_in.drop_duplicates(subset=["receipt_id", "invoice_number"], keep="first")

    return df_in


def write_into_DB(df: pd.DataFrame) -> None:
    """
    Directly bulk-upserts an Invoice DataFrame into the MySQL database.
    Reuses the persistent global engine connection pool.
    """
    # df.empty is a pandas property that returns whether the DataFrame has zero rows or zero columns.
    if df.empty:
        logger.info("DataFrame is empty. Skipping database write.")
        return

    # ── PHASE 1: OPEN TICKETS DATA INGESTION ────────────────────────────────
    # Convert DataFrame to list of dicts ("records" format) for SQLAlchemy named parameters
    records = df.where(df.notna(), None).to_dict(orient="records")

    try:
        if records:
            with engine.begin() as connection:
                connection.execute(upsert_sql, records)  # pyright: ignore[reportArgumentType, reportCallIssue]
            logger.info(
                f"Successfully bulk-upserted {len(df)} records into opentickets."
            )
        else:
            logger.info("No records to sync.")

    except Exception:
        logger.exception("Database upsert failed")
        raise

    # ── PHASE 2: Update INVOICE_NUMBERS DATA if duplicate ────────────────────────────────
    # This block always executes after Phase 1 finishes successfully,
    try:
        df_in = create_invoice_numbers_df(df)
        in_records = df_in.where(df_in.notna(), None).to_dict(orient="records")
        if in_records:
            with engine.begin() as connection:
                connection.execute(
                    insert_invoice_numbers,
                    in_records,  # type: ignore
                )  # type: ignore
                logger.info("Successfully updated invoice_numbers table.")
        else:
            logger.info("No invoice_numbers records to insert")

    except Exception:
        logger.exception("Insert invoice_numbers table failed")
        raise

    # ── PHASE 3: PARTIES MASTER DATA REFRESH using INSERT IGNORE (skips if DUNS already exists) ────────────────────────────────
    # This block always executes after Phase 2 finishes successfully,
    try:
        parties_df = create_duns_parties_df(df)
        parties_records = parties_df.where(parties_df.notna(), None).to_dict(
            orient="records"
        )  # NaNs should have been previously removed anyways

        if parties_records:
            with engine.begin() as connection:
                connection.execute(insert_parties_sql, parties_records)  # pyright: ignore[reportArgumentType, reportCallIssue]
            logger.info(
                f"Successfully ran master sync for {len(parties_records)} party records."
            )
        else:
            logger.info("No party records to sync.")
    except Exception:
        logger.exception("Lookup master data sync failed on the parties table.")
        # no raise. it is okay
