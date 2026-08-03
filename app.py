import difflib
import glob
import hashlib
import json
import os
from pathlib import Path
import re

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, dash_table


ROOT_DIR = Path(__file__).resolve().parent
CACHE_PATH = ROOT_DIR / 'data' / 'stop_locations.json'


def load_data():
    repo_root = str(ROOT_DIR)
    candidate_csv = sorted(glob.glob(os.path.join(repo_root, 'IR-1230*.csv')))
    route_order_paths = []
    ridership_paths = []

    for path in candidate_csv:
        try:
            sample = pd.read_csv(path, nrows=0, encoding='utf-8-sig')
        except Exception:
            continue
        columns = [col.strip() for col in sample.columns]
        if 'Stop Sequence' in columns and 'Stop' in columns and 'Date' not in columns:
            route_order_paths.append(path)
        elif 'Date' in columns and 'Boardings' in columns and 'Alightings' in columns:
            ridership_paths.append(path)

    if not ridership_paths:
        sample_path = os.path.join(repo_root, 'data', 'ridership_sample.csv')
        if os.path.exists(sample_path):
            ridership_paths.append(sample_path)

    if not ridership_paths:
        raise FileNotFoundError('No ridership CSV files found in repository. Expected IR-1230*.csv or data/ridership_sample.csv')

    rename_map = {
        'Route': 'route_id',
        'Direction': 'direction',
        'Stop Name': 'stop_name',
        'Stop': 'stop_name',
        'Stop ID': 'stop_id',
        'Date': 'date',
        'Boardings': 'boardings',
        'Alightings': 'alightings',
    }
    direction_map = {
        'Northbound': 'North',
        'Southbound': 'South',
        'Eastbound': 'East',
        'Westbound': 'West',
    }

    frames = []
    for path in ridership_paths:
        frame = pd.read_csv(path, encoding='utf-8-sig')
        frame = frame.rename(columns=rename_map)

        if 'date' in frame.columns:
            frame['date'] = pd.to_datetime(frame['date'], errors='coerce', dayfirst=True)

        frame = frame.loc[:, ~frame.columns.duplicated(keep='last')].copy()

        for col in ['route_id', 'stop_id', 'stop_name', 'direction']:
            if col in frame.columns:
                frame[col] = frame[col].astype(str).fillna('').str.strip()

        for col in ['boardings', 'alightings', 'passengers']:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')

        if 'boardings' in frame.columns and 'alightings' in frame.columns:
            frame['boardings'] = frame['boardings'].fillna(0)
            frame['alightings'] = frame['alightings'].fillna(0)
            frame['passengers'] = frame['boardings'] + frame['alightings']
        elif 'passengers' in frame.columns:
            frame['passengers'] = frame['passengers'].fillna(0)
        else:
            frame['passengers'] = 0

        frames.append(frame)

    df = pd.concat(frames, ignore_index=True, sort=False)
    df = df.loc[:, ~df.columns.duplicated(keep='last')].copy()

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
    else:
        df['date'] = pd.NaT

    df['route_id'] = df['route_id'].astype(str).str.strip().replace({'nan': ''})
    df['stop_id'] = df['stop_id'].astype(str).str.strip().replace({'nan': ''})
    df['stop_name'] = df['stop_name'].astype(str).str.strip().replace({'nan': 'Unknown'})
    df['direction'] = df['direction'].astype(str).replace(direction_map).str.strip().replace({'nan': 'Unknown'})

    if 'passengers' not in df.columns:
        df['passengers'] = 0

    route_order = pd.DataFrame()
    if route_order_paths:
        route_order_parts = []
        for path in route_order_paths:
            order_frame = pd.read_csv(path, encoding='utf-8-sig')
            order_frame = order_frame.rename(columns={
                'Route': 'route_id',
                'Direction': 'direction',
                'Stop Sequence': 'stop_sequence',
                'Stop': 'raw_stop',
            })
            route_order_parts.append(order_frame)
        route_order = pd.concat(route_order_parts, ignore_index=True, sort=False)
        route_order['route_id'] = route_order['route_id'].astype(str).str.strip()
        route_order['direction'] = route_order['direction'].astype(str).replace(direction_map).str.strip()
        route_order['stop_sequence'] = pd.to_numeric(route_order['stop_sequence'], errors='coerce')
        route_order[['stop_name', 'stop_id']] = route_order['raw_stop'].str.extract(r'^(.*)\s+\[(\d+)\]$')
        route_order['stop_id'] = route_order['stop_id'].fillna('').astype(str).str.strip()
        route_order['stop_name'] = route_order['stop_name'].fillna(route_order['raw_stop']).str.strip()
        route_order = route_order[['route_id', 'direction', 'stop_sequence', 'stop_id', 'stop_name']]

    return df, route_order


