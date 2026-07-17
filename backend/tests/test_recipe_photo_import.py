"""POST /api/recipes/import-photo helpers (backend/app/routers/recipes.py) and
the vision model-chain override (backend/app/ai/client.py) — unit-tested
without any real OpenRouter call."""

from app.ai.client import _effective_chain
from app.ai.prompts import build_recipe_photo_prompt
from app.config import Settings
from app.routers.recipes import _sniff_image_mime

_JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
_WEBP_MAGIC = b"RIFF\x24\x00\x00\x00WEBPVP8 "


# ---------------------------------------------------------------------------
# _sniff_image_mime
# ---------------------------------------------------------------------------

class TestSniffImageMime:
    def test_detects_jpeg(self):
        assert _sniff_image_mime(_JPEG_MAGIC) == "image/jpeg"

    def test_detects_png(self):
        assert _sniff_image_mime(_PNG_MAGIC) == "image/png"

    def test_detects_webp(self):
        assert _sniff_image_mime(_WEBP_MAGIC) == "image/webp"

    def test_rejects_unknown_bytes(self):
        assert _sniff_image_mime(b"not an image, just text") is None

    def test_rejects_empty(self):
        assert _sniff_image_mime(b"") is None


# ---------------------------------------------------------------------------
# build_recipe_photo_prompt
# ---------------------------------------------------------------------------

class TestBuildRecipePhotoPrompt:
    def test_embeds_all_images_as_content_blocks(self):
        urls = ["data:image/jpeg;base64,AAA", "data:image/png;base64,BBB"]
        messages = build_recipe_photo_prompt(image_data_urls=urls)

        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        content = messages[1]["content"]
        assert content[0] == {"type": "text", "text": content[0]["text"]}
        image_blocks = [c for c in content if c["type"] == "image_url"]
        assert [b["image_url"]["url"] for b in image_blocks] == urls

    def test_single_image_text_differs_from_multi(self):
        one = build_recipe_photo_prompt(image_data_urls=["data:image/jpeg;base64,AAA"])
        two = build_recipe_photo_prompt(
            image_data_urls=["data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"]
        )
        assert one[1]["content"][0]["text"] != two[1]["content"][0]["text"]


# ---------------------------------------------------------------------------
# _effective_chain override (vision chain must not merge with the text chain)
# ---------------------------------------------------------------------------

class TestEffectiveChainOverride:
    def test_override_replaces_chain_entirely(self):
        settings = Settings(openrouter_api_key="x")
        vision_chain = settings.vision_model_chain
        result = _effective_chain(settings, override=vision_chain)
        assert result == vision_chain

    def test_no_override_falls_back_to_default_behavior(self):
        settings = Settings(openrouter_api_key="x")
        result = _effective_chain(settings)
        assert result[0] == settings.openrouter_default_model

    def test_vision_model_chain_has_three_free_models(self):
        settings = Settings(openrouter_api_key="x")
        chain = settings.vision_model_chain
        assert len(chain) == 3
        assert all(m.endswith(":free") for m in chain)
