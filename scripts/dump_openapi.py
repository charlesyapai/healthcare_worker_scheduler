"""Dump the FastAPI app's OpenAPI spec as JSON.

Used by the UI build to regenerate `ui/src/api/types.ts` without having to
run a live server. Run from the repo root:

    python scripts/dump_openapi.py > ui/src/api/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app  # noqa: E402


def main() -> None:
    spec = app.openapi()
    json.dump(spec, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
