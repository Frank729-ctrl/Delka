import httpx
from services.providers.vision_base_provider import VisionBaseProvider

_ANALYSIS_PROMPT = """Analyze this image and return ONLY a JSON object with these exact fields:
{
  "category": "main product category",
  "colors": ["color1", "color2"],
  "material": "primary material",
  "shape": "shape description",
  "brand_text": "any visible text or brand",
  "style": "style descriptor",
  "attributes": ["attribute1", "attribute2"],
  "description": "one sentence summary",
  "confidence": 0.95
}
No markdown. No explanation. JSON only."""


class VisionOllamaProvider(VisionBaseProvider):

    def is_available(self) -> bool:
        from config import settings
        return bool(settings.OLLAMA_BASE_URL)

    def is_rate_limit_error(self, error: Exception) -> bool:
        return False

    async def analyze_image(self, image_base64: str, model: str) -> dict:
        from config import settings

        url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": model,
            "prompt": _ANALYSIS_PROMPT,
            "images": [image_base64],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "")
            return self._parse_json_response(raw)