def safe_days(dff):
    if dff['date'].notna().any():
        span = dff['date'].max() - dff['date'].min()
        return max(int(span.days) + 1, 1)
    return 1


def choose_canonical_stop_name(names):
    names = [str(n).strip() for n in names if str(n).strip()]
    if not names:
        return ''
    bad_pattern = re.compile(r'closed|closure|night closures?|until|from\s+\d', re.I)
    preferred = [name for name in names if not bad_pattern.search(name)]
    candidates = preferred or names
    counts = pd.Series(candidates).value_counts()
    return counts.index[0]


def empty_figure(title='No data available'):
    fig = go.Figure()
    fig.add_annotation(
        x=0.5,
        y=0.5,
        text=title,
        showarrow=False,
        font={'size': 16, 'color': '#65748b'},
        xanchor='center',
        yanchor='middle',
    )
    fig.update_layout(
        xaxis={'visible': False},
        yaxis={'visible': False},
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
    )
    return fig


def load_stop_location_cache(cache_path=CACHE_PATH):
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception:
            return {}
    return {}


def save_stop_location_cache(cache, cache_path=CACHE_PATH):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as handle:
        json.dump(cache, handle, indent=2)


def fallback_coordinates(stop_name):
    hash_value = hashlib.md5(stop_name.encode('utf-8')).hexdigest()
    seed = int(hash_value[:8], 16)
    lat = -28.15 + (seed % 200) / 20000
    lon = 153.3 + (seed % 300) / 20000
    return {'latitude': round(lat, 5), 'longitude': round(lon, 5)}


def resolve_stop_location(stop_name, cache=None, allow_fallback=False):
    if cache is None:
        cache = {}
    if stop_name in cache:
        return cache[stop_name]
    if allow_fallback:
        result = fallback_coordinates(stop_name)
        cache[stop_name] = result
        return result
    return None


def normalize_stop_name(name):
    if not name:
        return ''
    text = str(name)
    text = re.sub(r'\s*\[\d+\]$', '', text)
    text = re.sub(r'\b(station|stn|bus stop|busstop|stop)\b', '', text, flags=re.I)
    text = re.sub(r'\b(closed|closure|closures|permanent|permanently|until|from|\d{1,2}\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)\b).*$', '', text, flags=re.I)
    text = re.sub(r'\b(pde|rd|dr|st|ave|av|hwy|highway|terrace|tce|cres|bvd|bvd|ct|place|lane|ln|circuit|cir|way|gr|grove|op|esplanade)\b', lambda m: m.group(1).lower(), text, flags=re.I)
    text = re.sub(r'[^a-z0-9 ]+', ' ', text.lower())
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def find_stop_coordinate(stop_name, cache):
    if not stop_name:
        return None
    if stop_name in cache:
        return cache[stop_name]
    normalized = normalize_stop_name(stop_name)
    normalized_cache = {normalize_stop_name(k): k for k in cache.keys()}
    if normalized in normalized_cache:
        return cache[normalized_cache[normalized]]
    matches = difflib.get_close_matches(normalized, list(normalized_cache.keys()), n=1, cutoff=0.75)
    if matches:
        return cache[normalized_cache[matches[0]]]
    return None


def build_stop_location_lookup(stop_names, cache_path=CACHE_PATH, allow_fallback=False):
    cache = load_stop_location_cache(cache_path)
    stop_names = [name for name in stop_names if name and str(name).strip()]
    unique_names = sorted(set(stop_names))
    resolved = {}
    for stop_name in unique_names:
        coordinate = find_stop_coordinate(stop_name, cache)
        if coordinate is None and allow_fallback:
            coordinate = resolve_stop_location(stop_name, cache=cache, allow_fallback=True)
        resolved[stop_name] = coordinate
    if allow_fallback:
        save_stop_location_cache(cache, cache_path)
    return resolved


