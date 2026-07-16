# Bus Network Dashboard

Quick starter for an interactive Bus Network dashboard (Plotly Dash).

Setup

1. Create a virtualenv and install:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Run the app:

```bash
python app.py
```

3. Open http://127.0.0.1:8050 in your browser.

Notes

- Replace `data/ridership_sample.csv` with your CSV. Expected columns: `date,route_id,stop_id,stop_name,direction,boardings,alightings,latitude,longitude`.
- If you have route GeoJSON files, we can add overlay layers on the map.# Southern-Gold-Coast-Bus-Enhancement-Corridor
Data Analysis Southern Gold Coast Bus Enhancement Corridor
