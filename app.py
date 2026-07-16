import pandas as pd
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import dash_table
import plotly.express as px
import glob
import os


def load_data():
    repo_root = os.path.dirname(__file__)
    patterns = [os.path.join(repo_root, 'IR-1230*.csv'), os.path.join(repo_root, 'data', '*.csv')]
    files = sorted(set(sum((glob.glob(p) for p in patterns), [])))
    if not files:
        raise FileNotFoundError('No CSV files found in repository or data folder')

    frames = []
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

    for path in files:
        frame = pd.read_csv(path)
        if 'Date' in frame.columns:
            frame['date'] = pd.to_datetime(frame['Date'], errors='coerce', dayfirst=True)
        if 'date' in frame.columns:
            frame['date'] = pd.to_datetime(frame['date'], errors='coerce', dayfirst=True)
        frame = frame.rename(columns=rename_map)
        frame = frame.loc[:, ~frame.columns.duplicated()].copy()

        if 'route_id' in frame.columns:
            frame['route_id'] = frame['route_id'].astype(str).str.strip()
        if 'stop_id' in frame.columns:
            frame['stop_id'] = frame['stop_id'].astype(str).str.strip()
        if 'stop_name' in frame.columns:
            frame['stop_name'] = frame['stop_name'].astype(str).fillna('Unknown')
        if 'direction' in frame.columns:
            frame['direction'] = frame['direction'].astype(str).fillna('Unknown')

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
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if 'date' not in df.columns:
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

    return df


def safe_days(dff):
    if dff['date'].notna().any():
        span = dff['date'].max() - dff['date'].min()
        return max(int(span.days) + 1, 1)
    return 1


def empty_figure(title='No data available'):
    fig = px.bar(x=[], y=[] )
    fig.update_layout(title=title, xaxis_title=None, yaxis_title=None, paper_bgcolor='white')
    fig.update_xaxes(showgrid=False, visible=False)
    fig.update_yaxes(showgrid=False, visible=False)
    return fig


def make_kpi(title, value):
    return dbc.Card(dbc.CardBody([html.Div(title, className='text-muted'), html.H3(value)]), className='h-100')


