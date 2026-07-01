from app.config import settings


def test_default_model_placeholder_is_the_cheapest_requested_option() -> None:
    assert settings.default_gemini_model == "gemini-flash-lite-latest"
