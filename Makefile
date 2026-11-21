.PHONY: install api ui eval eval-bench index-samples index-bench index-code index-docs index-media ask schema test vendor ollama-up ollama-down

# uv targets ./.venv automatically (the venv is uv-made and has no pip)
install:
	uv pip install -e ".[all]"

# --- index -------------------------------------------------------------------
index-samples:
	python -m memory.ingest_docs samples/docs --reset
	python -m memory.ingest_code samples/code
	python -m memory.ingest_media samples/media

# usage: make index-code DIR=path/to/repo   (same for index-docs / index-media)
index-code:
	python -m memory.ingest_code $(DIR)

index-docs:
	python -m memory.ingest_docs $(DIR)

index-media:
	python -m memory.ingest_media $(DIR)

# Stand-in benchmark (~100 chunks of this repo's own code/docs) until the kickoff dataset exists.
# Separate index file, so it never mixes with the samples index.
BENCH = MEMORY_PATH=data/bench.sqlite
index-bench:
	$(BENCH) python -m memory.ingest_code agent api memory shared eval ui tests pyproject.toml docker-compose.yml --reset
	$(BENCH) python -m memory.ingest_docs README.md samples/docs api/static
	$(BENCH) python -m memory.ingest_media samples/media

# --- run -----------------------------------------------------------------------
# usage: make ask Q="How do I report a pothole?"
ask:
	python -m agent.pipeline $(Q)

api:
	uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

ui:
	streamlit run ui/app.py

eval:
	python -m eval.run

eval-bench:
	$(BENCH) python -m eval.run --cases eval/cases_repo.jsonl --compare extractive ollama

# --- maintenance -----------------------------------------------------------------
schema:
	python -m shared.export_schema

# Re-mirror the A2UI renderer into api/static/vendor (offline page). Needs internet once.
vendor:
	python tools/vendor_a2ui.py

test:
	pytest -q

# Only if you are NOT running Ollama natively (both bind port 11434).
ollama-up:
	docker compose --profile docker-ollama up -d --wait

ollama-down:
	docker compose --profile docker-ollama down
