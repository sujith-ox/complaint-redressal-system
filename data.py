import logging
import pandas as pd
from db import get_engine

logger = logging.getLogger(__name__)

USE_DUMMY = True

# Columns required in the raw data source
REQUIRED_COLUMNS = [
    'request_id', 'date_raised', 'client_name',
    'issue_type', 'priority', 'status',
    'assigned_to', 'first_response_at', 'date_resolved'
]

def validate_schema(df):
    """Raise a clear error if required columns are missing."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Data source is missing required columns: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )

def load_complaints():
    if USE_DUMMY:
        logger.info("Loading data from dummy CSV.")
        try:
            df = pd.read_csv('dummy_data_extended.csv')
            logger.info(f"Loaded {len(df)} rows from CSV.")
        except FileNotFoundError:
            logger.error("dummy_data_extended.csv not found.")
            raise FileNotFoundError(
                "dummy_data_extended.csv not found. "
                "Make sure the file is in the same directory as app.py."
            )
    else:
        logger.info("Connecting to database.")
        try:
            engine = get_engine()
            df = pd.read_sql("SELECT * FROM complaints", engine)
            logger.info(f"Loaded {len(df)} rows from database.")
        except Exception as e:
            logger.error(f"Database connection failed: {e}", exc_info=True)
            raise ConnectionError(f"Could not connect to the database: {e}")

    validate_schema(df)
    logger.info("Schema validation passed.")

    issue_type_map = {
        'BUG': 'Bug',
        'DATA_FIX': 'Data Fix',
        'CHANGE_REQUEST': 'Change Request'
    }
    priority_map = {
        'HIGH': 'High',
        'MEDIUM': 'Medium',
        'LOW': 'Low'
    }
    status_map = {
        'OPEN': 'Open',
        'CLOSED': 'Closed',
        'RESOLVED': 'Resolved',
        'IN_PROGRESS': 'In Progress',
        'ACKNOWLEDGED': 'Acknowledged',
        'AWAITING_INFO': 'Awaiting Info',
        'REJECTED': 'Rejected'
    }
    assigned_map = {
        'JENIL': 'Jenil',
        'ASKAR': 'Askar',
        'AJITHA': 'Ajitha',
        'JENISH': 'Jenish',
        'UNASSIGNED': 'Unassigned'
    }

    df['issue_type']  = df['issue_type'].map(issue_type_map).fillna(df['issue_type'])
    df['priority']    = df['priority'].map(priority_map).fillna(df['priority'])
    df['status']      = df['status'].map(status_map).fillna(df['status'])
    df['assigned_to'] = df['assigned_to'].map(assigned_map).fillna(df['assigned_to'])

    for col in ['date_raised', 'first_response_at', 'date_resolved']:
        df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

    # Strip timezone for clean display
    for col in ['date_raised', 'first_response_at', 'date_resolved']:
        df[col] = df[col].dt.tz_localize(None)

    # Response time
    df['response_hours'] = (
        df['first_response_at'] - df['date_raised']
    ).dt.total_seconds() / 3600
    df.loc[df['response_hours'] < 0, 'response_hours'] = None

    # Resolution time — use now for open tickets so SLA accrues
    now = pd.Timestamp.now()
    resolution_end = df['date_resolved'].fillna(now)
    df['resolution_hours'] = (
        resolution_end - df['date_raised']
    ).dt.total_seconds() / 3600

    # SLA thresholds: High=8hrs, Medium=48hrs, Low=120hrs
    df['sla_breached_bool'] = (
        ((df['priority'] == 'High')   & (df['resolution_hours'] > 8))   |
        ((df['priority'] == 'Medium') & (df['resolution_hours'] > 48))  |
        ((df['priority'] == 'Low')    & (df['resolution_hours'] > 120))
    )

    # Display-only resolution (NaN for unresolved — renders blank in table)
    df['resolution_hours_display'] = (
        df['date_resolved'] - df['date_raised']
    ).dt.total_seconds() / 3600
    df['resolution_hours_display'] = df['resolution_hours_display'].round(1)

    # Readable SLA label
    df['sla_breached'] = df['sla_breached_bool'].map({True: 'Breached', False: 'On Time'})

    logger.info("Data processing complete.")
    return df