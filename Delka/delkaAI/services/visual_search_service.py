import time
from fastapi import HTTPException
from schemas.vision_schema import (
    IndexRequest,
    IndexResponse,
    VisionSearchRequest,
    VisionSearchResponse,
)
from services import vision_service, index_service
from services import embedding_service


async def search(request: VisionSearchRequest, db) -> VisionSearchResponse:
    start = time.monotonic()

    image_b64 = await vision_service.get_image_base64(request)

    analysis = await vision_service.analyze_image(image_b64)

    from PIL import Image
    image_obj = embedding_service.image_from_base64(image_b64)
    img_vec = embedding_service.generate_image_embedding(image_obj)

    description_parts = [
        analysis.get("category", ""),
        analysis.get("description", ""),
        " ".join(analysis.get("colors", [])),
        analysis.get("material", ""),
        analysis.get("brand_text", ""),
        analysis.get("style", ""),
        " ".join(analysis.get("attributes", [])),
    ]
    description_text = " ".join(p for p in description_parts if p).strip()
    if not description_text:
        description_text = "product image"

    txt_vec = embedding_service.generate_text_embedding(description_text)
    query_vec = embedding_service.combine_embeddings(img_vec, txt_vec)

    raw_results = await index_service.search_similar(
        platform=request.platform,
        query_embedding=query_vec,
        limit=request.limit,
        min_similarity=request.min_similarity,
    )

    search_time_ms = round((time.monotonic() - start) * 1000)

    from config import settings
    results = [
        {
            "item_id": r["item_id"],
            "similarity_score": r["similarity_score"],
            "rank": idx + 1,
            "metadata": r["metadata"],
        }
        for idx, r in enumerate(raw_results)
    ]

    return VisionSearchResponse(
        status="success",
        data={
            "query_analysis": {
                "detected_category": analysis.get("category", ""),
                "detected_colors": analysis.get("colors", []),
                "detected_attributes": analysis.get("attributes", []),
                "detected_text": analysis.get("brand_text", ""),
                "confidence": analysis.get("confidence", 0.0),
            },
            "results": results,
            "total_found": len(results),
            "search_time_ms": search_time_ms,
            "provider_used": settings.VISION_PRIMARY_PROVIDER,
            "model_used": settings.VISION_PRIMARY_MODEL,
        },
    )


async def index_batch(request: IndexRequest, db) -> IndexResponse:
    from job_queue.job_queue import enqueue_job
    from database import AsyncSessionLocal

    if request.webhook_url:
        job_id = await enqueue_job(
            job_type="vision_index",
            payload=request.model_dump(),
            webhook_url=request.webhook_url,
            db=db,
        )
        return IndexResponse(
            status="queued",
            indexed_count=0,
            failed_count=0,
            job_id=job_id,
        )

    indexed = 0
    failed = 0

    for item in request.items:
        try:
            image_b64 = await vision_service.get_image_base64(item)

            from PIL import Image
            image_obj = embedding_service.image_from_base64(image_b64)
            img_vec = embedding_service.generate_image_embedding(image_obj)

            analysis = await vision_service.analyze_image(image_b64)
            description_parts = [
                analysis.get("category", ""),
                analysis.get("description", ""),
                " ".join(analysis.get("colors", [])),
                analysis.get("material", ""),
                analysis.get("brand_text", ""),
                analysis.get("style", ""),
                " ".join(analysis.get("attributes", [])),
            ]
            description_text = " ".join(p for p in description_parts if p).strip()
            if not description_text:
                description_text = "product image"

            txt_vec = embedding_service.generate_text_embedding(description_text)
            final_vec = embedding_service.combine_embeddings(img_vec, txt_vec)

            await index_service.index_single_item(
                platform=request.platform,
                item_id=item.item_id,
                embedding=final_vec,
                metadata=item.metadata,
                image_url=item.image_url,
                db=db,
            )
            indexed += 1
        except Exception:
            failed += 1

    return IndexResponse(
        status="success",
        indexed_count=indexed,
        failed_count=failed,
    )