def build_tab_content(tab_id, dff, has_geo):
    if tab_id == 'tab-routes':
        route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
        route_summary['avg_daily'] = route_summary['passengers'] / safe_days(dff)
        route_summary = route_summary.sort_values('passengers', ascending=False)
        direction_breakdown = dff.groupby(['route_id', 'direction'], as_index=False).agg({'passengers': 'sum'})

        return html.Div([
            dbc.Row(dbc.Col(dcc.Graph(figure=px.bar(route_summary.head(12), x='route_id', y='passengers', title='Top Routes by Total Passengers')))),
            dbc.Row(dbc.Col(dcc.Graph(figure=px.bar(route_summary.head(12), x='route_id', y='avg_daily', title='Top Routes by Avg Daily Passengers')))),
            dbc.Row(dbc.Col(dcc.Graph(figure=px.bar(direction_breakdown, x='route_id', y='passengers', color='direction', barmode='group', title='Direction Breakdown by Route')))),
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
        top_stops_fig = px.bar(top_stops, x='passengers', y='stop_name', orientation='h', title='Top Stops by Passengers')
        top_stops_fig.update_layout(yaxis={'categoryorder': 'total ascending'})

        ba = dff.groupby('stop_name', as_index=False).agg({'boardings': 'sum', 'alightings': 'sum'})
        ba = ba.melt(id_vars='stop_name', value_vars=['boardings', 'alightings'], var_name='type', value_name='count')
        ba_fig = px.bar(ba, x='stop_name', y='count', color='type', title='Boardings vs Alightings')
        ba_fig.update_layout(xaxis_tickangle=-45)

        content = [
            dbc.Row(dbc.Col(dcc.Graph(figure=top_stops_fig))),
            dbc.Row(dbc.Col(dcc.Graph(figure=ba_fig))),
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
                    height=450,
                )
                map_fig.update_layout(mapbox_style='open-street-map', margin={'r': 0, 't': 30, 'l': 0, 'b': 0})
                content.insert(0, dbc.Row(dbc.Col(dcc.Graph(id='map-stops', figure=map_fig))))
            else:
                content.insert(0, dbc.Row(dbc.Col(html.Div('No coordinate data available for the selected filters.'))))
        else:
            content.insert(0, dbc.Row(dbc.Col(html.Div('No geographic coordinates present in the loaded data.'))))

        return html.Div(content)

    route_summary = dff.groupby('route_id', as_index=False).agg({'passengers': 'sum'})
    route_summary['avg_daily'] = route_summary['passengers'] / safe_days(dff)
    route_summary = route_summary.sort_values('passengers', ascending=False)

    stop_summary = dff.groupby(['stop_id', 'stop_name'], as_index=False).agg({'passengers': 'sum'})
    stop_summary = stop_summary.sort_values('passengers', ascending=False).head(12)

    overview_figs = [
        px.bar(route_summary.head(10), x='route_id', y='passengers', title='Top 10 Routes by Passengers'),
        px.bar(stop_summary, x='passengers', y='stop_name', orientation='h', title='Top Stops by Passengers'),
    ]
    overview_figs[1].update_layout(yaxis={'categoryorder': 'total ascending'})

    ba = dff.groupby('stop_name', as_index=False).agg({'boardings': 'sum', 'alightings': 'sum'})
    ba = ba.melt(id_vars='stop_name', value_vars=['boardings', 'alightings'], var_name='type', value_name='count')
    ba_fig = px.bar(ba, x='stop_name', y='count', color='type', title='Boardings vs Alightings')
    ba_fig.update_layout(xaxis_tickangle=-45)

    return html.Div([
        dbc.Row(dbc.Col(dcc.Graph(figure=overview_figs[0]))),
        dbc.Row(dbc.Col(dcc.Graph(figure=overview_figs[1]))),
        dbc.Row(dbc.Col(dcc.Graph(figure=ba_fig))),
    ])


df = load_data()
all_routes = sorted(df['route_id'].dropna().unique())
all_directions = sorted(df['direction'].dropna().unique())
min_date = df['date'].min()
max_date = df['date'].max()
has_geo = 'latitude' in df.columns and 'longitude' in df.columns and df[['latitude', 'longitude']].notna().any().any()

app = Dash(__name__, external_stylesheets=[dbc.themes.LUMEN])
app.config.suppress_callback_exceptions = True

app.layout = dbc.Container(fluid=True, children=[
    dbc.Row(dbc.Col(html.H1('Southern Gold Coast Bus Dashboard'), width=12), className='mb-4'),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Filters')),
                dbc.CardBody([
                    html.Div([
                        html.Label('Route'),
                        dcc.Dropdown(
                            id='route-filter',
                            options=[{'label': r, 'value': r} for r in all_routes],
                            value=all_routes,
                            multi=True,
                        ),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Direction'),
                        dcc.Checklist(
                            id='direction-filter',
                            options=[{'label': d, 'value': d} for d in all_directions],
                            value=all_directions,
                        ),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Date Range'),
                        dcc.DatePickerRange(
                            id='date-range',
                            start_date=min_date,
                            end_date=max_date,
                            display_format='DD/MM/YYYY',
                        ),
                    ], className='mb-3'),
                    html.Div([
                        html.Label('Sort Routes By'),
                        dcc.Dropdown(
                            id='sort-by',
                            options=[
                                {'label': 'Total Passengers', 'value': 'passengers'},
                                {'label': 'Average Daily Passengers', 'value': 'avg_daily'},
                            ],
                            value='passengers',
                            clearable=False,
                        ),
                    ]),
                ]),
            ]),
            html.Div(id='stop-info-card', className='mt-3'),
            dbc.Card([
                dbc.CardHeader(html.H5('Stop Summary')),
                dbc.CardBody([
                    dash_table.DataTable(
                        id='stop-table',
                        columns=[
                            {'name': 'Stop ID', 'id': 'stop_id'},
                            {'name': 'Stop Name', 'id': 'stop_name'},
                            {'name': 'Passengers', 'id': 'passengers'},
                            {'name': 'Routes', 'id': 'routes'},
                        ],
                        page_size=8,
                        sort_action='native',
                        style_table={'overflowX': 'auto'},
                        style_cell={'textAlign': 'left', 'padding': '5px'},
                        style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                    )
                ]),
            ], className='mt-3'),
        ], width=3),
        dbc.Col([
            dbc.Row([
                dbc.Col(make_kpi('Total Passengers', id='kpi-total'), width=3),
                dbc.Col(make_kpi('Busiest Route', id='kpi-busiest-route'), width=3),
                dbc.Col(make_kpi('Top Stop', id='kpi-busiest-stop'), width=3),
                dbc.Col(make_kpi('Avg Daily', id='kpi-avg-daily'), width=3),
            ], className='mb-3'),
            dbc.Row([
                dbc.Col(make_kpi('Weekday Passengers', id='kpi-weekday'), width=6),
                dbc.Col(make_kpi('Weekend Passengers', id='kpi-weekend'), width=6),
            ], className='mb-3'),
            dbc.Tabs([
                dbc.Tab(label='Overview', tab_id='tab-overview'),
                dbc.Tab(label='Routes', tab_id='tab-routes'),
                dbc.Tab(label='Stops', tab_id='tab-stops'),
                dbc.Tab(label='Trend', tab_id='tab-trend'),
            ], id='tabs', active_tab='tab-overview'),
            html.Div(id='tab-content', className='mt-3'),
        ], width=9),
    ]),
])


