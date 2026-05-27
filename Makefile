.PHONY: dev backend test eval reindex

dev:
	docker compose up -d

backend:
	python main.py

test:
	pytest

eval:
	python eval/retrieval_eval.py

reindex:
	python scripts/reindex_collection.py
