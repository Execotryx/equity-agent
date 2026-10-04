"""Write the API's OpenAPI schema as JSON: `uv run python scripts/export_openapi.py OUT.json`.

Builds the app with placeholder settings and without running its lifespan, so no keys, network or worker are needed.
`npm run gen:types` (root package.json) runs this, then openapi-typescript writes frontend/src/lib/types.ts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from equity_agent.api import create_app
from equity_agent.config import load_settings

PLACEHOLDERS = {"ANTHROPIC_API_KEY": "unused", "TAVILY_API_KEY": "unused", "EDGAR_IDENTITY": "unused"}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    schema = create_app(load_settings(PLACEHOLDERS)).openapi()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
