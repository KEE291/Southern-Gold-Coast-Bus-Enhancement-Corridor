import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / 'app.py'

spec = importlib.util.spec_from_file_location('app_module', APP_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_load_data_returns_expected_frames():
    df, route_order = module.load_data()
    assert not df.empty
    assert 'route_id' in df.columns
    assert 'stop_name' in df.columns
    assert 'passengers' in df.columns
    assert 'date' in df.columns

    assert 'route_id' in route_order.columns or route_order.empty
