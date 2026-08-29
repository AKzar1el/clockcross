from clockcross.config import Settings


def test_llm_defaults_to_featherless_compatible_endpoint_but_no_credentials():
    settings = Settings(alpaca_api_key="x", alpaca_secret_key="y")
    assert str(settings.llm_base_url).rstrip("/") == "https://api.featherless.ai/v1"
    assert settings.llm_api_key is None
    assert settings.llm_model is None


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
