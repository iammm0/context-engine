# Security Boundaries

context-engine currently supports anonymous local use. Production deployments
should add authentication, authorization, and tenant isolation before exposing
the service to untrusted users.

## Uploads

- Keep upload size limits enabled.
- Treat parsed files, OCR output, and extracted text as untrusted input.
- Run document parsers in an isolated environment for public deployments.
- Review file retention policies for `uploads/` and `conversation_uploads/`.

## Secrets

- Do not commit `.env` files with real credentials.
- Use strong MongoDB, Neo4j, Qdrant, Redis, and model-provider credentials.
- Prefer private networks for databases and model runtimes.

## RAG Output

Generated answers may still be incomplete or wrong. Evidence citations help
users inspect support, but they are not a substitute for domain review in
medical, legal, financial, or safety-critical settings.
