from clockcross.config import Settings


def test_llm_defaults_to_verified_clockcross_gateway_but_no_credentials():
    settings = Settings(alpaca_api_key="x", alpaca_secret_key="y")
    assert str(settings.llm_base_url).rstrip("/") == (
        "https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1"
    )
    assert settings.llm_api_key is None
    assert settings.llm_model == "clockcross-cloudflare-llama-3.3-70b"


def test_llm_provider_can_be_overridden_without_changing_trading_code():
    settings = Settings(
        alpaca_api_key="x",
        alpaca_secret_key="y",
        llm_base_url="https://example.invalid/v1",
        llm_api_key="provider-key",
        llm_model="provider/model",
    )
    assert str(settings.llm_base_url).rstrip("/") == "https://example.invalid/v1"
    assert settings.llm_api_key == "provider-key"
    assert settings.llm_model == "provider/model"
