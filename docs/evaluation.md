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
`eval/retrieval_dataset.example.json`. Results are written to JSON and
Markdown.

## Metrics

- Recall@K
- Precision@K
- nDCG@K
- MRR
- Citation recall
- Citation precision
- Artifact quality
- Source locator quality
- Citation quality

`Artifact quality` checks whether retrieved evidence preserves structured
preview artifacts and normalized source locators needed by document review and
answer citation UI:

- gold chunk coverage and missing gold chunk indices
- artifact coverage among retrieved evidence
- structured artifact coverage for table, OCR, formula, and code chunks
- source locator coverage among retrieved evidence
- source locator coverage for gold hits and structured evidence
- bbox, table-source, OCR-source, and source-anchor locator counts
- table artifact structure and source-reference retention
- OCR source-reference coverage, low-confidence image counts, and average OCR
  confidence
- missing required artifact types declared by the dataset

`Citation quality` is computed when a dataset item includes an `answer`,
`generated_answer`, `generated.answer`, or a precomputed `citation_quality`
object. Generated answers are checked with the same diagnostics used by the
chat pipeline, including valid/invalid citation ids, duplicate citations,
unused evidence ids, coverage, status, risk level, cited structured evidence
counts, cited evidence missing `source_locator`, cited artifact warnings,
cited low-confidence OCR evidence, cited `quality_notes`,
`evidence_citation_audit` type/locator/risk ledger,
`cited_risky_evidence` locator details, and warnings.

## Dataset Format

```json
[
  {
    "id": "q1",
    "query": "Question text",
    "gold": {
      "document_id": "document id",
      "chunk_indices": [1, 2],
      "required_artifact_types": ["table", "image_ocr"]
    },
    "answer": "Optional generated answer with citations such as [S1]."
  }
]
```

Gold chunk indices should point to chunks created in MongoDB for the selected
document. `required_artifact_types` can be placed either inside `gold` or at
the top level of the dataset item. Supported structured artifact types are
`table`, `image_ocr`, `ocr`, `formula`, and `code`.

## Result Shape

The JSON result now includes an `items` array with per-query diagnostics:

- `artifact_quality`: per-query gold coverage, artifact coverage, table/OCR
  completeness, source locator coverage, and missing required artifact types
- `citation_quality`: optional per-query citation diagnostics when an answer or
  precomputed citation quality object is available, including cited risky
  evidence locators and the full evidence citation audit ledger when a
  generated answer cites low-quality or hard-to-source evidence

The aggregate values are also written under `metrics.artifact` and
`metrics.citation_quality`, and the Markdown report renders separate
`Artifact Quality` and `Citation Quality` sections. The `Artifact Quality`
section includes source locator coverage rows such as
`avg_source_locator_coverage`, `avg_structured_source_locator_coverage`, and
`structured_missing_source_locator_count`, so evaluation runs can catch evidence
that retrieves the right chunk but cannot reliably jump back to the original
page, table, OCR image, or bbox. The `Citation Quality` section also includes
`risk_level_counts`, `cited_missing_source_locator_count`,
`cited_artifact_warning_count`, `cited_low_confidence_ocr_count`, and
`cited_quality_note_count`, so answer evaluation can catch cases where
generated text cites evidence ids but cites evidence that still needs source,
OCR, or chunk-quality review.