def build_map_data(dff, route_order, stop_lookup, stop_name_by_stop_id):
    dff = dff.copy()
    dff['route_id'] = dff['route_id'].astype(str).str.strip()
    dff['stop_id'] = dff['stop_id'].astype(str).str.strip()
    dff['direction'] = dff['direction'].astype(str).str.strip()

    route_order = route_order.copy()
    route_order['route_id'] = route_order['route_id'].astype(str).str.strip()
    route_order['direction'] = route_order['direction'].astype(str).str.strip()
    route_order['stop_id'] = route_order['stop_id'].astype(str).str.strip()
    route_order['stop_name'] = route_order['stop_name'].astype(str).str.strip()

    route_order['canonical_name'] = route_order['stop_id'].map(stop_name_by_stop_id).fillna(route_order['stop_name'])
    official_stops = route_order[['stop_id', 'canonical_name']].drop_duplicates().rename(columns={'canonical_name': 'stop_name'})

    demand = dff.groupby('stop_id', as_index=False).agg({'passengers': 'sum', 'boardings': 'sum', 'alightings': 'sum'})
    demand['stop_id'] = demand['stop_id'].astype(str).str.strip()
    stop_summary = official_stops.merge(demand, on='stop_id', how='left').fillna({'passengers': 0, 'boardings': 0, 'alightings': 0})
    stop_summary['passengers'] = stop_summary['passengers'].astype(int)
    stop_summary['boardings'] = stop_summary['boardings'].astype(int)
    stop_summary['alightings'] = stop_summary['alightings'].astype(int)
    stop_summary['routes'] = stop_summary['stop_id'].map(dff.groupby('stop_id')['route_id'].nunique().astype(int)).fillna(0).astype(int)
    stop_summary = stop_summary[stop_summary['stop_name'].isin(stop_lookup.keys())]
    stop_summary = stop_summary.sort_values('passengers', ascending=False)

    map_points = []
    for _, row in stop_summary.iterrows():
        location = stop_lookup.get(row['stop_name'])
        if location is None:
            continue
        route_ids = sorted(
            route_order.loc[route_order['stop_id'] == row['stop_id'], 'route_id'].dropna().astype(str).unique()
        )
        map_points.append({
            'stop_id': row['stop_id'],
            'stop_name': row['stop_name'],
            'passengers': int(row['passengers']),
            'boardings': int(row['boardings']),
            'alightings': int(row['alightings']),
            'routes': int(row['routes']),
            'latitude': location['latitude'],
            'longitude': location['longitude'],
            'route_ids': ', '.join(route_ids) if route_ids else 'None',
        })

    map_df = pd.DataFrame(map_points)
    if map_df.empty:
        return map_df, []

    route_lines = []
    if not route_order.empty:
        for route_id in sorted(route_order['route_id'].dropna().unique()):
            for direction in sorted(route_order.loc[route_order['route_id'] == route_id, 'direction'].dropna().unique()):
                ordered = route_order[(route_order['route_id'] == route_id) & (route_order['direction'] == direction)].sort_values('stop_sequence')
                ordered = ordered.merge(map_df[['stop_id', 'latitude', 'longitude']], on='stop_id', how='left')
                ordered = ordered[ordered[['latitude', 'longitude']].notna().all(axis=1)]
                if len(ordered) < 2:
                    continue
                current_segment = []
                for _, row in ordered.iterrows():
                    if current_segment:
                        prev = current_segment[-1]
                        if abs(row['latitude'] - prev['latitude']) > 0.04 or abs(row['longitude'] - prev['longitude']) > 0.04:
                            if len(current_segment) >= 2:
                                route_lines.append({
                                    'route_id': route_id,
                                    'direction': direction,
                                    'lat': [r['latitude'] for r in current_segment],
                                    'lon': [r['longitude'] for r in current_segment],
                                })
                            current_segment = []
                    current_segment.append(row)
                if len(current_segment) >= 2:
                    route_lines.append({
                        'route_id': route_id,
                        'direction': direction,
                        'lat': [r['latitude'] for r in current_segment],
                        'lon': [r['longitude'] for r in current_segment],
                    })

    return map_df, route_lines