@app.callback(
    Output('kpi-total', 'children'),
    Output('kpi-busiest-route', 'children'),
    Output('kpi-busiest-stop', 'children'),
    Output('kpi-avg-daily', 'children'),
    Output('kpi-weekday', 'children'),
    Output('kpi-weekend', 'children'),
    Output('tab-content', 'children'),
    Output('stop-table', 'data'),
    Input('route-filter', 'value'),
    Input('direction-filter', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
    Input('tabs', 'active_tab'),
    Input('sort-by', 'value'),
)
def update_dashboard(selected_routes, selected_dirs, start_date, end_date, active_tab, sort_by):
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
        content = html.Div('No data matches the selected filters.')
        return '0', 'N/A', 'N/A', '0', '0', '0', content, []

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

    content = build_tab_content(active_tab, dff, has_geo)
    table_data = stop_summary[['stop_id', 'stop_name', 'passengers', 'routes']].head(15).to_dict('records')

    return (
        f'{total_passengers:,}',
        f'{busiest_route['route_id']} ({int(busiest_route['passengers']):,})',
        f'{busiest_stop['stop_name']} ({int(busiest_stop['passengers']):,})',
        f'{avg_daily:,}',
        f'{weekday_passengers:,}',
        f'{weekend_passengers:,}',
        content,
        table_data,
    )


@app.callback(
    Output('stop-info-card', 'children'),
    Input('map-stops', 'clickData'),
    Input('route-filter', 'value'),
    Input('direction-filter', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
)
def update_stop_info(click_data, selected_routes, selected_dirs, start_date, end_date):
    if click_data is None:
        return dbc.Card([
            dbc.CardHeader('Selected Stop Details'),
            dbc.CardBody('Click a stop marker in the Stops tab to view ridership details.'),
        ])

    point = click_data['points'][0]
    custom = point.get('customdata', [])
    stop_id = custom[0] if len(custom) > 0 else None
    stop_name = custom[1] if len(custom) > 1 else point.get('hovertext')

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

    stop_filter = dff['stop_id'] == str(stop_id) if stop_id is not None else dff['stop_name'] == stop_name
    stop_data = dff[stop_filter]
    if stop_data.empty:
        return dbc.Card([
            dbc.CardHeader('Selected Stop Details'),
            dbc.CardBody('No data found for the selected stop.'),
        ])

    total = int(stop_data['passengers'].sum())
    boardings = int(stop_data['boardings'].sum())
    alightings = int(stop_data['alightings'].sum())
    top_routes = stop_data.groupby('route_id', as_index=False).agg({'passengers': 'sum'}).sort_values('passengers', ascending=False).head(5)
    route_fig = px.bar(top_routes, x='route_id', y='passengers', title='Top Routes Serving This Stop')

    return dbc.Card([
        dbc.CardHeader(f'Stop: {stop_name or stop_id}'),
        dbc.CardBody([
            html.Div(f'Total passengers: {total:,}'),
            html.Div(f'Boardings: {boardings:,}'),
            html.Div(f'Alightings: {alightings:,}'),
            dcc.Graph(figure=route_fig, style={'height': '260px'}),
        ]),
    ])


if __name__ == '__main__':
    app.run_server(debug=True, port=8050)
