import re
import pandas as pd
from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import glob
import os


def load_data():
    repo_root = os.path.dirname(__file__)
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
        'Latitude': 'latitude',
        'Longitude': 'longitude',
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

        if 'route_id' in frame.columns:
            frame['route_id'] = frame['route_id'].astype(str).str.strip()
        if 'stop_id' in frame.columns:
            frame['stop_id'] = frame['stop_id'].astype(str).str.strip()
        if 'stop_name' in frame.columns:
            frame['stop_name'] = frame['stop_name'].astype(str).fillna('Unknown')
        if 'direction' in frame.columns:
            frame['direction'] = frame['direction'].astype(str).replace(direction_map).str.strip()

        for col in ['boardings', 'alightings', 'latitude', 'longitude', 'passengers']:
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
    if 'route_id' not in df.columns:
        df['route_id'] = ''
    if 'stop_id' not in df.columns:
        df['stop_id'] = ''
    if 'stop_name' not in df.columns:
        df['stop_name'] = 'Unknown'
    if 'direction' not in df.columns:
        df['direction'] = 'Unknown'
    if 'passengers' not in df.columns:
        df['passengers'] = 0

    df['route_id'] = df['route_id'].astype(str).str.strip().replace({'nan': ''})
    df['stop_id'] = df['stop_id'].astype(str).str.strip().replace({'nan': ''})
    df['stop_name'] = df['stop_name'].astype(str).str.strip().replace({'nan': 'Unknown'})
    df['direction'] = df['direction'].astype(str).replace(direction_map).str.strip().replace({'nan': 'Unknown'})

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


def make_kpi(title, value='', id=None):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, className='text-muted text-uppercase mb-2', style={'fontSize': '0.75rem', 'letterSpacing': '0.1em'}),
            html.H3(value, className='mb-0', style={'fontWeight': '700'}),
        ], className='py-3'),
        className='h-100 shadow-sm border-0 bg-white',
        id=id,
    )


def build_overview_insights(dff, route_summary, stop_summary):
    top_route = route_summary.iloc[0] if not route_summary.empty else None
    top_stop = stop_summary.iloc[0] if not stop_summary.empty else None
    direction_summary = dff.groupby('direction', as_index=False).agg({'passengers': 'sum'}).sort_values('passengers', ascending=False)
    top_direction = direction_summary.iloc[0] if not direction_summary.empty else None

    return dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Div('Busiest Route', className='text-muted text-uppercase small mb-2'),
                html.H4(f"{top_route['route_id']}" if top_route is not None else 'N/A', className='mb-1'),
                html.Div(f"{int(top_route['passengers']):,} passengers", className='text-muted small'),
            ])
        ], className='h-100 shadow-sm border-0 bg-white'), width=4),
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Div('Most Active Stop', className='text-muted text-uppercase small mb-2'),
                html.H4(f"{top_stop['stop_name']}" if top_stop is not None else 'N/A', className='mb-1'),
                html.Div(f"{int(top_stop['passengers']):,} passengers", className='text-muted small'),
            ])
        ], className='h-100 shadow-sm border-0 bg-white'), width=4),
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Div('Dominant Direction', className='text-muted text-uppercase small mb-2'),
                html.H4(f"{top_direction['direction']}" if top_direction is not None else 'N/A', className='mb-1'),
                html.Div(f"{int(top_direction['passengers']):,} passengers", className='text-muted small'),
            ])
        ], className='h-100 shadow-sm border-0 bg-white'), width=4),
    ], className='g-3 mb-4')


