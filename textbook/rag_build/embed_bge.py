#!/usr/bin/env python3
"""
Generate embeddings using BGE-M3 and store in Weaviate.
BGE-M3: 1024-dim, supports Chinese natively, no translation needed.
"""

import json
import os
import torch
from pathlib import Path
from FlagEmbedding import BGEM3FlagModel
import weaviate
from weaviate.classes.init import AdditionalConfig
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.data import DataObject
from tqdm import tqdm


TEXTBOOK_DIR = Path(__file__).parent.parent
MODEL_SOURCE = os.environ.get('RAG_MODEL_DIR', 'BAAI/bge-m3')
DATA_DIR = Path(os.environ.get('RAG_DATA_DIR', str(TEXTBOOK_DIR / 'weaviate_data')))
CHUNKS_FILE = Path(
    os.environ.get('RAG_CHUNKS_FILE', str(TEXTBOOK_DIR / 'merged' / 'chunks_final.json'))
)


def load_model():
    """Load BGE-M3 model."""
    print(f"Loading BGE-M3 from {MODEL_SOURCE}...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = BGEM3FlagModel(
        MODEL_SOURCE,
        use_fp16=(device == "cuda"),
        devices=device,
    )
    print(f"Model loaded on {device}")
    return model


def get_embeddings(texts, model, max_length=2048):
    """Get dense embeddings for a list of texts."""
    output = model.encode(texts, max_length=max_length, return_dense=True,
                          return_sparse=False, return_colbert_vecs=False)
    return output['dense_vecs'].tolist()


def setup_weaviate():
    """Setup Weaviate client and collection with 1024-dim vectors."""
    print("Setting up Weaviate...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = weaviate.connect_to_embedded(
        headers={},
        persistence_data_path=str(DATA_DIR),
        additional_config=AdditionalConfig(timeout=(5, 120))
    )

    # Delete collection if exists
    if client.collections.exists("PhysicsChunks"):
        client.collections.delete("PhysicsChunks")

    # Create collection with 1024-dim vectors
    collection = client.collections.create(
        name="PhysicsChunks",
        properties=[
            Property(name="book", data_type=DataType.TEXT),
            Property(name="chapter", data_type=DataType.TEXT),
            Property(name="section", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="type", data_type=DataType.TEXT),
            Property(name="chunkIndex", data_type=DataType.INT),
            Property(name="totalChunks", data_type=DataType.INT),
            Property(name="imagePaths", data_type=DataType.TEXT_ARRAY),
        ],
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            vector_cache_max_objects=10000,
        ),
    )

    print("Weaviate collection created (1024-dim)")
    return client, collection


def main():
    if not CHUNKS_FILE.is_file():
        raise FileNotFoundError(
            f"Rebuild input not found: {CHUNKS_FILE}. The source-derived chunks "
            "are not shipped in this repository; create them with the documented "
            "pipeline or set RAG_CHUNKS_FILE."
        )

    print(f"Loading chunks from {CHUNKS_FILE}...")
    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks")

    model = load_model()
    client, collection = setup_weaviate()

    batch_size = 32
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    print(f"\nProcessing {len(chunks)} chunks in {total_batches} batches...")

    inserted = 0
    for batch_idx in tqdm(range(total_batches), desc="Embedding batches"):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(chunks))
        batch_chunks = chunks[start_idx:end_idx]

        # Use Chinese content for embedding (BGE-M3 handles Chinese natively)
        texts = [c['content'] for c in batch_chunks]
        embeddings = get_embeddings(texts, model)

        objects = []
        for chunk, emb in zip(batch_chunks, embeddings):
            objects.append(DataObject(
                properties={
                    "book": chunk['book'],
                    "chapter": str(chunk.get('chapter', '') or ''),
                    "section": str(chunk.get('section', '') or ''),
                    "title": chunk['title'],
                    "content": chunk['content'],
                    "type": chunk.get('type', 'content'),
                    "chunkIndex": chunk.get('chunk_index', 0),
                    "totalChunks": chunk.get('total_chunks', 1),
                    "imagePaths": chunk.get('images', []),
                },
                vector=emb,
            ))

        try:
            collection.data.insert_many(objects)
            inserted += len(objects)
        except Exception as e:
            print(f"\nError inserting batch {batch_idx}: {e}")
            continue

    print(f"\nDone! Inserted {inserted} chunks into Weaviate")

    # Test queries (Chinese)
    test_queries = ["库仑定律", "牛顿第二定律", "能量守恒", "电偶极子电场"]
    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Testing: {q}")
        q_emb = get_embeddings([q], model)[0]
        results = collection.query.near_vector(
            near_vector=q_emb, limit=3,
            return_properties=["book", "chapter", "title", "content", "type"]
        )
        for i, obj in enumerate(results.objects):
            p = obj.properties
            print(f"  {i+1}. [{p['book']}] {p['title']} | {p['type']}")
            print(f"     {p['content'][:100]}...")

    client.close()


if __name__ == '__main__':
    main()
