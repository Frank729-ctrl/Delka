"""
Image generation service — uses NVIDIA Stable Diffusion XL via NIM.
Returns base64-encoded PNG.
"""
import base64
import httpx
from config import settings


async def generate_image(
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    seed: int = -1,
) -> tuple[bytes, str, int]:
    """
    Returns (image_bytes, provider_name, seed_used).
    """
    if not settings.NVIDIA_API_KEY:
        return b"", "unavailable", seed

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            payload = {
                "model": settings.NVIDIA_IMAGE_GEN_MODEL,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "num_inference_steps": steps,
                "guidance_scale": 7.5,
                "sampler": "DDIM",
                "output_format": "b64_json",
            }
            if seed >= 0:
                payload["seed"] = seed

            response = await client.post(
                f"{settings.NVIDIA_BASE_URL}/images/generations",
                headers={
                    "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            b64 = data["data"][0].get("b64_json", "")
            used_seed = data["data"][0].get("seed", seed)
            image_bytes = base64.b64decode(b64) if b64 else b""
            return image_bytes, "nvidia", used_seed
    except Exception:
        return b"", "unavailable", seed
