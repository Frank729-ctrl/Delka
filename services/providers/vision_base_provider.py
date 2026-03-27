from abc import ABC, abstractmethod


class VisionBaseProvider(ABC):

    @abstractmethod
    async def analyze_image(self, image_base64: str, model: str) -> dict:
        """
        Analyze image and return structured description dict with keys:
        category, colors, material, shape, brand_text, style,
        attributes, description, confidence.
        """

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def is_rate_limit_error(self, error: Exception) -> bool: ...

    def _fallback_analysis(self) -> dict:
        return {
            "category": "Unknown",
            "colors": [],
            "material": "",
            "shape": "",
            "brand_text": "",
            "style": "",
            "attributes": [],
            "description": "Image analysis unavailable",
            "confidence": 0.0,
        }

    def _parse_json_response(self, raw: str) -> dict:
        import json
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            result = json.loads(text)
            # Normalize field names
            return {
                "category": result.get("category", "Unknown"),
                "colors": result.get("colors", []),
                "material": result.get("material", ""),
                "shape": result.get("shape", ""),
                "brand_text": result.get("brand_text", ""),
                "style": result.get("style", ""),
                "attributes": result.get("attributes", []),
                "description": result.get("description", ""),
                "confidence": float(result.get("confidence", 0.5)),
            }
        except (json.JSONDecodeError, ValueError):
            return self._fallback_analysis()
