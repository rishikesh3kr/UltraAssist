import base64
import os
from io import BytesIO

from PIL import Image

try:
    import boto3
except ImportError: 
    boto3 = None

try:
    from botocore.config import Config
except ImportError: 
    Config = None


class ImageAnalyzer:
    def __init__(self):
        self.enabled = os.getenv("ENABLE_IMAGE_SEMANTICS", "true").lower() == "true"
        self.model_id = os.getenv(
            "BEDROCK_VISION_MODEL",
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        self.max_image_bytes = int(os.getenv("MAX_DOCX_IMAGE_BYTES", str(5 * 1024 * 1024)))
        self.max_summary_chars = int(os.getenv("MAX_IMAGE_SUMMARY_CHARS", "1200"))
        self.connect_timeout = int(os.getenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", "5"))
        self.read_timeout = int(os.getenv("BEDROCK_READ_TIMEOUT_SECONDS", "20"))
        self.client = None

        if self.enabled and boto3 is not None:
            region = (
                os.getenv("AWS_REGION_NAME")
                or os.getenv("AWS_DEFAULT_REGION")
                or "us-east-1"
            )
            client_kwargs = {"region_name": region}
            if Config is not None:
                client_kwargs["config"] = Config(
                    connect_timeout=self.connect_timeout,
                    read_timeout=self.read_timeout,
                    retries={"max_attempts": 1, "mode": "standard"},
                )
            self.client = boto3.client("bedrock-runtime", **client_kwargs)

    def encode_base32(self, image_bytes):
        return base64.b32encode(image_bytes).decode("ascii")

    def _detect_format(self, image_bytes):
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                image_format = (img.format or "PNG").upper()
                return "JPEG" if image_format == "JPG" else image_format
        except Exception:
            return "PNG"

    def _prepare_bedrock_image(self, image_bytes):
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                image_format = (img.format or "PNG").upper()
                normalized_format = "JPEG" if image_format == "JPG" else image_format
                if normalized_format in {"PNG", "JPEG", "GIF", "WEBP"}:
                    return image_bytes, normalized_format.lower()

                converted = BytesIO()
                if normalized_format == "GIF":
                    img = img.convert("P")
                else:
                    img = img.convert("RGBA") if img.mode not in {"RGB", "RGBA"} else img
                img.save(converted, format="PNG")
                return converted.getvalue(), "png"
        except Exception:
            try:
                with Image.open(BytesIO(image_bytes)) as img:
                    converted = BytesIO()
                    img.convert("RGBA").save(converted, format="PNG")
                    return converted.getvalue(), "png"
            except Exception:
                return b"", ""

    def summarize_image(self, image_bytes, file_name="", frs_id="", heading="", department=None, purpose=None):
        if not (department == "validation" and purpose == "script_authoring"):
            return {"summary": "", "status": "skipped_non_frs"}

        if not self.enabled or self.client is None:
            return {"summary": "", "status": "disabled"}

        if not image_bytes:
            return {"summary": "", "status": "empty_image"}

        if len(image_bytes) > self.max_image_bytes:
            return {"summary": "", "status": "image_too_large"}

        prepared_bytes, image_format = self._prepare_bedrock_image(image_bytes)

        if not prepared_bytes or image_format not in {"gif", "jpeg", "png", "webp"}:
            return {"summary": "", "status": "unsupported_image_format"}

        prompt = (
            "You are analyzing a diagram or image from a technical document.\n\n"
            f"File: {file_name or 'unknown'}\n"
            f"Context ID: {frs_id or 'N/A'}\n"
            f"Section: {heading or 'N/A'}\n\n"
            "Summarize only useful technical meaning.\n\n"
            "Return:\n"
            "Type:\n"
            "Key Elements:\n"
            "Flow/Process:\n"
            "Important Notes:\n"
            "If not meaningful, say: 'No relevant technical content'."
        )

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"text": prompt},
                            {
                                "image": {
                                    "format": image_format,
                                    "source": {"bytes": prepared_bytes},
                                }
                            },
                        ],
                    }
                ],
                inferenceConfig={"maxTokens": 600, "temperature": 0.1},
            )

            content = response.get("output", {}).get("message", {}).get("content", [])
            parts = [item.get("text", "") for item in content if item.get("text")]

            summary = "\n".join(parts).strip()[: self.max_summary_chars]

            return {
                "summary": summary,
                "status": "complete" if summary else "empty_summary",
            }

        except Exception as exc:
            print(f"[UltraAssist RAG - image_analyzer.summarize_image] Failed to summarize image: {exc}")
            return {"summary": "", "status": "error", "error": str(exc)}