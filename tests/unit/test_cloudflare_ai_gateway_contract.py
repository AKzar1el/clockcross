from pathlib import Path

GATEWAY = Path("deploy/cloudflare-ai-gateway/src/index.js")
WRANGLER = Path("deploy/cloudflare-ai-gateway/wrangler.jsonc")


def test_gateway_is_authenticated_fixed_model_and_schema_bounded():
    source = GATEWAY.read_text()

    assert "CLOCKCROSS_AI_AUTH" in source
    assert "Authorization" in source
    assert '"/v1/chat/completions"' in source
    assert "@cf/meta/llama-3.3-70b-instruct-fp8-fast" in source
    assert "response_format" in source
    assert "json_schema" in source
    for field in (
        "action",
        "confidence",
        "idiosyncratic_news_detected",
        "driver",
        "reason",
    ):
        assert field in source

    assert "body.model" not in source
    assert "env.AI.run(body" not in source
    assert "CLOCKCROSS_AI_AUTH:" not in source


def test_gateway_caps_input_and_output_and_returns_openai_shape():
    source = GATEWAY.read_text()

    assert "MAX_INPUT_CHARS" in source
    assert "max_tokens: 220" in source
    assert 'object: "chat.completion"' in source
    assert 'role: "assistant"' in source
    assert "choices:" in source


def test_wrangler_config_declares_only_ai_binding_and_no_secret_literal():
    config = WRANGLER.read_text()

    assert '"name": "clockcross-ai-gateway"' in config
    assert '"binding": "AI"' in config
    assert "CLOCKCROSS_AI_AUTH" not in config
    assert "api_token" not in config.lower()
