# Reindexing

Qdrant collections are no longer automatically recreated when vector dimensions
do not match. This prevents accidental data loss.

Run a safe rebuild into a new collection:

```bash
python scripts/reindex_collection.py --collection-name default_knowledge
```

Scope by knowledge space:

```bash
python scripts/reindex_collection.py --knowledge-space-id <id>
```

Scope by document:

```bash
python scripts/reindex_collection.py --document-id <id>
```

By default the script writes to `<source>_reindex_<timestamp>`. Use
`--target-collection` to choose a fixed target collection. The script prints a
manifest with the source collection, target collection, embedding model, vector
dimension, and chunk count.

Production operators should verify the target collection before switching users
or knowledge spaces to it.
