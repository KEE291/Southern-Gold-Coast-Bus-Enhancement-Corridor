import pandas as pd
from datetime import datetime
from dash import Dash, dcc, html, Input, Output
import plotly.express as px
import glob
import os


def load_all_data():
    # look for CSVs in repo root matching IR-1230* and any in data/
    repo_root = os.path.dirname(__file__)
    patterns = [os.path.join(repo_root, 'IR-1230*.csv'), os.path.join(repo_root, 'data', '*.csv')]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    files = sorted(set(files))
    if not files:
        raise FileNotFoundError("No CSV files found to load")
    parts = []
    for f in files:
        try:
            parts.append(pd.read_csv(f, parse_dates=['date']))
        except Exception:
            try:
                parts.append(pd.read_csv(f))
            except Exception:
                continue
    if not parts:
        raise ValueError('No readable CSVs found')
    df = pd.concat(parts, ignore_index=True)
    # normalize expected columns
    if 'boardings' in df.columns and 'alightings' in df.columns:
        df['boardings'] = pd.to_numeric(df['boardings'], errors='coerce').fillna(0)
        df['alightings'] = pd.to_numeric(df['alightings'], errors='coerce').fillna(0)
        df['passengers'] = df['boardings'] + df['alightings']
    else:
        # try to infer passenger counts
        if 'passengers' in df.columns:
            df['passengers'] = pd.to_numeric(df['passengers'], errors='coerce').fillna(0)
        else:
            df['passengers'] = 0
    # Ensure route_id and stop_id string types
    if 'route_id' in df.columns:
        df['route_id'] = df['route_id'].astype(str)
    if 'stop_id' in df.columns:
        df['stop_id'] = df['stop_id'].astype(str)
    return df


df = load_all_data()

# Normalize columns that may have mixed types or missing values
if 'direction' in df.columns:
    df['direction'] = df['direction'].fillna('Unknown').astype(str)
else:
    df['direction'] = 'Unknown'

if 'date' in df.columns:
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

for col in ['latitude', 'longitude']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    else:
        df[col] = pd.NA

app = Dash(__name__)

routes = sorted(df["route_id"].unique())
directions = sorted(df["direction"].unique())

app.layout = html.Div([
    html.H2("Bus Network Overview"),
    html.Div([
        html.Div(id="kpi-total", style={"display":"inline-block","padding":"8px","width":"23%","backgroundColor":"#f3f3f3","marginRight":"1%"}),
        html.Div(id="kpi-busiest-route", style={"display":"inline-block","padding":"8px","width":"23%","backgroundColor":"#f3f3f3","marginRight":"1%"}),
        html.Div(id="kpi-busiest-stop", style={"display":"inline-block","padding":"8px","width":"23%","backgroundColor":"#f3f3f3","marginRight":"1%"}),
        html.Div(id="kpi-avg-daily", style={"display":"inline-block","padding":"8px","width":"23%","backgroundColor":"#f3f3f3"}),
    ], style={"width":"100%","marginBottom":"10px"}),
    html.Div([
        html.Div(id="kpi-weekday", style={"display":"inline-block","padding":"8px","width":"48%","backgroundColor":"#eef7ff","marginRight":"2%"}),
        html.Div(id="kpi-weekend", style={"display":"inline-block","padding":"8px","width":"48%","backgroundColor":"#fff7ee"}),
    ], style={"width":"100%","marginBottom":"10px"}),
    html.Div([
        html.Label("Route"),
        dcc.Dropdown(options=[{"label": r, "value": r} for r in routes], multi=True, value=routes, id="route-filter"),
        html.Label("Direction"),
        dcc.Checklist(options=[{"label": d, "value": d} for d in directions], value=directions, id="direction-filter"),
        html.Label("Date Range"),
        dcc.DatePickerRange(id="date-range", start_date=df["date"].min(), end_date=df["date"].max()),
    ], style={"width":"25%", "display":"inline-block", "verticalAlign":"top"}),

    html.Div([
        dcc.Graph(id="map-stops"),
        dcc.Graph(id="no-coord-stops"),
        dcc.Graph(id="top-stops"),
        dcc.Graph(id="boarding-vs-alighting"),
        dcc.Graph(id="top-routes"),
        dcc.Graph(id="direction-analysis"),
        dcc.Graph(id="heatmap-time"),
    ], style={"width":"70%", "display":"inline-block", "paddingLeft":"20px"})
])


