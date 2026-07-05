# RAG Pipeline

advanced-rag keeps the legacy `context` and `sources` response fields, but the
retrieval pipeline is now centered on chunk-level evidence.

## Flow

1. Parse and chunk uploaded documents.
2. Store chunks in MongoDB and vectors in Qdrant.
3. Build a rule-based `QueryPlan` for each query.
4. Retrieve candidates with vector search, BM25-style keyword search, and
   optional graph expansion.
5. Fuse candidates with Reciprocal Rank Fusion by default.
6. Convert final chunks into `EvidenceItem[]`.
7. Format evidence as `[S1] ...` context for generation.
8. Validate generated citations as warnings, without blocking the response.

## RAGFlow-style Ingestion Metadata

The ingestion path now keeps parser output explainable without copying large
parser payloads into every chunk. After parsing and chunking, each chunk is
enriched with compact metadata for preview, citation, and debugging:

- `content_type`: inferred chunk type such as `text`, `table`, `image_ocr`,
  `formula`, or `code`.
- `section_path`: detected heading path when available.
- `page`, `page_start`, `page_end`: page-level source location derived from
  parser page spans.
- `char_start`, `char_end`: character offsets in the synthesized document text.
- `preview`: normalized short text used by chunk visualization UIs.
- `features`: booleans such as `has_table`, `has_image_ocr`, `has_formula`, and
  `has_code`.
- `parse_summary`: compact document-level parse quality counters, including
  parser type, extraction method, page count, extracted page count, table count,
  formula count, OCR image count, and OCR text length.

Heavy parser fields such as `pages`, `tables`, `formulas`, and `code_blocks`
remain on the document metadata when available, but are removed from repeated
per-chunk metadata before chunk storage.

## Chunk Preview API

`GET /api/documents/{doc_id}/chunks` returns paginated chunk previews for
document chunk visualization.

Query parameters:

- `skip`: default `0`.
- `limit`: default `100`, maximum `500`.
- `include_text`: default `true`; set to `false` for a lightweight preview.

The Next.js document page uses this endpoint to show chunk type, page/section
location, feature flags, token count, and preview text.

## EvidenceItem

Each evidence item includes `id`, `text`, `document_id` or `file_id`,
`chunk_id`, `chunk_index`, `document_title`, `section_path`, `page`, `score`,
`retrieval_type`, and `metadata`. Evidence context now includes the chunk
`content_type` and can display page ranges when a chunk spans multiple pages.

## Compatibility

`POST /api/retrieval` still returns `context`, `sources`, `retrieval_count`, and
`recommended_resources`. New clients should prefer the `evidence`, `query_plan`,
and `trace` fields.
