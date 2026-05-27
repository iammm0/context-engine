# Evaluation

Run retrieval evaluation with:

```bash
make eval
```

or:

```bash
python eval/retrieval_eval.py
```

The script reads `RETRIEVAL_DATASET` or defaults to
`eval/retrieval_dataset.json`. Results are written to JSON and Markdown.

## Metrics

- Recall@K
- Precision@K
- nDCG@K
- MRR
- Citation recall
- Citation precision

## Dataset Format

```json
[
  {
    "id": "q1",
    "query": "Question text",
    "gold": {
      "document_id": "document id",
      "chunk_indices": [1, 2]
    }
  }
]
```

Gold chunk indices should point to chunks created in MongoDB for the selected
document.