@app.callback(
    Output("kpi-total", "children"),
    Output("kpi-busiest-route", "children"),
    Output("kpi-busiest-stop", "children"),
    Output("kpi-avg-daily", "children"),
    Output("map-stops", "figure"),
    Output("top-stops", "figure"),
    Output("boarding-vs-alighting", "figure"),
    Output("top-routes", "figure"),
    Output("direction-analysis", "figure"),
    Input("route-filter", "value"),
    Input("direction-filter", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def update_charts(selected_routes, selected_dirs, start_date, end_date):
    if not isinstance(selected_routes, list):
        selected_routes = [selected_routes]
    dff = df[df["route_id"].isin(selected_routes) & df["direction"].isin(selected_dirs)]
    if start_date:
        dff = dff[dff["date"] >= pd.to_datetime(start_date)]
    if end_date:
        dff = dff[dff["date"] <= pd.to_datetime(end_date)]

    # Map of stops
    stops = dff.groupby(["stop_id","stop_name","latitude","longitude"], as_index=False).agg({"passengers":"sum"})
    fig_map = px.scatter_mapbox(stops, lat="latitude", lon="longitude", size="passengers", hover_name="stop_name",
                                color_continuous_scale=px.colors.cyclical.IceFire, size_max=20, zoom=11)
    fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0,r=0,t=30,b=0))

    # Top stops by avg daily passengers
    days = (dff["date"].max() - dff["date"].min()).days + 1
    stop_daily = dff.groupby(["stop_id","stop_name"], as_index=False).agg({"passengers":"sum"})
    stop_daily["avg_daily"] = stop_daily["passengers"]/max(days,1)
    top_stops = stop_daily.sort_values("avg_daily", ascending=False).head(10)
    fig_top_stops = px.bar(top_stops, x="avg_daily", y="stop_name", orientation="h", title="Top Stops (Avg Daily Passengers)")

    # Boarding vs alighting
    ba = dff.groupby(["stop_name"], as_index=False).agg({"boardings":"sum","alightings":"sum"})
    ba_m = ba.melt(id_vars=["stop_name"], value_vars=["boardings","alightings"], var_name="type", value_name="count")
    fig_ba = px.bar(ba_m, x="stop_name", y="count", color="type", title="Boarding vs Alighting by Stop")

    # Top ten routes by movements
    routes_sum = dff.groupby("route_id", as_index=False).agg({"passengers":"sum"}).sort_values("passengers", ascending=False).head(10)
    fig_routes = px.bar(routes_sum, x="route_id", y="passengers", title="Top 10 Routes by Passenger Movements")

    # Direction analysis
    dir_sum = dff.groupby(["route_id","direction"], as_index=False).agg({"passengers":"sum"})
    fig_dir = px.bar(dir_sum, x="route_id", y="passengers", color="direction", barmode="group", title="Direction Analysis by Route")

    # KPIs
    total_passengers = int(dff['passengers'].sum()) if not dff.empty else 0
    busiest_route = None
    if not routes_sum.empty:
        busiest_route = f"Route {routes_sum.iloc[0]['route_id']} ({int(routes_sum.iloc[0]['passengers'])} pax)"
    busiest_stop = None
    if not top_stops.empty:
        busiest_stop = f"{top_stops.iloc[0]['stop_name']} ({int(top_stops.iloc[0]['avg_daily'])} avg/day)"
    days = (dff["date"].max() - dff["date"].min()).days + 1 if not dff.empty else 1
    avg_daily_overall = round(dff['passengers'].sum()/max(days,1),1) if not dff.empty else 0

    kpi_total = html.Div([html.H4("Total Passengers"), html.Div(f"{total_passengers:,}")])
    kpi_route = html.Div([html.H4("Busiest Route"), html.Div(busiest_route or "N/A")])
    kpi_stop = html.Div([html.H4("Top Stop (avg/day)"), html.Div(busiest_stop or "N/A")])
    kpi_avg = html.Div([html.H4("Avg Daily Passengers"), html.Div(f"{avg_daily_overall}")])

    return kpi_total, kpi_route, kpi_stop, kpi_avg, fig_map, fig_top_stops, fig_ba, fig_routes, fig_dir


if __name__ == "__main__":
    app.run_server(debug=True, port=8050)