def make_kpi(title, value='', id=None):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, className='text-muted text-uppercase mb-2', style={'fontSize': '0.75rem', 'letterSpacing': '0.1em'}),
            html.H3(value, className='mb-0', style={'fontWeight': '700'}),
        ], className='py-3'),
        className='h-100 shadow-sm border-0 bg-white',
        id=id,
    )


def build_map_figure(map_df, route_lines=None, selected_stop_id=None):
    fig = go.Figure()

    if route_lines is None:
        route_lines = []

    if route_lines:
        colors = px.colors.qualitative.Prism
        for index, line in enumerate(route_lines):
            color = colors[index % len(colors)]
            fig.add_trace(go.Scattermapbox(
                lat=line['lat'],
                lon=line['lon'],
                mode='lines',
                line=dict(color=color, width=3),
                name=f"Route {line['route_id']} {line['direction']}",
                hoverinfo='text',
                text=[f"Route {line['route_id']} — {line['direction']}"] * len(line['lat']),
                opacity=0.7,
                showlegend=True,
            ))

    if not map_df.empty:
        customdata = list(zip(map_df['stop_id'], map_df['passengers'], map_df['boardings'], map_df['alightings'], map_df['routes'], map_df['route_ids']))
        fig.add_trace(go.Scattermapbox(
            lat=map_df['latitude'],
            lon=map_df['longitude'],
            mode='markers',
            marker=dict(
                size=(map_df['passengers'] / max(map_df['passengers'].max(), 1) * 34).clip(lower=12, upper=42),
                color=map_df['passengers'],
                colorscale='Blues',
                opacity=0.95,
                colorbar=dict(title='Passengers'),
                showscale=True,
            ),
            text=map_df['stop_name'],
            customdata=customdata,
            hoverlabel=dict(
                bgcolor='rgba(255,255,255,0.98)',
                bordercolor='#2563eb',
                font=dict(color='#111827', size=12),
            ),
            hovertemplate=(
                '<b>%{text}</b><br>'
                'Stop ID: %{customdata[0]}<br>'
                'Passengers: %{customdata[1]:,}<br>'
                'Boardings: %{customdata[2]:,}<br>'
                'Alightings: %{customdata[3]:,}<br>'
                'Routes served: %{customdata[4]}<br>'
                '<span style="font-size:11px;">%{customdata[5]}</span><extra></extra>'
            ),
            hoverinfo='text',
            showlegend=False,
        ))

    if selected_stop_id:
        selected = map_df[map_df['stop_id'] == selected_stop_id]
        if not selected.empty:
            fig.add_trace(go.Scattermapbox(
                lat=[selected.iloc[0]['latitude']],
                lon=[selected.iloc[0]['longitude']],
                mode='markers',
                marker=dict(size=34, color='#f59e0b', symbol='star'),
                hoverinfo='skip',
                showlegend=False,
            ))

    avg_lat = map_df['latitude'].mean() if not map_df.empty else -28.18
    avg_lon = map_df['longitude'].mean() if not map_df.empty else 153.54
    fig.update_layout(
        mapbox=dict(
            style='carto-positron',
            center=dict(lat=avg_lat, lon=avg_lon),
            zoom=10,
        ),
        legend=dict(
            title='Route overlay',
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0,
            font=dict(size=11),
            bgcolor='rgba(255,255,255,0.85)',
        ),
        margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
        paper_bgcolor='white',
        plot_bgcolor='white',
        height=600,
    )
    return fig


