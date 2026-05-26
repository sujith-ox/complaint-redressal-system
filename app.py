import streamlit as st
import plotly.express as px
import pandas as pd
import logging
from data import load_complaints

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Complaint Dashboard",
    layout="wide"
)

st.title("Complaint Redressal Dashboard")

# ── Load data ─────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_data():
    return load_complaints(), pd.Timestamp.now()

try:
    df, last_fetched = get_data()
    st.caption(f"Last updated: {last_fetched.strftime('%d %b %Y, %I:%M:%S %p')}")
except Exception as e:
    logger.error(f"Failed to load complaint data: {e}", exc_info=True)
    st.error(f"Failed to load complaint data: {e}")
    st.info("Please check that the data source is available and try refreshing.")
    st.stop()

# ── Dynamic assignee color palette ───────────────────────────
# Generated from a fixed palette so new team members always get a color
_PALETTE = [
    '#3b82f6', '#ef4444', '#22c55e', '#f97316', '#a78bfa',
    '#06b6d4', '#ec4899', '#eab308', '#14b8a6', '#f43f5e',
]
def make_assignee_colors(assignees):
    return {name: _PALETTE[i % len(_PALETTE)] for i, name in enumerate(sorted(assignees))}

# ── Sidebar filters ───────────────────────────────────────────
# ── Filter defaults (used for reset) ─────────────────────────
_status_options   = sorted(df['status'].unique())
_priority_options = sorted(df['priority'].unique())
_assignee_options = sorted(df['assigned_to'].unique())
_date_min = df['date_raised'].min().date()
_date_max = df['date_raised'].max().date()

# Reset counter — incrementing it changes widget keys, forcing Streamlit
# to treat them as new widgets and initialize from default= values.
# This is the only reliable way to reset sidebar widgets in Streamlit.
if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

_rc = st.session_state['reset_counter']  # suffix for all widget keys

