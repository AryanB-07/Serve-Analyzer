import json
import tempfile
from pathlib import Path

from serve_api.app import create_app
from serve_api.settings import Settings

COMMITTED = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def test_committed_openapi_matches_app():
    """If this fails, run `npm run gen:api` in frontend/ and commit the result."""
    with tempfile.TemporaryDirectory() as tmp:
        live = create_app(Settings(data_dir=Path(tmp))).openapi()
    assert json.loads(COMMITTED.read_text()) == live
