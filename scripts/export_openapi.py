"""Write the API's OpenAPI schema to frontend/openapi.json (input for TS type generation)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from serve_api.app import create_app
from serve_api.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "frontend" / "openapi.json"
    with tempfile.TemporaryDirectory() as tmp:
        schema = create_app(Settings(data_dir=Path(tmp))).openapi()
    out.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
