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

## EvidenceItem

Each evidence item includes `id`, `text`, `document_id` or `file_id`,
`chunk_id`, `chunk_index`, `document_title`, `section_path`, `page`, `score`,
`retrieval_type`, and `metadata`.

## Compatibility

`POST /api/retrieval` still returns `context`, `sources`, `retrieval_count`, and
`recommended_resources`. New clients should prefer the `evidence`, `query_plan`,
and `trace` fields.
