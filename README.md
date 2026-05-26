# Complaint Redressal Dashboard

A Streamlit dashboard for tracking and analyzing client complaints — with SLA monitoring, team workload distribution, and trend analysis.

---

## What it does

- Tracks complaints by **status**, **priority**, **issue type**, and **assignee**
- Monitors **SLA breaches** (High: 8h · Medium: 48h · Low: 120h)
- Shows **response time** averages by priority
- Auto-adjusts chart granularity (daily → weekly → monthly → quarterly) based on date range
- Supports both **CSV (dummy)** and **PostgreSQL** as data sources

---

## Stack

- **Frontend** — [Streamlit](https://streamlit.io)
- **Charts** — Plotly Express
- **Database** — PostgreSQL via SQLAlchemy (`psycopg2`)

---

## Setup

```bash
pip install streamlit plotly sqlalchemy psycopg2-binary pandas python-dotenv
```

Copy `.env.example` to `.env` and fill in your credentials:

```env
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_db
DB_SCHEMA=task       # optional, defaults to "task"
```

Run:

```bash
streamlit run app.py
```

---

## Data source

Toggle between dummy CSV and live DB in `data.py`:

```python
USE_DUMMY = True   # False → reads from PostgreSQL
```

When using CSV, place `dummy_data_extended.csv` in the same directory as `app.py`.

**Required columns:**

`request_id`, `date_raised`, `client_name`, `issue_type`, `priority`, `status`, `assigned_to`, `first_response_at`, `date_resolved`

---

## Project structure

```
├── app.py                   # Streamlit UI
├── data.py                  # Data loading, SLA logic, preprocessing
├── db.py                    # SQLAlchemy engine with env var validation
├── dummy_data_extended.csv  # Sample data (not committed)
└── .env.example             # Environment variable template
```
