import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


DEFAULT_EVIDENCE_MODEL = "gemini-flash-lite-latest"
DEFAULT_SECTION_ANALYSIS_MODEL = "gemini-2.5-flash"
DEFAULT_FINAL_COHERENCE_MODEL = "gemini-2.5-flash"


load_dotenv(
    dotenv_path=Path(__file__).resolve().parent.parent / ".env",
    override=True,
)


def _default_browser_executable() -> str | None:
    configured = os.getenv("BRV_BROWSER_EXECUTABLE")
    if configured:
        return configured
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


class Settings(BaseModel):
    app_name: str = "brv-capstone"
    docx_max_upload_bytes: int = 20 * 1024 * 1024
    default_gemini_model: str = Field(
        default_factory=lambda: os.getenv(
            "BRV_GEMINI_MODEL",
            DEFAULT_EVIDENCE_MODEL,
        )
    )
    section_analysis_model: str = Field(
        default_factory=lambda: os.getenv(
            "BRV_SECTION_ANALYSIS_MODEL",
            DEFAULT_SECTION_ANALYSIS_MODEL,
        )
    )
    final_coherence_model: str = Field(
        default_factory=lambda: os.getenv(
            "BRV_FINAL_COHERENCE_MODEL",
            DEFAULT_FINAL_COHERENCE_MODEL,
        )
    )
    google_api_key: str | None = Field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY") or None
    )
    google_genai_use_vertexai: bool = Field(
        default_factory=lambda: os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower()
        in {"1", "true", "yes", "on"}
    )
    google_cloud_project: str | None = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT") or None
    )
    google_cloud_location: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    )
    source_fetch_timeout_seconds: float = Field(
        default_factory=lambda: float(
            os.getenv("BRV_SOURCE_FETCH_TIMEOUT_SECONDS", "12")
        )
    )
    source_max_download_bytes: int = Field(
        default_factory=lambda: int(
            os.getenv("BRV_SOURCE_MAX_DOWNLOAD_BYTES", str(4 * 1024 * 1024))
        )
    )
    source_fetch_max_redirects: int = Field(
        default_factory=lambda: int(os.getenv("BRV_SOURCE_FETCH_MAX_REDIRECTS", "3"))
    )
    browser_render_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "BRV_BROWSER_RENDER_ENABLED", "true"
        ).lower()
        in {"1", "true", "yes", "on"}
    )
    browser_executable_path: str | None = Field(
        default_factory=_default_browser_executable
    )
    browser_render_timeout_seconds: float = Field(
        default_factory=lambda: float(
            os.getenv("BRV_BROWSER_RENDER_TIMEOUT_SECONDS", "20")
        )
    )
    section_max_words: int = Field(
        default_factory=lambda: int(os.getenv("BRV_SECTION_MAX_WORDS", "800"))
    )
    section_subchunk_max_words: int = Field(
        default_factory=lambda: int(
            os.getenv("BRV_SECTION_SUBCHUNK_MAX_WORDS", "250")
        )
    )
    section_max_concurrent_workers: int = Field(
        default_factory=lambda: int(
            os.getenv("BRV_SECTION_MAX_CONCURRENT_WORKERS", "5")
        )
    )

    def gemini_config_ready(self) -> bool:
        if self.google_genai_use_vertexai:
            return bool(self.google_cloud_project)
        return bool(self.google_api_key and not self.google_api_key.startswith("PASTE_"))


settings = Settings()
