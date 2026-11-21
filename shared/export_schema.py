"""Write JSON Schema files for the contract so non-Python clients (React UI, etc.) can use it.

Usage: python -m shared.export_schema
"""

import json
from pathlib import Path

from shared import contracts

MODELS = [
    contracts.Chunk,
    contracts.RetrievedChunk,
    contracts.DraftAnswer,
    contracts.Finding,
    contracts.AgentAnswer,
    contracts.AskRequest,
    contracts.EvalCase,
]


def main() -> None:
    out = Path(__file__).parent / "schema"
    out.mkdir(exist_ok=True)
    for model in MODELS:
        path = out / f"{model.__name__}.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