def build_summary_cards(dff):
    route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
    route_summary = route_summary.sort_values('passengers', ascending=False)
    stop_summary = dff.groupby(['stop_name'], as_index=False).agg({'passengers': 'sum', 'boardings': 'sum', 'alightings': 'sum'})
    stop_summary = stop_summary.sort_values('passengers', ascending=False)

    total = int(dff['passengers'].sum())
    dominant_route = route_summary.iloc[0]['route_id'] if not route_summary.empty else 'N/A'
    dominant_stop = stop_summary.iloc[0]['stop_name'] if not stop_summary.empty else 'N/A'
    avg_daily = round(total / safe_days(dff), 1) if not dff.empty else 0
    weekday = int(dff.loc[dff['date'].dt.dayofweek < 5, 'passengers'].sum()) if not dff.empty and dff['date'].notna().any() else 0
    weekend = int(dff.loc[dff['date'].dt.dayofweek >= 5, 'passengers'].sum()) if not dff.empty and dff['date'].notna().any() else 0
    route_count = len(route_summary)
    stop_count = len(stop_summary)

    return [
        ('Total passengers', f'{total:,}'),
        ('Routes in view', f'{route_count:,}'),
        ('Stops in view', f'{stop_count:,}'),
        ('Top route', dominant_route),
        ('Top stop', dominant_stop),
        ('Avg daily', f'{avg_daily:,}'),
    ]


df, route_order = load_data()
if not route_order.empty:
    all_routes = sorted(route_order['route_id'].astype(str).str.strip().dropna().unique())
    all_directions = sorted(route_order['direction'].astype(str).str.strip().dropna().unique())
    stop_options = route_order[['stop_id', 'stop_name']].drop_duplicates().sort_values('stop_name')
else:
    all_routes = sorted(df.loc[df['route_id'].astype(str).str.strip() != '', 'route_id'].dropna().unique())
    all_directions = sorted(df.loc[df['direction'].astype(str).str.strip() != '', 'direction'].dropna().unique())
    stop_options = df.loc[df['stop_id'].astype(str).str.strip() != '', ['stop_id', 'stop_name']].drop_duplicates().sort_values('stop_name')
min_date = df['date'].min()
max_date = df['date'].max()

app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
app.config.suppress_callback_exceptions = True

