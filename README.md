# Submission Analytics Pipeline
## Automated Dual-Source Ingestion & BI Reporting for OpenTicket & OpenInvoice Data

### Tech Stack & Tools
* **Core AWS Services:** AWS Lambda, Amazon S3, Amazon SQS, AWS EventBridge, Amazon CloudWatch, Amazon SNS, AWS SSM Parameter Store
* **Database & Analytics:** Amazon RDS (MySQL), AWS Glue, Amazon Athena, Amazon QuickSight
* **Languages & Libraries:** Python 3.13, Pandas, SQLAlchemy, PyMySQL, AWSWrangler, PyArrow, Requests, SAM CLI
* **Upstream Sources:** OpenTicket API (mTLS), OpenInvoice (Power Automate / S3 XLSX exports)

---

## Project Overview & Business Goal

### Business Context & Background
EMI submits field service tickets and invoices on behalf of oil and gas suppliers to their corporate buyers. Submissions run through two primary platforms: **OpenTicket** and **OpenInvoice** (both owned by Enverus). In field operations, once a ticket is approved inside OpenTicket, it is flipped into an invoice inside OpenInvoice. Because ticket approvals directly drive invoice creation, tracking activity across both systems is critical to understanding the complete financial lifecycle.

### The Dual-Source Technical Challenge
Although both platforms hold connected data, system access differs significantly between them:
* **OpenTicket (Automated API Route):** EMI has direct API access authenticated via mutual TLS. This allows the pipeline to extract full historical audit logs, status changes, and granular creator metadata.
* **OpenInvoice (S3 File Ingestion Route):** Direct API access is unavailable. OpenInvoice data is retrieved as multi-row Excel snapshot reports, downloaded via an automated Power Automate flow, and dropped into an S3 landing bucket. Due to file format limits, OpenInvoice only provides macro volume totals and lag metrics.

### Business Drivers & Key Analytics Metrics
EMI previously tracked basic monthly submission totals, but management lacked an aggregated, cross-system view to answer key operational questions. The business owner needed deep analytics to uncover new revenue streams, optimize supplier entry habits, and accelerate cash flow:

* **B2B vs. Manual Volume Splits:** Compare overall ticket counts between **B2B automated API submissions** (handled by EMI) versus **manual portal submissions** (handled directly by suppliers). This highlights which suppliers still rely heavily on manual entry.
* **Ticket Quality & Approval Status Breakdown:** Compare the exact volume and percentage of tickets that end up **canceled**, **disputed**, or **approved** across both submission channels. This proves whether manual entries lead to higher error rates and processing friction compared to automated B2B submissions.
* **Turnaround & Cash Flow Lag Metrics:** Measure key operational timelines across both submission sources:
  1. **Service-to-Submission Lag:** Time elapsed from field work completion to initial ticket submission.
  2. **Submission-to-Approval Lag:** Time elapsed from submission to final ticket approval.
  * *Financial Impact:* Faster ticket approvals lead directly to faster invoice creation and payment. Proving that EMI's B2B automation significantly cuts approval lag proves that clients get their cash back much faster.
* **User-Level Behavior Tracking (OpenTicket API):** The business owner noticed that manual portal delays were often caused by specific individuals at a supplier manually typing in entries. By pulling the creator's name and company email from the OpenTicket API payloads, the system tracks manual entry habits down to the individual employee.

### Daily Business Impact & Sales Enablement
QuickSight dataset refreshes trigger daily from the MySQL RDS views to load the latest data. Every morning, the business owner and sales team use these daily dashboards to review supplier metrics and user entry distributions. They use this data to show suppliers how much employee payroll is wasted on manual data entry and pitch them on switching to EMI's automated B2B service.

---

## Pipeline Architecture & Data Flow

![Pipeline Architecture Diagram](Enverus_submission_analytics_pipeline.jpg)

### Data Processing Stages

#### 1. OpenTicket API Pipeline (Automated Scheduled Extraction)
* **Fanout Event:** An EventBridge rule triggers **Lambda 1 (Fanout)** every 7 days. It iterates through 25+ suppliers and pushes an individual SQS message per supplier into a worker queue.
* **Parallel API Fetching:** **Lambda 2 (Worker)** scales up (max 5 concurrent instances) to fetch tickets from the OpenTicket API using mutual TLS credentials stored in SSM Parameter Store.
* **Schema Enforcement & Upsert:** Standardizes field types using Pandas, extracts user creator metadata, and upserts records into MySQL RDS (`opentickets` table), preserving the most recent data via timestamp checks.

#### 2. OpenInvoice Pipeline (Event-Driven File Ingestion)
* **File Delivery:** A Power Automate flow drops multi-row OpenInvoice Excel reports (`.xlsx`) into a dedicated Amazon S3 landing bucket (`emi-v3`).
* **Queue Ingestion:** S3 upload events trigger an SQS message, invoking the **OpenInvoice Worker Lambda**.
* **Deduplication & Consolidation:** Converts multi-row invoice event logs into clean, single-row records per invoice before upserting into MySQL RDS (`openinvoices` table).

---

## Key Engineering Decisions & Solutions

