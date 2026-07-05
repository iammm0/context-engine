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
8. Validate generated citations as warnings and structured citation quality
   diagnostics, without blocking the response.

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
- `image_ocr`: normalized OCR metadata for parsed images. PDF images, standalone
  image files, and Word embedded images use the same compact shape when OCR is
  enabled.
- `parse_summary`: compact document-level parse quality counters, including
  parser type, extraction method, page count, extracted page count, table count,
  formula count, OCR image count, OCR text length, OCR image coverage, OCR
  average confidence, low-confidence image counts, chunk anchor coverage, chunk
  token size distribution, and structured artifact preview coverage.
- `parse_quality`: the document-level quality summary stored on
  `documents.metadata`, including `quality_score`, `page_coverage`, warning
  messages, chunk `content_type_counts`, `risk_level`, structured
  `quality_checks`, and recommended follow-up actions.

`parse_quality.quality_checks` keeps each parser diagnostic as a stable item
with `id`, `label`, `status`, `severity`, `message`, and optional `action`.
The current checks cover text extraction, page coverage, image OCR, chunk type
recognition, chunk anchor coverage, chunk size distribution, OCR confidence,
structured artifact completeness, table chunk retention, and formula chunk
retention. Artifact completeness checks whether table/OCR/formula/code chunks
carry compact preview artifacts, whether table artifacts preserve structure, and
whether OCR artifacts retain image source refs. The legacy `warnings` array is
still returned for compatibility, while `risk_level` gives clients a compact
`low` / `medium` / `high` signal.

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
- `content_type`: optional chunk type filter, for example `table`,
  `image_ocr`, `formula`, or `code`.
- `feature`: optional feature filter, for example `has_table` or
  `has_image_ocr`.
- `q`: optional keyword search across chunk text, preview, section path, and
  compact artifact data such as table cells or OCR text.
- `target_chunk_id` / `target_chunk_index`: optional evidence locator. When
  provided, the API shifts the returned window so the matching chunk is included
  near its surrounding context.
- `context_window`: number of chunks to keep before the target when using a
  target locator, default `4`.

The response includes `total_chunks` for the current filtered result and
`total_all_chunks` for the full document chunk count. When a target locator is
used, the response also returns `target_found`, `target_offset`,
`target_chunk_id`, and `target_chunk_index` so clients can highlight the exact
source chunk.

The Next.js document page uses this endpoint to show chunk type, page/section
location, feature flags, token count, parse quality, and preview text. The
chunk inspector keeps the active `content_type`/`q` filters while using
`skip`/`limit` to load more matching chunks for long documents. The
document list also shows a compact parse quality line for completed documents
when `metadata.parse_quality` is available.

For table and OCR chunks, preview responses include a compact `artifact`:

- Table artifacts expose `headers`, `rows`, `row_count`, `column_count`, and a
  Markdown fallback. When the chunk text is not a Markdown table, the artifact
  builder falls back to parser metadata such as `metadata.tables[].markdown`,
  `metadata.tables[].data`, or semantic headers so the visual table structure is
  still preserved. Table artifacts can also include compact `sources` refs with
  `table_index`, `page`/`page_end`, `caption`, `type`, `source`/`target`,
  `bbox`, and table dimensions so table evidence remains traceable to its
  parser origin.
- OCR artifacts expose the normalized OCR text preview, image count, and image
  source refs when known. Each source ref can include `page`, `image_index`,
  `confidence`, `line_count`, `text_length`, compact `text_preview`,
  `low_confidence`, `width`, `height`, and parser source `target` for embedded
  Word images.

Chat evidence cards show the evidence id, content type, page/section location,
retrieval type, and score so generated citations such as `[S1]` are easier to
trace back to source chunks. In the chat UI, inline citations such as `[S1]`
are rendered as citation chips when matching evidence is available; selecting a
chip opens the evidence list and highlights the corresponding source chunk.
Evidence and source cards also link to `/documents` with the document and chunk
locator, opening the chunk inspector around the cited chunk for source review.
Assistant messages can include `citation_quality` with citation coverage,
valid/invalid citation ids, duplicate citations, unused evidence ids, and the
highest-scored evidence that was not referenced. The UI displays this as a
compact citation audit line next to any non-blocking `citation_warnings`.
Assistant messages can also include `evidence_quality`, a runtime diagnostic for
retrieved structured evidence. It reports artifact coverage, structured artifact
coverage, table structure/source gaps, OCR source gaps, low-confidence OCR image
refs, and compact recommendations for re-parsing or reindexing when evidence is
not source-complete.

## EvidenceItem

Each evidence item includes `id`, `text`, `document_id` or `file_id`,
`chunk_id`, `chunk_index`, `document_title`, `section_path`, `page`, `score`,
`retrieval_type`, and `metadata`. Evidence context now includes the chunk
`content_type` and can display page ranges when a chunk spans multiple pages.
When available, compact table/OCR/formula/code `artifact` data is carried in
`metadata.artifact` so chat evidence cards can render the same source-specific
preview as the document chunk inspector. The generation context also includes a
short artifact summary before the raw chunk text: table evidence exposes column
names, sample rows, and table source refs; OCR evidence exposes image source
refs, confidence, low-confidence flags, and per-image OCR text previews; and
formula/code evidence exposes a compact content preview.
Generated answers are checked against the available `EvidenceItem` ids to build
`citation_quality.status`, `coverage`, `valid_citation_ids`,
`invalid_citation_ids`, `duplicate_citation_ids`, `unused_evidence_ids`, and
`unreferenced_top_evidence_ids`.
The same evidence list is checked before generation to build
`evidence_quality.status`, `risk_level`, `artifact_coverage`,
`structured_artifact_coverage`, table/OCR completeness counters, warnings, and
recommendations. This lets the chat UI expose when an answer used table or OCR
evidence whose source preview is incomplete.

## Compatibility

`POST /api/retrieval` still returns `context`, `sources`, `retrieval_count`, and
`recommended_resources`. New clients should prefer the `evidence`, `query_plan`,
`evidence_quality`, and `trace` fields.