app.layout = dbc.Container(fluid=True, style={'maxWidth': '1500px', 'padding': '24px 20px', 'backgroundColor': '#f5f7fb'}, children=[
    dbc.Row([
        dbc.Col([
            html.H1('Southern Gold Coast Bus Explorer', className='mb-2'),
            html.P('A live, map-first view of corridor demand with clickable stops, route flows, and instant filters.', className='text-muted'),
        ], width=12),
    ], className='mb-4'),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Filters')),
                dbc.CardBody([
                    html.Div([
                        html.Label('Routes', className='fw-semibold'),
                        dcc.Dropdown(id='route-filter', options=[{'label': route, 'value': route} for route in all_routes], value=all_routes, multi=True, clearable=False),
                        html.Small('Only official corridor routes with route geometry are shown on the map.', className='text-muted d-block mt-1'),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Directions', className='fw-semibold'),
                        dcc.Checklist(id='direction-filter', options=[{'label': direction, 'value': direction} for direction in all_directions], value=all_directions, inline=False),
                    ], className='mb-3'),
                    html.Div([
                        html.Div([
                            html.Label('Select stop', className='fw-semibold'),
                            html.Span('Official IDs only', className='badge bg-info text-dark ms-2', style={'fontSize': '0.75rem'}),
                        ], className='d-flex align-items-center'),
                        dcc.Dropdown(
                            id='stop-filter',
                            options=[
                                {'label': name, 'value': sid}
                                for sid, name in sorted(
                                    stop_options.values,
                                    key=lambda x: x[1]
                                )
                            ],
                            placeholder='Choose a stop to inspect',
                            clearable=True,
                        ),
                        html.Small('Stop selection is tied to the official route network map.', className='text-muted'),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Date range', className='fw-semibold'),
                        dcc.DatePickerRange(id='date-range', start_date=min_date, end_date=max_date, min_date_allowed=min_date, max_date_allowed=max_date, display_format='DD/MM/YYYY', day_size=39),
                    ], className='mb-3'),
                ]),
            ], className='shadow-sm mb-4'),
        ], width=3),
        dbc.Col([
            dbc.Row([
                dbc.Col(make_kpi(title, value, id=f'kpi-{index}'), width=4) for index, (title, value) in enumerate(build_summary_cards(df))
            ], className='g-3'),
        ], width=9),
    ], className='g-4 mb-4'),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Official Route Network Reference')),
                dbc.CardBody([
                    html.P(
                        'Use the provided Gold Coast route network map as the authoritative source for stop and corridor geometry. The stop dropdown is tied to the route data so selected demand metrics align with this official map.',
                        className='text-muted mb-3'
                    ),
                    html.Iframe(
                        src='/assets/260518-gold-coast-network-map.pdf',
                        style={'width': '100%', 'height': '480px', 'border': '1px solid #dee2e6'},
                    ),
                    html.Div(
                        html.A('Open the full route map in a new tab', href='/assets/260518-gold-coast-network-map.pdf', target='_blank', style={'fontWeight': '600'}),
                        className='mt-3',
                    ),
                    html.Hr(),
                    html.H6('Interactive corridor map overlay', className='mt-3 mb-2'),
                    dcc.Graph(id='corridor-map', figure=empty_figure('Loading corridor map'), config={'displayModeBar': False}, style={'height': '500px'}),
                ]),
            ], className='shadow-sm mb-4'),
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Selection Detail')),
                dbc.CardBody(id='selection-detail', style={'minHeight': '220px', 'backgroundColor': '#f8fafc'}),
            ], className='shadow-sm mb-4'),
            dbc.Card([
                dbc.CardHeader(html.H5('Top Stops')),
                dbc.CardBody([
                    dash_table.DataTable(
                        id='stop-table',
                        columns=[
                            {'name': 'Stop', 'id': 'stop_name'},
                            {'name': 'Passengers', 'id': 'passengers', 'type': 'numeric'},
                            {'name': 'Boardings', 'id': 'boardings', 'type': 'numeric'},
                            {'name': 'Alightings', 'id': 'alightings', 'type': 'numeric'},
                        ],
                        page_size=8,
                        sort_action='native',
                        style_table={'overflowX': 'auto'},
                        style_cell={'textAlign': 'left', 'padding': '10px', 'whiteSpace': 'normal', 'height': 'auto'},
                        style_cell_conditional=[
                            {'if': {'column_id': 'stop_name'}, 'width': '45%'},
                            {'if': {'column_id': 'passengers'}, 'width': '18%'},
                            {'if': {'column_id': 'boardings'}, 'width': '18%'},
                            {'if': {'column_id': 'alightings'}, 'width': '18%'},
                        ],
                        style_header={'backgroundColor': '#eef2ff', 'fontWeight': 'bold', 'borderBottom': '2px solid #c7d2fe'},
                        style_data_conditional=[
                            {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8fafc'},
                        ],
                    ),
                ]),
            ], className='shadow-sm'),
        ], width=4),
    ], className='g-4'),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Demand by Route')),
                dbc.CardBody(dcc.Graph(id='route-trend', figure=empty_figure('Loading route trend'), config={'displayModeBar': False})),
            ], className='shadow-sm mt-4'),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Boardings vs Alightings')),
                dbc.CardBody(dcc.Graph(id='boarding-chart', figure=empty_figure('Loading boarding chart'), config={'displayModeBar': False})),
            ], className='shadow-sm mt-4'),
        ], width=6),
    ], className='g-4'),
])


