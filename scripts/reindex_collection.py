"""Rebuild Qdrant vectors into a new collection without deleting old data."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List, Optional

from database.mongodb import mongodb_client
from database.qdrant_client import get_qdrant_client
from embedding.embedding_service import embedding_service
from utils.logger import logger


def _resolve_collection_name(knowledge_space_id: Optional[str], collection_name: str) -> str:
    if not knowledge_space_id:
        return collection_name
    if mongodb_client.db is None:
        mongodb_client.connect()
    spaces = mongodb_client.get_collection("knowledge_spaces")
    doc = spaces.find_one({"_id": knowledge_space_id})
    if not doc:
        try:
            from bson import ObjectId
            doc = spaces.find_one({"_id": ObjectId(knowledge_space_id)})
        except Exception:
            doc = None
    return (doc or {}).get("collection_name") or collection_name


def _load_chunks(knowledge_space_id: Optional[str], document_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    if mongodb_client.db is None:
        mongodb_client.connect()
    chunks = mongodb_client.get_collection("chunks")
    query: Dict[str, Any] = {}
    if document_id:
        query["document_id"] = document_id
    elif knowledge_space_id:
        documents = mongodb_client.get_collection("documents")
        doc_ids = [str(d["_id"]) for d in documents.find({"knowledge_space_id": knowledge_space_id}, {"_id": 1})]
        if doc_ids:
            query["document_id"] = {"$in": doc_ids}
    cursor = chunks.find(query).sort([("document_id", 1), ("chunk_index", 1)])
    if limit > 0:
        cursor = cursor.limit(limit)
    return [{**chunk, "_id": str(chunk["_id"])} for chunk in cursor]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex chunks into a new Qdrant collection.")
    parser.add_argument("--collection-name", default="default_knowledge", help="Source collection name used for naming only.")
    parser.add_argument("--target-collection", default="", help="Target Qdrant collection. Defaults to <source>_reindex_<ts>.")
    parser.add_argument("--knowledge-space-id", default="", help="Optional knowledge space id to select documents.")
    parser.add_argument("--document-id", default="", help="Optional single document id.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0, help="Limit chunks for dry smoke runs. 0 means all.")
    parser.add_argument("--manifest-out", default="", help="Optional JSON manifest output path.")
    args = parser.parse_args()

    source_collection = _resolve_collection_name(args.knowledge_space_id or None, args.collection_name)
    target_collection = args.target_collection or f"{source_collection}_reindex_{int(time.time())}"
    chunks = _load_chunks(args.knowledge_space_id or None, args.document_id or None, args.limit)
    if not chunks:
        raise SystemExit("No chunks found for the requested scope.")

    qdrant = get_qdrant_client(target_collection)
    vector_dim = embedding_service.dimension
    qdrant.create_collection(vector_size=vector_dim)

    inserted = 0
    for start in range(0, len(chunks), args.batch_size):
        batch = chunks[start:start + args.batch_size]
        texts = [chunk.get("text", "") for chunk in batch]
        vectors = embedding_service.encode(texts)
        payloads = []
        ids = []
        for chunk in batch:
            meta = chunk.get("metadata") or {}
            payloads.append({
                "chunk_id": chunk["_id"],
                "document_id": chunk.get("document_id"),
                "text": chunk.get("text", ""),
                "chunk_index": chunk.get("chunk_index"),
                "metadata": {
                    **meta,
                    "embedding_model": embedding_service.model_name,
                    "vector_dimension": vector_dim,
                    "chunk_version": meta.get("chunk_version", "v1"),
                    "reindexed_at": int(time.time()),
                },
            })
            ids.append(chunk["_id"])
        qdrant.insert_vectors(vectors=vectors, payloads=payloads, ids=ids)
        inserted += len(batch)
        logger.info(f"Reindexed {inserted}/{len(chunks)} chunks into {target_collection}")

    manifest = {
        "source_collection": source_collection,
        "target_collection": target_collection,
        "chunk_count": inserted,
        "embedding_model": embedding_service.model_name,
        "vector_dimension": vector_dim,
        "knowledge_space_id": args.knowledge_space_id or None,
        "document_id": args.document_id or None,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.manifest_out:
        with open(args.manifest_out, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
