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

# Local Container Cache to prevent hammering the database on warm starts
GLOBAL_DUNS_MAP = None

insert_openinvoice_sql = text("""
    insert into openinvoice (
        invoice_number, invoice_date, status, status_date, current_owner,
        amount, buyer, buyer_duns, supplier, supplier_duns, invoice_type, 
        submission_type, ingested_at
    )
    values (
        :invoice_number, :invoice_date, :status, :status_date, :current_owner,
        :amount, :buyer, :buyer_duns, :supplier, :supplier_duns, :invoice_type, 
        :submission_type, :ingested_at
    ) as new_data
    on duplicate key update
        invoice_date = if(new_data.status_date >= openinvoice.status_date, new_data.invoice_date, openinvoice.invoice_date), 
        status = if(new_data.status_date >= openinvoice.status_date, new_data.status, openinvoice.status), 
        status_date = if(new_data.status_date >= openinvoice.status_date, new_data.status_date, openinvoice.status_date), 
        current_owner = if(new_data.status_date >= openinvoice.status_date, new_data.current_owner, openinvoice.current_owner), 
        amount = if(new_data.status_date >= openinvoice.status_date, new_data.amount, openinvoice.amount), 
        submission_type = if(new_data.status_date >= openinvoice.status_date, new_data.submission_type, openinvoice.submission_type), 
        ingested_at = if(new_data.status_date >= openinvoice.status_date, new_data.ingested_at, openinvoice.ingested_at)
""")


def get_duns_mapping():
    """
    Fetches master party configurations directly from the database.
    Queries the database exactly ONCE per container lifecycle.
    """
    global GLOBAL_DUNS_MAP
    if GLOBAL_DUNS_MAP is not None:
        return GLOBAL_DUNS_MAP

    logger.info("Cache miss. Fetching dynamic supplier mapping from database...")
    query = text("select name, duns from parties")
    with engine.connect() as connection:
        mapping_df = pd.read_sql(query, connection)

    # GLOBAL_DUNS_MAP = dict(zip(mapping_df["name"], mapping_df["duns"]))
    GLOBAL_DUNS_MAP = mapping_df.set_index("name")["duns"].to_dict()
    return GLOBAL_DUNS_MAP


def write_into_DB(df: pd.DataFrame) -> None:
    """
    Directly bulk-upserts an Invoice DataFrame into the MySQL database.
    Reuses the persistent global engine connection pool.
    """
    if df.empty:
        logger.info("DataFrame is empty. Skipping database write.")
        return

    records = df.where(df.notna(), None).to_dict(orient="records")
    try:
        if records:
            with engine.begin() as connection:
                connection.execute(insert_openinvoice_sql, records)  # pyright: ignore[reportCallIssue, reportArgumentType]
            logger.info(
                f"Successfully bulk-upserted {len(df)} records into openinvoice."
            )
        else:
            logger.info("No records to sync.")
    except Exception:
        logger.exception("Database upsert failed")
        raise