def build_tab_content(tab_id, dff, route_order, has_geo):
    if tab_id == 'tab-routes':
        route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
        route_summary['avg_daily'] = route_summary['passengers'] / safe_days(dff)
        route_summary = route_summary.sort_values('passengers', ascending=False)
        direction_breakdown = dff.groupby(['route_id', 'direction'], as_index=False).agg({'passengers': 'sum'})

        route_lines = []
        route_stop_overview = None
        if not route_order.empty:
            selected = route_order[route_order['route_id'].isin(route_summary['route_id'])]
            if not selected.empty:
                summary = selected.sort_values(['route_id', 'direction', 'stop_sequence']).groupby(['route_id', 'direction']).agg(
                    stops_count=('stop_name', 'size'),
                    start_stop=('stop_name', 'first'),
                    end_stop=('stop_name', 'last'),
                ).reset_index()
                route_lines = [
                    html.Div([
                        html.H6(f"Route {row['route_id']} — {row['direction']}", className='mb-1'),
                        html.Div(f"{row['stops_count']} stops • from {row['start_stop']} to {row['end_stop']}", className='small text-muted'),
                    ], className='mb-3')
                    for _, row in summary.head(8).iterrows()
                ]

                route_stop_overview = dbc.Table.from_dataframe(
                    summary.rename(columns={
                        'route_id': 'Route',
                        'direction': 'Direction',
                        'stops_count': 'Number of Stops',
                        'start_stop': 'First Stop',
                        'end_stop': 'Last Stop',
                    }),
                    striped=True,
                    bordered=True,
                    hover=True,
                    responsive=True,
                    className='mt-3',
                )

        route_chart = px.bar(
            route_summary.head(12),
            x='route_id',
            y='passengers',
            title='Top Routes by Total Passengers',
            template='plotly_white',
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        avg_chart = px.bar(
            route_summary.head(12),
            x='route_id',
            y='avg_daily',
            title='Top Routes by Average Daily Passengers',
            template='plotly_white',
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        direction_chart = px.bar(
            direction_breakdown,
            x='route_id',
            y='passengers',
            color='direction',
            barmode='group',
            title='Direction Breakdown by Route',
            template='plotly_white',
            color_discrete_sequence=px.colors.qualitative.Set2,
        )

        summary_block = [html.H4('Route Stop Summaries', className='mt-4')]
        if route_lines:
            summary_block += route_lines
        else:
            summary_block.append(html.Div('Stop order details are not available for the selected filters.', className='text-muted'))

        return html.Div([
            dbc.Row([
                dbc.Col(dcc.Graph(figure=route_chart, config={'displayModeBar': False}), width=6),
                dbc.Col(dcc.Graph(figure=avg_chart, config={'displayModeBar': False}), width=6),
            ], className='g-4 mb-4'),
            dbc.Row(dbc.Col(dcc.Graph(figure=direction_chart, config={'displayModeBar': False}))),
            dbc.Row(dbc.Col(dbc.Card([
                dbc.CardBody(summary_block)
            ]), className='shadow-sm mt-4')),
            dbc.Row(dbc.Col(route_stop_overview, width=12), className='mt-3') if route_stop_overview is not None else None,
        ])

    if tab_id == 'tab-trend':
        if dff.empty or dff['date'].isna().all():
            return html.Div(dcc.Graph(figure=empty_figure('No trend data available')))

        trend = dff.groupby(dff['date'].dt.date, as_index=False).agg({'passengers': 'sum'})
        trend = trend.sort_values('date')
        trend_fig = px.line(trend, x='date', y='passengers', markers=True, title='Daily Passenger Trend')
        trend_fig.update_layout(xaxis_title='Date', yaxis_title='Passengers')

        dff = dff.copy()
        dff['weekday'] = dff['date'].dt.day_name()
        dff['hour'] = dff['date'].dt.hour.fillna(0).astype(int)
        heat = dff.groupby(['weekday', 'hour'], as_index=False).agg({'passengers': 'sum'})
        heat['weekday'] = pd.Categorical(heat['weekday'], categories=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], ordered=True)
        heat = heat.pivot(index='weekday', columns='hour', values='passengers').fillna(0)
        heat_fig = px.imshow(heat, aspect='auto', labels={'x': 'Hour', 'y': 'Weekday', 'color': 'Passengers'}, title='Passenger Heatmap by Weekday/Hour')

        return html.Div([
            dbc.Row(dbc.Col(dcc.Graph(figure=trend_fig))),
            dbc.Row(dbc.Col(dcc.Graph(figure=heat_fig))),
        ])

    if tab_id == 'tab-stops':
        top_stops = dff.groupby(['stop_id', 'stop_name'], as_index=False).agg({'passengers': 'sum', 'boardings': 'sum', 'alightings': 'sum'})
        top_stops = top_stops.sort_values('passengers', ascending=False).head(20)
        top_stops_fig = px.bar(
            top_stops,
            x='passengers',
            y='stop_name',
            orientation='h',
            title='Top Stops by Passengers',
            template='plotly_white',
            color_discrete_sequence=['#2a9d8f'],
        )
        top_stops_fig.update_layout(yaxis={'categoryorder': 'total ascending'}, margin={'t': 50})

        ba = dff.groupby('stop_name', as_index=False).agg({'boardings': 'sum', 'alightings': 'sum'})
        ba = ba.melt(id_vars='stop_name', value_vars=['boardings', 'alightings'], var_name='type', value_name='count')
        ba_fig = px.bar(
            ba,
            x='stop_name',
            y='count',
            color='type',
            title='Boardings vs Alightings by Stop',
            template='plotly_white',
            color_discrete_map={'boardings': '#264653', 'alightings': '#e76f51'},
        )
        ba_fig.update_layout(xaxis_tickangle=-45, margin={'t': 50})

        route_map = pd.DataFrame()
        if not route_order.empty:
            route_map = route_order.merge(
                dff[['route_id', 'direction', 'stop_id', 'stop_name']].drop_duplicates(),
                on=['route_id', 'direction', 'stop_id', 'stop_name'],
                how='inner'
            )

        overview_text = html.Div([
            html.H5('Stop and boardings analysis', className='mb-3'),
            html.P('This tab highlights the busiest boarding and alighting locations along the corridor. If geographic coordinates are present, stop points appear on a map for spatial context.', className='text-muted'),
        ], className='mb-4')

        content = [
            dbc.Row(dbc.Col(overview_text)),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=top_stops_fig, config={'displayModeBar': False}), width=6),
                dbc.Col(dcc.Graph(figure=ba_fig, config={'displayModeBar': False}), width=6),
            ], className='g-4 mb-4'),
        ]

        if has_geo:
            geo_stops = dff.dropna(subset=['latitude', 'longitude']).groupby(['stop_id', 'stop_name', 'latitude', 'longitude'], as_index=False).agg({'passengers': 'sum'})
            if not geo_stops.empty:
                map_fig = px.scatter_mapbox(
                    geo_stops,
                    lat='latitude',
                    lon='longitude',
                    size='passengers',
                    hover_name='stop_name',
                    hover_data={'stop_id': True, 'passengers': True},
                    custom_data=['stop_id', 'stop_name'],
                    zoom=11,
                    height=520,
                    template='plotly_white',
                )
                map_fig.update_layout(mapbox_style='open-street-map', margin={'r': 0, 't': 30, 'l': 0, 'b': 0}, legend={'orientation': 'h', 'y': -0.1})
                content.append(dbc.Row(dbc.Col(dcc.Graph(id='map-stops', figure=map_fig), width=12)))
            else:
                content.append(dbc.Row(dbc.Col(dbc.Alert('No coordinate data available for the selected filters.', color='warning'))))
        else:
            content.append(dbc.Row(dbc.Col(dbc.Alert(
                'No geographic coordinates are available in the loaded dataset. Add latitude/longitude for stops to see them on the map.',
                color='warning',
            ))))

        return html.Div(content)

    if tab_id == 'tab-map':
        map_url = app.get_asset_url('260518-gold-coast-network-map.pdf')
        route_totals = dff.groupby(['route_id', 'direction'], as_index=False).agg({'passengers': 'sum'}).sort_values('passengers', ascending=False).head(8)
        route_note = []
        if not route_order.empty:
            selected_order = route_order[route_order['route_id'].isin(route_totals['route_id'])]
            summary = selected_order.sort_values(['route_id', 'direction', 'stop_sequence']).groupby(['route_id', 'direction'], as_index=False).agg(
                stops_count=('stop_name', 'size'),
                first_stop=('stop_name', 'first'),
                last_stop=('stop_name', 'last'),
            )
            summary = summary.merge(route_totals[['route_id', 'direction']], on=['route_id', 'direction'], how='right')
            route_note = [
                html.Div([
                    html.H6(f"Route {row['route_id']} — {row['direction']}", className='mb-1'),
                    html.Div(f"{int(row['stops_count'])} stops from {row['first_stop']} to {row['last_stop']}", className='small text-muted'),
                ], className='mb-3')
                for _, row in summary.iterrows()
            ]
        else:
            route_note = [html.Div('Route stop order details are not available for this dataset.', className='text-muted')]

        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.H3('Gold Coast Network Map'),
                    html.P('The official network map is embedded here to help connect route analysis to the southern Gold Coast corridor.', className='text-muted'),
                    html.Iframe(src=map_url, style={'width': '100%', 'height': '760px', 'border': '1px solid #dfe3e8'}),
                ], width=8),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader('Selected Route Summary'),
                        dbc.CardBody([
                            html.P('Top selected routes with stop span details from the route order file.', className='small text-muted'),
                            *route_note,
                        ]),
                    ], className='shadow-sm'),
                ], width=4),
            ], className='g-4'),
        ])

    route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
    route_summary['avg_daily'] = route_summary['passengers'] / safe_days(dff)
    route_summary = route_summary.sort_values('passengers', ascending=False)

    stop_summary = dff.groupby(['stop_id', 'stop_name'], as_index=False).agg({'passengers': 'sum'})
    stop_summary = stop_summary.sort_values('passengers', ascending=False).head(12)

    overview_figs = [
        px.bar(route_summary.head(10), x='route_id', y='passengers', title='Top 10 Routes by Passengers', template='plotly_white'),
        px.bar(stop_summary, x='passengers', y='stop_name', orientation='h', title='Top Stops by Passengers', template='plotly_white'),
    ]
    overview_figs[1].update_layout(yaxis={'categoryorder': 'total ascending'}, margin={'t': 50})

    ba = dff.groupby('stop_name', as_index=False).agg({'boardings': 'sum', 'alightings': 'sum'})
    ba = ba.melt(id_vars='stop_name', value_vars=['boardings', 'alightings'], var_name='type', value_name='count')
    ba_fig = px.bar(ba, x='stop_name', y='count', color='type', title='Boardings vs Alightings', template='plotly_white')
    ba_fig.update_layout(xaxis_tickangle=-45, margin={'t': 50})

    highlight = []
    if not route_summary.empty and not stop_summary.empty:
        highlight.append(html.P(
            f"{route_summary.iloc[0]['route_id']} is the busiest route, delivering {int(route_summary.iloc[0]['passengers']):,} passengers. "
            f"{stop_summary.iloc[0]['stop_name']} is the corridor's busiest stop with {int(stop_summary.iloc[0]['passengers']):,} passengers.",
            className='text-muted'
        ))
    if not dff.empty and dff['date'].notna().any():
        avg_daily = int(dff['passengers'].sum() / safe_days(dff))
        highlight.append(html.P(f"Average daily ridership is approximately {avg_daily:,}.", className='text-muted'))

    return html.Div([
        build_overview_insights(dff, route_summary, stop_summary),
        dbc.Row(dbc.Col(dbc.Card([
            dbc.CardBody([html.H5('Corridor Insights', className='mb-3'), *highlight])
        ]), className='mb-4')),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=overview_figs[0], config={'displayModeBar': False}), width=6),
            dbc.Col(dcc.Graph(figure=overview_figs[1], config={'displayModeBar': False}), width=6),
        ], className='g-4 mb-4'),
        dbc.Row(dbc.Col(dcc.Graph(figure=ba_fig, config={'displayModeBar': False}))),
    ])


