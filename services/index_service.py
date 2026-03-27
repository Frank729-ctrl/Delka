from datetime import datetime

_client = None


def get_chroma_client():
    global _client
    if _client is None:
        import chromadb
        from config import settings
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def get_collection(platform: str):
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=f"{platform}_index",
        metadata={"hnsw:space": "cosine"},
    )


async def index_single_item(
    platform: str,
    item_id: str,
    embedding: list[float],
    metadata: dict,
    image_url: str,
    db,
) -> bool:
    from sqlalchemy import select
    from models.vision_index_model import VisionIndexItem

    collection = get_collection(platform)
    chroma_id = f"{platform}_{item_id}"
    safe_meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                 for k, v in metadata.items()}
    safe_meta["item_id"] = item_id
    safe_meta["platform"] = platform

    collection.upsert(
        ids=[chroma_id],
        embeddings=[embedding],
        metadatas=[safe_meta],
    )

    now = datetime.utcnow()
    result = await db.execute(
        select(VisionIndexItem).where(
            VisionIndexItem.item_id == item_id,
            VisionIndexItem.platform == platform,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.is_indexed = True
        row.indexed_at = now
        row.metadata_ = metadata
        if image_url:
            row.image_url = image_url
    else:
        db.add(VisionIndexItem(
            item_id=item_id,
            platform=platform,
            image_url=image_url or None,
            metadata_=metadata,
            is_indexed=True,
            indexed_at=now,
        ))
    return True


async def search_similar(
    platform: str,
    query_embedding: list[float],
    limit: int,
    min_similarity: float,
) -> list[dict]:
    collection = get_collection(platform)
    count = collection.count()
    if count == 0:
        return []

    n = min(limit, count)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n,
        include=["metadatas", "distances"],
    )

    output = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    for i, (chroma_id, distance, meta) in enumerate(zip(ids, distances, metadatas)):
        similarity = 1.0 - distance
        if similarity < min_similarity:
            continue
        item_id = meta.get("item_id", chroma_id)
        clean_meta = {k: v for k, v in meta.items()
                      if k not in ("item_id", "platform")}
        output.append({
            "item_id": item_id,
            "similarity_score": round(similarity, 4),
            "rank": i + 1,
            "metadata": clean_meta,
        })

    return sorted(output, key=lambda x: x["similarity_score"], reverse=True)


async def remove_item(platform: str, item_id: str, db) -> bool:
    from sqlalchemy import select, delete
    from models.vision_index_model import VisionIndexItem

    collection = get_collection(platform)
    chroma_id = f"{platform}_{item_id}"
    try:
        collection.delete(ids=[chroma_id])
    except Exception:
        pass

    await db.execute(
        delete(VisionIndexItem).where(
            VisionIndexItem.item_id == item_id,
            VisionIndexItem.platform == platform,
        )
    )
    return True


async def get_index_stats(platform: str, db) -> dict:
    from sqlalchemy import select, func
    from models.vision_index_model import VisionIndexItem

    result = await db.execute(
        select(
            func.count(VisionIndexItem.id),
            func.max(VisionIndexItem.indexed_at),
        ).where(
            VisionIndexItem.platform == platform,
            VisionIndexItem.is_indexed.is_(True),
        )
    )
    row = result.one()
    total = row[0] or 0
    last_indexed = row[1].isoformat() if row[1] else None

    # Rough size estimate: ~6KB per vector (512 floats * 4 bytes + metadata overhead)
    size_mb = round((total * 6) / 1024, 3)

    return {
        "platform": platform,
        "total_indexed": total,
        "last_indexed_at": last_indexed,
        "collection_size_mb": size_mb,
    }


async def platform_exists(platform: str) -> bool:
    try:
        collection = get_collection(platform)
        return collection.count() > 0
    except Exception:
        return False
