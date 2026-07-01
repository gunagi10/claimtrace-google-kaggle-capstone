from app.review_models import SourceFetchStatus, SourceKind
from app.source_fetcher import RenderedPage, fetch_exact_source, fetch_rendered_exact_source
import app.source_fetcher as source_fetcher
from app.review_models import ReferenceEntry


def test_fetch_exact_source_returns_failed_document_when_reference_has_no_url() -> None:
    outcome = fetch_exact_source(
        ReferenceEntry(
            reference_id="reference-1",
            citation_label="1",
            raw_bibliography_text="Internal appendix",
            canonical_url=None,
            source_kind=SourceKind.HTML,
        ),
        "source-1",
    )

    assert outcome.payload is None
    assert outcome.failure_document is not None
    assert outcome.failure_document.source_record.fetch_status == SourceFetchStatus.FAILED
    assert "missing_canonical_url" in outcome.failure_document.warnings


def test_fetch_exact_source_blocks_loopback_hosts() -> None:
    outcome = fetch_exact_source(
        ReferenceEntry(
            reference_id="reference-1",
            citation_label="1",
            raw_bibliography_text="http://127.0.0.1/report",
            canonical_url="http://127.0.0.1/report",
            source_kind=SourceKind.HTML,
        ),
        "source-1",
    )

    assert outcome.payload is None
    assert outcome.failure_document is not None
    assert outcome.failure_document.source_record.fetch_status == SourceFetchStatus.FAILED
    assert "blocked_source_url" in outcome.failure_document.warnings


def test_browser_rendered_fetch_returns_bounded_html_payload(monkeypatch) -> None:
    monkeypatch.setattr(source_fetcher, "_validate_public_url", lambda url: url)
    reference = ReferenceEntry(
        reference_id="reference-1",
        citation_label="1",
        raw_bibliography_text="https://example.com/report",
        canonical_url="https://example.com/report",
        source_kind=SourceKind.HTML,
    )

    outcome = fetch_rendered_exact_source(
        reference,
        "source-1",
        renderer=lambda url: RenderedPage(
            final_url=url,
            html="<main><p>Revenue was $70.1 billion.</p></main>",
            http_status_code=200,
        ),
    )

    assert outcome.failure_document is None
    assert outcome.payload is not None
    assert outcome.payload.content_type == "text/html"
    assert b"Revenue was $70.1 billion" in outcome.payload.body


def test_browser_rendered_fetch_rejects_http_error_page(monkeypatch) -> None:
    monkeypatch.setattr(source_fetcher, "_validate_public_url", lambda url: url)
    reference = ReferenceEntry(
        reference_id="reference-1",
        citation_label="1",
        raw_bibliography_text="https://example.com/report",
        canonical_url="https://example.com/report",
        source_kind=SourceKind.HTML,
    )

    outcome = fetch_rendered_exact_source(
        reference,
        "source-1",
        renderer=lambda url: RenderedPage(
            final_url=url,
            html="<main><p>Access denied</p></main>",
            http_status_code=403,
        ),
    )

    assert outcome.payload is None
    assert outcome.failure_document is not None
    assert "browser_render_failed" in outcome.failure_document.warnings