@app.callback(
    [Output('kpi-0', 'children'), Output('kpi-1', 'children'), Output('kpi-2', 'children'), Output('kpi-3', 'children'), Output('kpi-4', 'children'), Output('kpi-5', 'children')],
    [Output('selection-detail', 'children'), Output('stop-table', 'data'), Output('route-trend', 'figure'), Output('boarding-chart', 'figure'), Output('corridor-map', 'figure')],
    Input('route-filter', 'value'),
    Input('direction-filter', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
    Input('stop-filter', 'value'),
)
def update_dashboard(selected_routes, selected_dirs, start_date, end_date, selected_stop_id):
    routes = selected_routes if isinstance(selected_routes, list) else [selected_routes]
    dirs = selected_dirs if isinstance(selected_dirs, list) else [selected_dirs]
    dff = df.copy()
    if routes:
        dff = dff[dff['route_id'].isin(routes)]
    if dirs:
        dff = dff[dff['direction'].isin(dirs)]
    if start_date:
        dff = dff[dff['date'] >= pd.to_datetime(start_date)]
    if end_date:
        dff = dff[dff['date'] <= pd.to_datetime(end_date)]

    if dff.empty:
        empty = empty_figure('No data available')
        return (
            '0',
            'N/A',
            'N/A',
            '0',
            '0',
            '0',
            dbc.Card([
                dbc.CardHeader('No selection available'),
                dbc.CardBody([html.P('No matching data for the selected filters.', className='text-muted mb-0')]),
            ], className='shadow-sm'),
            [],
            empty,
            empty,
            empty,
        )

    stop_lookup = build_stop_location_lookup(sorted(set(route_order['stop_name'].astype(str).dropna())), allow_fallback=False)
    stop_name_by_stop_id = dff.groupby('stop_id', as_index=False)['stop_name'].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]).set_index('stop_id')['stop_name'].to_dict()
    map_df, route_lines = build_map_data(dff, route_order, stop_lookup, stop_name_by_stop_id)

    if selected_stop_id and selected_stop_id not in map_df['stop_id'].values:
        selected_stop_id = None

    if map_df.empty:
        map_figure = empty_figure('No corridor data for selected filters')
    else:
        map_figure = build_map_figure(map_df, route_lines=route_lines, selected_stop_id=selected_stop_id)

    if selected_stop_id:
        stop_data = dff[dff['stop_id'] == selected_stop_id]
        stop_name = stop_data['stop_name'].mode().iloc[0] if not stop_data.empty else selected_stop_id
        stop_total = int(stop_data['passengers'].sum())
        stop_boardings = int(stop_data['boardings'].sum())
        stop_alightings = int(stop_data['alightings'].sum())
        top_routes = stop_data.groupby('route_id', as_index=False).agg({'passengers': 'sum'}).sort_values('passengers', ascending=False).head(5)
        route_list = [html.Li(f"{row['route_id']} — {int(row['passengers']):,} passengers") for _, row in top_routes.iterrows()]
        detail = dbc.Card([
            dbc.CardHeader(f'{stop_name} ({selected_stop_id})'),
            dbc.CardBody([
                html.Div(f'Total passengers: {stop_total:,}', className='mb-2'),
                html.Div(f'Boardings: {stop_boardings:,}', className='mb-2'),
                html.Div(f'Alightings: {stop_alightings:,}', className='mb-3'),
                html.H6('Top routes', className='mb-2'),
                html.Ul(route_list, className='small mb-0'),
            ]),
        ], className='shadow-sm')
    else:
        detail = dbc.Card([
            dbc.CardHeader('How to use the reference map'),
            dbc.CardBody([
                html.P('Open the Gold Coast network map on the left and select a stop from the dropdown to inspect demand.', className='text-muted mb-2'),
                html.P('Filtered routes and directions update the stop-level passenger counts below.', className='text-muted mb-0'),
            ]),
        ], className='shadow-sm')

    stop_table = dff.groupby(['stop_name'], as_index=False).agg({'passengers': 'sum', 'boardings': 'sum', 'alightings': 'sum'}).sort_values('passengers', ascending=False).head(12).to_dict('records')

    route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
    route_summary = route_summary.sort_values('passengers', ascending=False).head(10)
    trend_fig = px.bar(route_summary, x='route_id', y='passengers', title='Route demand', template='plotly_white', labels={'route_id': 'Route', 'passengers': 'Passengers'})
    trend_fig.update_layout(margin={'t': 45})

    boardings = dff.groupby('stop_name', as_index=False).agg({'boardings': 'sum', 'alightings': 'sum'})
    boardings = boardings.sort_values('boardings', ascending=False).head(12)
    boarding_fig = px.bar(boardings, x='stop_name', y=['boardings', 'alightings'], barmode='group', title='Boardings vs alightings', template='plotly_white')
    boarding_fig.update_layout(xaxis_tickangle=-35, margin={'t': 45})

    summary_cards = build_summary_cards(dff)
    summary_values = [html.Div(value, className='h3 mb-0') for _, value in summary_cards]

    return (
        summary_values[0],
        summary_values[1],
        summary_values[2],
        summary_values[3],
        summary_values[4],
        summary_values[5],
        detail,
        stop_table,
        trend_fig,
        boarding_fig,
        map_figure,
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run_server(debug=debug, host='127.0.0.1', port=port, use_reloader=False)
