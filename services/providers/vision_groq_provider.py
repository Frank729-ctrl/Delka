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


class VisionGroqProvider(VisionBaseProvider):

    def is_available(self) -> bool:
        from config import settings
        return bool(settings.GROQ_API_KEY)

    def is_rate_limit_error(self, error: Exception) -> bool:
        try:
            import groq
            if isinstance(error, groq.RateLimitError):
                return True
        except ImportError:
            pass
        return "429" in str(error)

    async def analyze_image(self, image_base64: str, model: str) -> dict:
        from config import settings
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": _ANALYSIS_PROMPT,
                            },
                        ],
                    }
                ],
                max_tokens=500,
                temperature=0.1,
            )
            raw = response.choices[0].message.content
            return self._parse_json_response(raw)
        except Exception:
            raise