df, route_order = load_data()
all_routes = sorted(df.loc[df['route_id'].astype(str).str.strip() != '', 'route_id'].dropna().unique())
if not all_routes:
    all_routes = sorted(df['route_id'].dropna().unique())
all_directions = sorted(df.loc[df['direction'].astype(str).str.strip() != '', 'direction'].dropna().unique())
if not all_directions:
    all_directions = sorted(df['direction'].dropna().unique())
min_date = df['date'].min()
max_date = df['date'].max()
has_geo = 'latitude' in df.columns and 'longitude' in df.columns and df[['latitude', 'longitude']].notna().any().any()

app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
app.config.suppress_callback_exceptions = True

app.layout = dbc.Container(fluid=True, style={'maxWidth': '1400px', 'padding': '22px 18px', 'backgroundColor': '#eef4fb'}, children=[
    dbc.Row([
        dbc.Col([
            html.H1('Southern Gold Coast Bus Dashboard', className='mb-2'),
            html.P('Explore corridor performance, route drill-downs, and stop-level detail with cleaner interaction and clearer insights.', className='text-muted'),
        ], width=12),
    ], className='mb-4'),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Controls')),
                dbc.CardBody([
                    html.Div([
                        html.Label('Routes', className='fw-semibold'),
                        dcc.Dropdown(
                            id='route-filter',
                            options=[{'label': r, 'value': r} for r in all_routes],
                            value=all_routes,
                            multi=True,
                            placeholder='Select route(s)',
                            clearable=False,
                        ),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Directions', className='fw-semibold'),
                        dcc.Checklist(
                            id='direction-filter',
                            options=[{'label': d, 'value': d} for d in all_directions],
                            value=all_directions,
                            inputStyle={'marginRight': '8px', 'marginLeft': '12px'},
                        ),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Date Range', className='fw-semibold'),
                        dcc.DatePickerRange(
                            id='date-range',
                            start_date=min_date,
                            end_date=max_date,
                            min_date_allowed=min_date,
                            max_date_allowed=max_date,
                            display_format='DD/MM/YYYY',
                            day_size=39,
                            style={'width': '100%'},
                        ),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Sort metrics', className='fw-semibold'),
                        dcc.RadioItems(
                            id='sort-by',
                            options=[
                                {'label': 'Total passengers', 'value': 'passengers'},
                                {'label': 'Average daily', 'value': 'avg_daily'},
                            ],
                            value='passengers',
                            inline=False,
                            labelStyle={'display': 'block', 'marginBottom': '8px'},
                        ),
                    ]),
                ]),
            ], className='shadow-sm mb-4'),
        ], width=4),
        dbc.Col([
            dbc.Row([
                dbc.Col(make_kpi('Total Passengers', id='kpi-total'), width=4),
                dbc.Col(make_kpi('Busiest Route', id='kpi-busiest-route'), width=4),
                dbc.Col(make_kpi('Top Stop', id='kpi-busiest-stop'), width=4),
            ], className='g-3 mb-3'),
            dbc.Row([
                dbc.Col(make_kpi('Avg Daily Load', id='kpi-avg-daily'), width=4),
                dbc.Col(make_kpi('Weekday Volume', id='kpi-weekday'), width=4),
                dbc.Col(make_kpi('Weekend Volume', id='kpi-weekend'), width=4),
            ], className='g-3'),
        ], width=8),
    ], className='g-4 mb-4'),
    dbc.Tabs([
        dbc.Tab(label='Overview', tab_id='overview', children=[
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Route Load by Corridor')),
                    dbc.CardBody(dcc.Graph(id='top-route-chart', figure=empty_figure('Loading route load'), config={'displayModeBar': False})),
                ], className='shadow-sm mb-4'), width=12),
            ]),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Direction Load')),
                    dbc.CardBody(dcc.Graph(id='direction-chart', figure=empty_figure('Loading direction load'), config={'displayModeBar': False})),
                ], className='shadow-sm mb-4'), width=6),
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Stop Performance')),
                    dbc.CardBody(dcc.Graph(id='top-stop-chart', figure=empty_figure('Loading stop performance'), config={'displayModeBar': False})),
                ], className='shadow-sm mb-4'), width=6),
            ], className='g-4'),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Daily Passenger Trend')),
                    dbc.CardBody(dcc.Graph(id='trend-chart', figure=empty_figure('Loading daily trend'), config={'displayModeBar': False})),
                ], className='shadow-sm mb-4'), width=6),
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Boardings vs Alightings')),
                    dbc.CardBody(dcc.Graph(id='stop-summary-chart', figure=empty_figure('Loading boardings vs alightings'), config={'displayModeBar': False})),
                ], className='shadow-sm mb-4'), width=6),
            ], className='g-4'),
        ]),
        dbc.Tab(label='Route & Stop Detail', tab_id='detail', children=[
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Top Stops')),
                    dbc.CardBody([
                        dash_table.DataTable(
                            id='stop-table',
                            columns=[
                                {'name': 'Stop Name', 'id': 'stop_name'},
                                {'name': 'Passengers', 'id': 'passengers', 'type': 'numeric'},
                                {'name': 'Boardings', 'id': 'boardings', 'type': 'numeric'},
                                {'name': 'Alightings', 'id': 'alightings', 'type': 'numeric'},
                                {'name': 'Routes', 'id': 'routes', 'type': 'numeric'},
                            ],
                            page_size=10,
                            sort_action='native',
                            style_table={'overflowX': 'auto'},
                            style_cell={'textAlign': 'left', 'padding': '8px', 'whiteSpace': 'normal', 'height': 'auto'},
                            style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                            style_data_conditional=[
                                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'},
                            ],
                        )
                    ]),
                ], className='shadow-sm mb-4'), width=12),
            ]),
            dbc.Row([
                dbc.Col(html.Div(id='selected-route-card'), width=6),
                dbc.Col(html.Div(id='stop-info-card'), width=6),
            ], className='g-4 mb-4'),
        ]),
        dbc.Tab(label='Reference Map', tab_id='reference', children=[
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5('Gold Coast Network Map')),
                    dbc.CardBody([
                        html.Iframe(src=app.get_asset_url('260518-gold-coast-network-map.pdf'), style={'width': '100%', 'height': '760px', 'border': '1px solid #dfe3e8'}),
                        html.P('The published network map delivers context for the southern Gold Coast enhancement corridor and supports route interpretation.', className='text-muted small mt-3'),
                    ]),
                ], className='shadow-sm mb-4'), width=12),
            ]),
        ]),
    ], id='main-tabs', active_tab='overview', className='shadow-sm'),
])


