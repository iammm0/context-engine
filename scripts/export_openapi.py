"""Export the FastAPI OpenAPI schema for frontend type generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/export_openapi.py <output-json>", file=sys.stderr)
        return 2

    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OpenAPI schema exported to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