with st.sidebar:
    st.header("Filters")

    status_filter = st.multiselect(
        "Status", options=_status_options, default=_status_options,
        key=f'status_filter_{_rc}'
    )
    priority_filter = st.multiselect(
        "Priority", options=_priority_options, default=_priority_options,
        key=f'priority_filter_{_rc}'
    )
    assignee_filter = st.multiselect(
        "Assigned to", options=_assignee_options, default=_assignee_options,
        key=f'assignee_filter_{_rc}'
    )

    # Date range — guard against missing end date
    date_range = st.date_input(
        "Date range",
        value=[_date_min, _date_max],
        min_value=_date_min,
        max_value=_date_max,
        key=f'date_range_{_rc}'
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        date_start, date_end = date_range[0], date_range[1]
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        date_start, date_end = date_range[0], _date_max
    else:
        date_start = date_range if not isinstance(date_range, (list, tuple)) else _date_min
        date_end = _date_max

    st.divider()

    # Reset button at the bottom — after all filters
    if st.button("Reset filters", use_container_width=True):
        st.session_state['reset_counter'] += 1
        st.rerun()

# ── Apply filters ─────────────────────────────────────────────
filtered = df[
    df['status'].isin(status_filter) &
    df['priority'].isin(priority_filter) &
    df['assigned_to'].isin(assignee_filter) &
    (df['date_raised'] >= pd.Timestamp(date_start)) &
    (df['date_raised'] <= pd.Timestamp(date_end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
]

# FIX #3: Empty state guard — stop rendering charts if no data
if filtered.empty:
    st.warning("No complaints match the current filters. Try adjusting the filters in the sidebar.")
    st.stop()

# ── KPI metrics ───────────────────────────────────────────────
st.subheader("Overview")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Complaints", len(filtered))
k2.metric("Open",        len(filtered[filtered['status'] == 'Open']))
k3.metric("In Progress", len(filtered[filtered['status'] == 'In Progress']))
k4.metric("Resolved",    len(filtered[filtered['status'] == 'Resolved']))
k5.metric("Closed",      len(filtered[filtered['status'] == 'Closed']))
k6.metric("🚨 SLA Breached", int(filtered['sla_breached_bool'].sum()))

st.divider()

# ── Helpers ───────────────────────────────────────────────────

BAR_LIMIT = 12

def ytick(max_val):
    if max_val <= 10:     return 1
    elif max_val <= 30:   return 5
    elif max_val <= 100:  return 10
    elif max_val <= 300:  return 50
    elif max_val <= 1000: return 100
    else:                 return 200

def auto_granularity(date_series):
    """
    Pick granularity keeping bars ≤ BAR_LIMIT.
    Returns (freq, label, tick_fmt, x_title).
    """
    # FIX #11: guard against empty or single-value series
    if date_series.empty or date_series.nunique() < 2:
        return 'D', 'Daily', '%Y-%m-%d', 'Date'
    span_days = (date_series.max() - date_series.min()).days
    if span_days < 14:
        return 'D', 'Daily',     '%Y-%m-%d',  'Date'
    elif span_days < 90:
        return 'W', 'Weekly',    '%b %d, %Y', 'Week Starting'
    elif span_days < 730:
        return 'M', 'Monthly',   '%b %Y',     'Month'
    else:
        return 'Q', 'Quarterly', '%b %Y',     'Quarter Starting'

def group_by_period(date_series, freq):
    """Group dates into periods, return DataFrame ['period', 'count']."""
    periods = date_series.dt.to_period(freq).dt.start_time.rename('period')
    result = (
        periods
        .groupby(periods)
        .count()
        .reset_index(name='count')
        .sort_values('period')
        .reset_index(drop=True)
    )
    return result

def drop_incomplete_if_safe(time_data, freq):
    """Drop current incomplete period only if ≥2 complete bars remain."""
    if len(time_data) <= 2:
        return time_data
    now = pd.Timestamp.now()
    if freq == 'D':
        cutoff = now.normalize()
    elif freq == 'W':
        cutoff = (now - pd.to_timedelta(now.dayofweek, unit='D')).normalize()
    elif freq == 'M':
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif freq == 'Q':
        start_month = ((now.month - 1) // 3) * 3 + 1
        cutoff = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif freq == 'Y':
        cutoff = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return time_data
    trimmed = time_data[time_data['period'] < cutoff].reset_index(drop=True)
    return trimmed if len(trimmed) >= 2 else time_data

def cap_bars(time_data, limit=BAR_LIMIT):
    """Keep only the most recent `limit` bars."""
    if len(time_data) > limit:
        return time_data.tail(limit).reset_index(drop=True)
    return time_data

# ── Color palettes ────────────────────────────────────────────
PRIORITY_COLORS = {'High': '#ef4444', 'Medium': '#f97316', 'Low': '#22c55e'}
STATUS_COLORS   = {
    'Open': '#3b82f6', 'In Progress': '#f97316',
    'Resolved': '#22c55e', 'Closed': '#94a3b8',
    'Acknowledged': '#a78bfa', 'Awaiting Info': '#fbbf24',
    'Rejected': '#f43f5e'
}
ISSUE_COLORS    = {'Bug': '#3b82f6', 'Change Request': '#93c5fd', 'Data Fix': '#ef4444'}
SLA_COLORS      = {'Breached': '#ef4444', 'On Time': '#22c55e'}

# FIX #13: Dynamic assignee colors — handles any team member from DB
ASSIGNEE_COLORS = make_assignee_colors(df['assigned_to'].unique())

# ── Row 2: Issue type and Priority ────────────────────────────
st.subheader("Breakdown")
c1, c2 = st.columns(2)

with c1:
    data = filtered['issue_type'].value_counts().reset_index()
    fig = px.bar(
        data, x='issue_type', y='count',
        title="Complaints by Issue Type",
        color='issue_type', text='count',
        color_discrete_map=ISSUE_COLORS,
        labels={'issue_type': 'Issue Type', 'count': 'Number of Complaints'}
    )
    fig.update_traces(textposition='outside', hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title="Issue Type", yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(data['count'].max()), rangemode='tozero')
    )
    st.plotly_chart(fig, use_container_width=True)

with c2:
    data = filtered['priority'].value_counts().reset_index()
    fig = px.bar(
        data, x='priority', y='count',
        title="Complaints by Priority",
        color='priority',
        color_discrete_map=PRIORITY_COLORS,
        text='count',
        labels={'priority': 'Priority', 'count': 'Number of Complaints'}
    )
    fig.update_traces(textposition='outside', hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title="Priority", yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(data['count'].max()), rangemode='tozero')
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Row 3: Over time and per person ──────────────────────────
c3, c4 = st.columns(2)

with c3:
    freq, label, tick_fmt, x_title = auto_granularity(filtered['date_raised'])
    time_data = group_by_period(filtered['date_raised'], freq)
    time_data = drop_incomplete_if_safe(time_data, freq)
    time_data = cap_bars(time_data)

    fig = px.bar(
        time_data, x='period', y='count',
        title=f"Complaints Over Time ({label})",
        text='count'
    )
    fig.update_traces(textposition='outside', hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title=x_title, yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(time_data['count'].max()), rangemode='tozero'),
        xaxis=dict(tickformat=tick_fmt, tickangle=-30 if len(time_data) > 8 else 0)
    )
    st.plotly_chart(fig, use_container_width=True)

with c4:
    data = filtered['assigned_to'].value_counts().reset_index()
    show_text = data['count'].max() < 500
    fig = px.bar(
        data, x='assigned_to', y='count',
        title="Load per Team Member",
        color='assigned_to',
        color_discrete_map=ASSIGNEE_COLORS,
        text='count' if show_text else None,
        labels={'assigned_to': 'Team Member', 'count': 'Number of Complaints'}
    )
    if show_text:
        fig.update_traces(textposition='outside')
    fig.update_traces(hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title="Team Member", yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(data['count'].max()), rangemode='tozero')
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Row 4: Status and SLA ─────────────────────────────────────
c5, c6 = st.columns(2)

with c5:
    data = filtered['status'].value_counts().reset_index()
    fig = px.bar(
        data, x='status', y='count',
        title="Complaints by Status",
        color='status', text='count',
        color_discrete_map=STATUS_COLORS,
        labels={'status': 'Status', 'count': 'Number of Complaints'}
    )
    fig.update_traces(textposition='outside', hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title="Status", yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(data['count'].max()), rangemode='tozero')
    )
    st.plotly_chart(fig, use_container_width=True)

with c6:
    sla = filtered.groupby(['priority', 'sla_breached']).size().reset_index(name='count')
    fig = px.bar(
        sla, x='priority', y='count',
        color='sla_breached', barmode='group',
        title="SLA Breached vs On Time",
        color_discrete_map=SLA_COLORS,
        text='count',
        labels={'priority': 'Priority', 'count': 'Number of Complaints', 'sla_breached': 'SLA Status'}
    )
    fig.update_traces(textposition='outside', hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title="Priority", yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(sla['count'].max()), rangemode='tozero'),
        legend_title="SLA Status"
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Row 5: Response time and trend ────────────────────────────
c7, c8 = st.columns(2)

with c7:
    avg_response = filtered.groupby('priority')['response_hours'].mean().reset_index()
    avg_response.columns = ['priority', 'avg_response_hours']
    avg_response['avg_response_hours'] = avg_response['avg_response_hours'].round(1)
    fig = px.bar(
        avg_response, x='priority', y='avg_response_hours',
        title="Avg Response Time by Priority",
        color='priority',
        color_discrete_map=PRIORITY_COLORS,
        text='avg_response_hours',
        labels={'priority': 'Priority', 'avg_response_hours': 'Avg Response Time (hrs)'}
    )
    fig.update_traces(textposition='outside', hovertemplate=None, hoverinfo='skip')
    fig.update_layout(
        uniformtext_minsize=8, uniformtext_mode='hide',
        xaxis_title="Priority", yaxis_title="Avg Response Time (hrs)",
        yaxis=dict(rangemode='tozero')
    )
    st.plotly_chart(fig, use_container_width=True)

with c8:
    valid_periods = set(time_data['period'])
    trend = filtered.copy()
    trend['period'] = trend['date_raised'].dt.to_period(freq).dt.start_time
    trend = trend[trend['period'].isin(valid_periods)]
    trend = trend.groupby(['period', 'issue_type']).size().reset_index(name='count')
    trend['label'] = trend['count'].astype(str)
    period_max = trend.groupby('period')['count'].sum().max() if len(trend) > 0 else 10

    fig = px.bar(
        trend, x='period', y='count',
        color='issue_type',
        title=f"Complaint Trend by Issue Type ({label})",
        barmode='stack',
        text='label',
        labels={'period': x_title, 'count': 'Number of Complaints', 'issue_type': 'Issue Type'}
    )
    fig.update_traces(
        textposition='inside',
        textfont=dict(size=11, color='white'),
        hovertemplate=None, hoverinfo='skip'
    )
    fig.update_layout(
        xaxis_title=x_title, yaxis_title="Number of Complaints",
        yaxis=dict(dtick=ytick(period_max), rangemode='tozero'),
        legend_title="Issue Type",
        xaxis=dict(tickformat=tick_fmt, tickangle=-30 if len(trend['period'].unique()) > 8 else 0)
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Row 6: Raw table ──────────────────────────────────────────
st.subheader("All Complaints")

MAX_ROWS = 500
display_df = filtered[[
    'request_id', 'date_raised', 'client_name',
    'issue_type', 'priority', 'status',
    'assigned_to', 'sla_breached', 'resolution_hours_display'
]].copy()

display_df['date_raised'] = display_df['date_raised'].dt.strftime('%Y-%m-%d')
display_df['resolution_hours_display'] = pd.to_numeric(
    display_df['resolution_hours_display'], errors='coerce'
)

# FIX #7: sort by date descending so most recent complaints appear first
display_df = display_df.sort_values('date_raised', ascending=False)

if len(display_df) > MAX_ROWS:
    st.caption(f"Showing most recent {MAX_ROWS} of {len(filtered):,} complaints. Use filters to narrow down.")
    display_df = display_df.head(MAX_ROWS)

st.dataframe(
    display_df.rename(columns={
        'request_id': 'Request ID',
        'date_raised': 'Date Raised',
        'client_name': 'Client',
        'issue_type': 'Issue Type',
        'priority': 'Priority',
        'status': 'Status',
        'assigned_to': 'Assigned To',
        'sla_breached': 'SLA Status',
        'resolution_hours_display': 'Resolution (hrs)'
    }),
    use_container_width=True,
    hide_index=True
)

col_refresh, col_spacer = st.columns([1, 5])
with col_refresh:
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()