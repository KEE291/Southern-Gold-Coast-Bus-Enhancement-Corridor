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

- The dashboard now loads the provided `IR-1230 TMR South Coast with data analysis for Southern Gold Coast Bus Enhancements*.csv` files for March 2026 ridership and uses the `Route's Stop Order` CSV for stop sequences in the Routes tab.
- If you want stop map markers, add `latitude` and `longitude` columns to the ridership file or provide a matching coordinates dataset.
- The filters are bound to the actual dataset date range, so the Date Range control will reflect the loaded March 2026 data.
- If you need to inspect the Excel route analysis workbook, install `openpyxl` in the virtual environment first:

```bash
./venv/bin/python -m pip install openpyxl
```

# Southern-Gold-Coast-Bus-Enhancement-Corridor
Data Analysis Southern Gold Coast Bus Enhancement Corridor