### 1. Fanout Architecture over Monolithic Lambda Loops
* **Challenge:** Each supplier API fetch operates independently and takes between 1 to 5 minutes. Processing 25+ suppliers sequentially inside a single Lambda function risked hitting the 15-minute AWS execution timeout and creating total pipeline failure if a single supplier API call hung.
* **Solution:** Implemented a Fanout pattern via SQS. The controller Lambda completes in seconds, while SQS distributes processing across isolated worker Lambda invocations running in parallel with automatic retry capabilities.

### 2. Migration to MySQL RDS over S3 / Athena
* **Challenge:** The pipeline initially used Parquet files on S3 queried via Amazon Athena. However, frequent schema evolution required updating Glue Data Catalogs, backfilling historical Parquet files, and rewriting Athena views whenever new upstream fields were added.
* **Solution:** Migrated the data warehouse layer to Amazon RDS (MySQL). Adding new metadata fields now requires a simple `ALTER TABLE ADD COLUMN` operation. Furthermore, performing complex `FULL OUTER JOIN` operations between tickets and invoices is faster and more maintainable in SQL than joining across separate Athena S3 datasets.

### 3. Last-Action Timestamp Upsert Logic
* **Challenge:** The OpenTicket API returns the complete historical state of a receipt. Standard `INSERT` statements caused duplicate key errors, while blind overwrites ran the risk of overwriting fresh data with out-of-order stale payload responses.
* **Solution:** Engineered an `ON DUPLICATE KEY UPDATE` strategy comparing incoming `last_action_timestamp` values against stored records. Fields are updated only if the incoming record contains a newer timestamp than the stored entry.

### 4. Staging Tables for Parallel Batch Updates
* **Challenge:** Multiple worker Lambdas running concurrently need to write batch update JSON payload mappings back to MySQL without causing deadlock conditions or race conditions.
* **Solution:** Each worker Lambda generates a uniquely named temporary staging table (`staging_{request_id}`), writes its local payload batch, executes the update join against the main table, and drops the staging table inside a `finally` block to guarantee clean execution.

### 5. Mutual TLS Authentication via SSM & `/tmp` Caching
* **Challenge:** The OpenTicket API requires mTLS client certificate authentication. The Python `requests` library requires file system paths to the client certificate and private key, but environment variables only pass raw text strings.
* **Solution:** Stored the encrypted certificate strings in AWS SSM Parameter Store. On Lambda cold start, credentials are written to the local `/tmp` execution directory as temporary files. The files persist across warm container re-invocations, minimizing SSM network calls.

---

## Analytics & Downstream BI Reporting

QuickSight connects directly to the MySQL RDS SQL views and refreshes daily, powering an interactive 5-page dashboard built for executive decision-making and client reporting.

*(Insert short video clip or GIF of the QuickSight Dashboard here)*

### 5 Dedicated Dashboard Pages
1. **Ticket Analytics:** Breakdown of ticket volumes, dollar values, approval durations, and status distribution comparisons (canceled, disputed, approved) by supplier and submission method.
2. **Invoice Analytics:** Financial totals, invoice counts, payment status distributions, and macro turnaround lag times.
3. **Submission Source Comparison:** Side-by-side bar charts comparing EMI automated API volume versus client manual web portal entries across supplier and buyer accounts.
4. **Time & User Behavior Analysis:** Features monthly/quarterly distribution bar charts breaking down manual ticket creation by individual user names and company emails. This allows management to isolate user-based manual entry habits for each supplier.
5. **Joined View Table:** A unified spreadsheet view combining ticket and invoice line items via a `FULL OUTER JOIN` for client auditing and CSV/Excel exports.

---

## Repository Structure

```text

├── openticket_lambdas/  
└────template.yaml                    # AWS SAM Infrastructure as Code template
|    ├── samconfig.toml                   # SAM CLI deployment parameters
|    └── lambda_fanout/                   # Lambda 1: Supplier iterator & SQS publisher
|    |       ├── app.py
|    |       └── requirements.txt
|    └── lambda_worker/                   # Lambda 2: OpenTicket API extraction & MySQL upsert
|    |       ├── app.py
|    |       ├── api_helper.py                # mTLS SSL certificate handler & API requester
|    |       ├── db_helper.py                 # SQLAlchemy engine & timestamp upsert logic
|    |       └── requirements.txt
|    ├── batch_backfill_handler/          # Lambda 3: S3 JSON batch publisher
|    │       ├── app.py
|    │       └── requirements.txt
|    ├── batch_backfill_operation/        # Lambda 4: Reads JSON & updates DB via staging tables
|    │       ├── app.py
|    │       └── requirements.txt
└── openinvoice_lambda/              # Lambda 5: S3 XLSX reader, dedup & MySQL upsert
    ├── app.py
    └── requirements.txt
```

---

## Results & Business Impact

* **Fully Automated Dual Pipeline:** Replaced time-consuming manual reporting with a hands-off, automated data pipeline combining API extractions and S3 file uploads.
* **Direct Sales Enablement:** Daily QuickSight refreshes empower the owner and sales team to identify manual portal usage and contact suppliers to pitch B2B automation services.
* **Targeted User Insights:** User-level email tracking pinpoints exactly which supplier employees enter manual tickets, giving sales concrete figures on wasted payroll.
* **Quantified Cash Flow Acceleration:** Proved that EMI's B2B automation reduces approval lag times and lowers dispute/cancellation rates, helping suppliers get paid faster.
* **High Scalability & Resiliency:** Processes 25+ suppliers in parallel with isolated error handling and instant email alerts via CloudWatch/SNS within 2 minutes of any failure.
