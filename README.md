# Submission Analytics Pipeline
## Automated Dual-Source Ingestion & BI Reporting for OpenTicket & OpenInvoice Data

### Tech Stack & Tools
* **Core AWS Services:** AWS Lambda, Amazon S3, Amazon SQS, AWS EventBridge, Amazon CloudWatch, Amazon SNS, AWS SSM Parameter Store, AWS VPC
* **Database & Analytics:** Amazon RDS (MySQL), AWS Glue, Amazon Athena, Amazon QuickSight
* **Languages & Libraries:** Python 3.13, Pandas, SQLAlchemy, PyMySQL, AWSWrangler, PyArrow, Requests, SAM CLI
* **Upstream Sources:** OpenTicket API (mTLS), OpenInvoice (Power Automate / S3 XLSX exports)

---

## Project Overview & Business Goal

### Business Context & Background
EMI submits field service tickets and invoices on behalf of oil and gas suppliers to their corporate buyers. Submissions run through two primary platforms: **OpenTicket** and **OpenInvoice** (both owned by Enverus). In field operations, once a ticket is approved inside OpenTicket, it is flipped into an invoice inside OpenInvoice. Because ticket approvals directly drive invoice creation, tracking activity across both systems is critical to understanding the complete financial lifecycle.

### The Dual-Source Technical Challenge
Although both platforms hold connected data, system access differs significantly between them:
* **OpenTicket (Automated API Route):** The API returns one JSON object per receipt containing the full history of that ticket, including all timestamps, statuses, and party information. This object updates whenever there is a change to that ticket. The API is accessed via mutual TLS using a client certificate registered with OpenInvoice.
* **OpenInvoice (S3 File Ingestion Route):** Direct API access is unavailable. OpenInvoice data is retrieved as multi-row Excel reports, downloaded via an automated Power Automate flow, and dropped into an S3 landing bucket. Unlike the API, these reports are snapshot-based. Each time an invoice status changes, a new row is added. The same invoice number can appear across multiple rows with different statuses and owners.

Joining these two sources into a clean, accurate, non-duplicated view required designing different deduplication and upsert strategies for each.

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

<img width="2736" height="3280" alt="Enverus_submission_analytics_pipeline" src="https://github.com/user-attachments/assets/8d009d80-a6af-4a43-9805-619d1434389d" />


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

### 1. Fanout + SQS Architecture over Monolithic Lambda Loops
* **Challenge:** Each supplier's API call is independent and takes between 1 to 5 minutes. A single Lambda looping through 25+ suppliers sequentially would risk hitting the 15-minute AWS execution timeout and would fail all suppliers if one timed out.
* **Solution:** Used a Fanout pattern via SQS. The controller Lambda finishes in seconds by sending one message per supplier to an SQS queue. SQS then triggers separate worker Lambda invocations in parallel, giving each supplier isolated execution and failure handling.

### 2. Migration to MySQL RDS over S3 / Parquet / Athena
* **Challenge:** The pipeline started with Parquet files on S3 and Athena views. However, OpenTicket and OpenInvoice have completely different data structures, and the client later requested a single joined view across both. Adding new fields required backfilling hundreds of Parquet files, updating Glue tables, and rewriting Athena views.
* **Solution:** Migrated the data storage layer to Amazon RDS (MySQL). Adding a new field now only requires a simple `ALTER TABLE ADD COLUMN` command. Joining ticket and invoice data is also much cleaner and faster using standard SQL views inside MySQL than doing cross-dataset joins in Athena.

### 3. Last-Action Timestamp Upsert Logic
* **Challenge:** The OpenTicket API returns the full history of a receipt, which can be re-fetched across multiple pipeline runs as statuses update. Standard `INSERT` queries fail on duplicate keys, while blind updates risk overwriting fresh data if payloads arrive out of order.
* **Solution:** Built an `ON DUPLICATE KEY UPDATE` query that checks the incoming `last_action_timestamp`. Incoming fields are only overwritten if the incoming record's timestamp is newer than what is currently stored in the database.

### 4. Staging Table Pattern for Parallel Batch Updates
* **Challenge:** A secondary Lambda processes S3 JSON files to update `invoice_number` values on existing ticket rows. Because multiple workers run in parallel, updating the main table at the same time could lead to race conditions or deadlocks.
* **Solution:** Each worker Lambda generates a uniquely named temporary staging table (`staging_{request_id}`), writes its local batch updates there, runs the update join against the main table, and drops the staging table inside a `finally` block to guarantee cleanup even if an error occurs.

### 5. Mutual TLS Authentication via SSM & `/tmp` Caching
* **Challenge:** The OpenTicket API requires client certificate authentication. The certificate and private key are stored in SSM Parameter Store, but the Python `requests` library needs actual file paths (not raw text strings) for its SSL configuration.
* **Solution:** Lambda fetches the certificate strings from SSM on startup and writes them as temporary files to `/tmp`. Because files persist across warm Lambda container invocations, the SSM fetch only happens during cold starts.

### 6. VPC & IP Whitelisting for OpenInvoice
* **Challenge:** The OpenInvoice platform requires all incoming API and file traffic to originate from specific, authorized IP addresses, which prevents standard public Lambda execution.
* **Solution:** Configured the OpenInvoice Lambda inside a custom AWS VPC with dedicated security groups and static outbound Elastic IPs (via NAT Gateway), ensuring all outbound requests match the whitelisted IP addresses.

### 7. DLQ + CloudWatch Alarms for Observability
* **Challenge:** Need fast, reliable visibility into pipeline failures without swallowing errors inside custom `try/except` blocks.
* **Solution:** Allowed Lambda exceptions to propagate naturally. SQS automatically retries failed messages up to 3 times before routing them to a Dead-Letter Queue (DLQ). A CloudWatch alarm monitors the DLQ and sends an SNS email alert within 2 minutes of any failure.

---

## Analytics & Downstream BI Reporting

QuickSight connects directly to the MySQL RDS SQL views and refreshes daily, powering an interactive 5-page dashboard built for executive decision-making and client reporting.

[![Watch Demo](https://img.shields.io/badge/▶️_Watch_the_B2B_QuickSight_Dashboard_Video_Demo-B1F6FC?style=for-the-badge)](https://youtu.be/5PW44m2eUOg)

<p align="center">
  <a href="https://youtu.be/5PW44m2eUOg" target="_blank">
    <img src="https://img.youtube.com/vi/5PW44m2eUOg/maxresdefault.jpg" alt="B2B QuickSight Dashboard Demo" width="100%" />
  </a>
</p>


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
│   ├── template.yaml                    # AWS SAM Infrastructure as Code template
│   ├── samconfig.toml                   # SAM CLI deployment parameters
│   ├── lambda_fanout/                   # Lambda 1: Supplier iterator & SQS publisher
│   │   ├── app.py
│   │   └── requirements.txt
│   ├── lambda_worker/                   # Lambda 2: OpenTicket API extraction & MySQL upsert
│   │   ├── app.py
│   │   ├── api_helper.py                # mTLS SSL certificate handler & API requester
│   │   ├── db_helper.py                 # SQLAlchemy engine & timestamp upsert logic
│   │   └── requirements.txt
│   ├── batch_backfill_handler/          # Lambda 3: S3 JSON batch publisher
│   │   ├── app.py
│   │   └── requirements.txt
│   └── batch_backfill_operation/        # Lambda 4: Reads JSON & updates DB via staging tables
│       ├── app.py
│       └── requirements.txt
└── openinvoice_lambda/                  # Lambda 5: S3 XLSX reader, dedup & MySQL upsert
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
