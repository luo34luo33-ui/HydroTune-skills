"""Report archive status for the old Intake v0.1 inspect benchmark."""
from __future__ import annotations

import json
from pathlib import Path


BENCHMARK = Path(__file__).parent


def main() -> None:
    cases = json.loads((BENCHMARK / "cases.json").read_text(encoding="utf-8"))["cases"]
    print(
        f"Archived {len(cases)} Intake v0.1 cases. "
        "The current Intake runtime no longer provides hydrotune inspect; "
        "use these files only for Agent-first preprocessing evaluations."
    )


if __name__ == "__main__":
    main()