@app.callback(
    Output('kpi-total', 'children'),
    Output('kpi-busiest-route', 'children'),
    Output('kpi-busiest-stop', 'children'),
    Output('kpi-avg-daily', 'children'),
    Output('kpi-weekday', 'children'),
    Output('kpi-weekend', 'children'),
    Output('top-route-chart', 'figure'),
    Output('direction-chart', 'figure'),
    Output('top-stop-chart', 'figure'),
    Output('trend-chart', 'figure'),
    Output('stop-summary-chart', 'figure'),
    Output('stop-table', 'data'),
    Input('route-filter', 'value'),
    Input('direction-filter', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
    Input('sort-by', 'value'),
)
def update_dashboard(selected_routes, selected_dirs, start_date, end_date, sort_by):
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
        return ('0', 'N/A', 'N/A', '0', '0', '0', empty, empty, empty, empty, empty, [])

    days = safe_days(dff)
    route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
    route_summary['avg_daily'] = route_summary['passengers'] / days
    route_summary = route_summary.sort_values(sort_by, ascending=False)

    stop_summary = dff.groupby(['stop_id', 'stop_name'], as_index=False).agg({'passengers': 'sum', 'boardings': 'sum', 'alightings': 'sum'})
    stop_summary['routes'] = dff.groupby('stop_id')['route_id'].nunique().reindex(stop_summary['stop_id']).fillna(0).astype(int).values
    stop_summary = stop_summary.sort_values('passengers', ascending=False)

    total_passengers = int(dff['passengers'].sum())
    busiest_route = route_summary.iloc[0]
    busiest_stop = stop_summary.iloc[0]
    avg_daily = round(total_passengers / days, 1)
    weekday_mask = dff['date'].dt.dayofweek < 5
    weekday_passengers = int(dff.loc[weekday_mask, 'passengers'].sum())
    weekend_passengers = int(dff.loc[~weekday_mask, 'passengers'].sum())

    route_chart = px.bar(
        route_summary.head(12),
        x='route_id',
        y='passengers',
        title='Top Routes by Total Passengers',
        template='plotly_white',
        labels={'route_id': 'Route', 'passengers': 'Passengers'},
    )
    route_chart.update_layout(clickmode='event+select', margin={'t': 45})

    direction_breakdown = dff.groupby(['direction', 'route_id'], as_index=False).agg(passengers=('passengers', 'sum'))
    direction_chart = go.Figure()
    for route in sorted(direction_breakdown['route_id'].dropna().unique()):
        route_data = direction_breakdown[direction_breakdown['route_id'] == route]
        direction_chart.add_trace(go.Bar(
            x=route_data['direction'],
            y=route_data['passengers'],
            name=str(route),
            hovertemplate='%{x}<br>%{y:,} passengers<br>Route: %{name}<extra></extra>',
        ))
    direction_chart.update_layout(
        barmode='stack',
        title='Load by Direction and Route',
        template='plotly_white',
        xaxis_title='Direction',
        yaxis_title='Passengers',
        legend_title='Route',
        margin={'t': 45},
    )

    top_stop_chart = px.bar(
        stop_summary.head(20),
        x='passengers',
        y='stop_name',
        orientation='h',
        title='Top Stops by Passengers',
        template='plotly_white',
        labels={'passengers': 'Passengers', 'stop_name': 'Stop'},
    )
    top_stop_chart.update_layout(yaxis={'categoryorder': 'total ascending'}, margin={'t': 45})

    trend = dff.assign(date=dff['date'].dt.date).groupby('date', as_index=False).agg(passengers=('passengers', 'sum'))
    trend_fig = px.line(trend, x='date', y='passengers', markers=True, title='Daily Passenger Trend', template='plotly_white')
    trend_fig.update_layout(xaxis_title='Date', yaxis_title='Passengers', margin={'t': 45})

    ba = dff.groupby('stop_name', as_index=False).agg({'boardings': 'sum', 'alightings': 'sum'})
    ba = ba.melt(id_vars='stop_name', value_vars=['boardings', 'alightings'], var_name='type', value_name='count')
    ba = ba.sort_values(['stop_name', 'type']).groupby(['stop_name', 'type'], as_index=False).agg({'count': 'sum'})
    ba = ba.sort_values('count', ascending=False).head(20)
    stop_summary_fig = go.Figure()
    for traffic_type in ba['type'].unique():
        series = ba[ba['type'] == traffic_type]
        stop_summary_fig.add_trace(go.Bar(
            x=series['stop_name'],
            y=series['count'],
            name=traffic_type,
            hovertemplate='%{x}<br>%{y:,} %{name}<extra></extra>',
        ))
    stop_summary_fig.update_layout(
        title='Boardings vs Alightings',
        template='plotly_white',
        xaxis_title='Stop',
        yaxis_title='Count',
        xaxis_tickangle=-45,
        barmode='group',
        margin={'t': 45},
    )

    table_data = stop_summary[['stop_name', 'passengers', 'boardings', 'alightings', 'routes']].head(15).to_dict('records')

    return (
        html.Div(f'{total_passengers:,}', className='h3 mb-0'),
        html.Div(f"{busiest_route['route_id']} ({int(busiest_route['passengers']):,})", className='h3 mb-0'),
        html.Div(f"{busiest_stop['stop_name']} ({int(busiest_stop['passengers']):,})", className='h3 mb-0'),
        html.Div(f'{avg_daily:,}', className='h3 mb-0'),
        html.Div(f'{weekday_passengers:,}', className='h3 mb-0'),
        html.Div(f'{weekend_passengers:,}', className='h3 mb-0'),
        route_chart,
        direction_chart,
        top_stop_chart,
        trend_fig,
        stop_summary_fig,
        table_data,
    )


@app.callback(
    Output('selected-route-card', 'children'),
    Input('top-route-chart', 'clickData'),
    Input('route-filter', 'value'),
    Input('direction-filter', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
)
def update_route_card(click_data, selected_routes, selected_dirs, start_date, end_date):
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

    if click_data is None:
        return dbc.Card([
            dbc.CardHeader('Route Drill-down'),
            dbc.CardBody('Click a route bar in the chart to explore route-level stop order, top stops and direction load.'),
        ], className='shadow-sm')

    route_id = click_data['points'][0]['x']
    route_data = dff[dff['route_id'] == route_id]
    if route_data.empty:
        return dbc.Card([
            dbc.CardHeader('Route Drill-down'),
            dbc.CardBody('Selected route has no data for the applied filters.'),
        ], className='shadow-sm')

    route_total = int(route_data['passengers'].sum())
    route_avg = round(route_total / safe_days(route_data), 1)
    route_dirs = ', '.join(sorted(route_data['direction'].unique()))
    route_stops = route_data['stop_name'].nunique()
    top_stops = route_data.groupby('stop_name', as_index=False).agg({'passengers': 'sum'}).sort_values('passengers', ascending=False).head(5)

    stop_list = [html.Li(f"{row['stop_name']} — {int(row['passengers']):,} passengers") for _, row in top_stops.iterrows()]
    order_text = 'Route order details unavailable.'
    if not route_order.empty:
        ordered = route_order[route_order['route_id'] == route_id].sort_values('stop_sequence')
        if not ordered.empty:
            order_text = f"First stop: {ordered.iloc[0]['stop_name']}, last stop: {ordered.iloc[-1]['stop_name']}, total stops: {len(ordered)}."

    return dbc.Card([
        dbc.CardHeader(f'Route {route_id} Details'),
        dbc.CardBody([
            html.Div(f'Passengers: {route_total:,}', className='mb-2'),
            html.Div(f'Avg daily: {route_avg:,}', className='mb-2'),
            html.Div(f'Directions: {route_dirs}', className='mb-2'),
            html.Div(order_text, className='text-muted mb-3'),
            html.H6('Top Stops', className='mb-2'),
            html.Ul(stop_list, className='small'),
        ]),
    ], className='shadow-sm')


@app.callback(
    Output('stop-info-card', 'children'),
    Input('top-stop-chart', 'clickData'),
    Input('route-filter', 'value'),
    Input('direction-filter', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
)
def update_stop_card(click_data, selected_routes, selected_dirs, start_date, end_date):
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

    if click_data is None:
        return dbc.Card([
            dbc.CardHeader('Stop Drill-down'),
            dbc.CardBody('Click a stop bar to reveal boardings, alightings, and route service detail for each stop.'),
        ], className='shadow-sm')

    stop_name = click_data['points'][0]['y']
    stop_data = dff[dff['stop_name'] == stop_name]
    if stop_data.empty:
        return dbc.Card([
            dbc.CardHeader('Stop Drill-down'),
            dbc.CardBody('Selected stop has no data for the applied filters.'),
        ], className='shadow-sm')

    total = int(stop_data['passengers'].sum())
    boardings = int(stop_data['boardings'].sum())
    alightings = int(stop_data['alightings'].sum())
    board_split = int(round(100 * boardings / max(total, 1)))
    top_routes = stop_data.groupby('route_id', as_index=False).agg({'passengers': 'sum'}).sort_values('passengers', ascending=False).head(5)

    route_list = [html.Li(f"{row['route_id']} — {int(row['passengers']):,} passengers") for _, row in top_routes.iterrows()]

    return dbc.Card([
        dbc.CardHeader(f'Stop {stop_name} Details'),
        dbc.CardBody([
            html.Div(f'Total passengers: {total:,}', className='mb-2'),
            html.Div(f'Boardings: {boardings:,} ({board_split}% of stop load)', className='mb-2'),
            html.Div(f'Alightings: {alightings:,}', className='mb-3'),
            html.H6('Top Serving Routes', className='mb-2'),
            html.Ul(route_list, className='small'),
        ]),
    ], className='shadow-sm')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('DEBUG', 'true').lower() in ('1', 'true', 'yes')
    app.run_server(debug=debug, host='127.0.0.1', port=port)
