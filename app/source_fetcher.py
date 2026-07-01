from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import settings
from app.review_models import (
    ExtractedSourceDocument,
    ReferenceEntry,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceRecord,
)
from app.source_adapters import SourcePayload


REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class SourceFetchOutcome:
    payload: SourcePayload | None = None
    failure_document: ExtractedSourceDocument | None = None
    http_status_code: int | None = None


@dataclass(frozen=True)
class RenderedPage:
    final_url: str
    html: str
    http_status_code: int | None = None


def fetch_exact_source(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
    canonical_url = (reference.canonical_url or "").strip()
    if not canonical_url:
        return SourceFetchOutcome(
            failure_document=_build_failed_source_document(
                reference=reference,
                source_id=source_id,
                reason="The selected reference does not expose a fetchable canonical URL.",
                warnings=["missing_canonical_url"],
            )
        )

    parsed = urlparse(canonical_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return SourceFetchOutcome(
            failure_document=_build_failed_source_document(
                reference=reference,
                source_id=source_id,
                reason="Only public HTTP/HTTPS cited sources can be fetched in this stage.",
                warnings=["unsupported_source_url"],
            )
        )

    try:
        current_url = _validate_public_url(canonical_url)
    except ValueError as exc:
        return SourceFetchOutcome(
            failure_document=_build_failed_source_document(
                reference=reference,
                source_id=source_id,
                reason=str(exc),
                warnings=["blocked_source_url"],
            )
        )

    transport = httpx.HTTPTransport(retries=1)
    with httpx.Client(
        follow_redirects=False,
        timeout=settings.source_fetch_timeout_seconds,
        transport=transport,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    ) as client:
        for _ in range(settings.source_fetch_max_redirects + 1):
            try:
                with client.stream("GET", current_url) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        redirect_target = response.headers.get("location")
                        if not redirect_target:
                            return SourceFetchOutcome(
                                failure_document=_build_failed_source_document(
                                    reference=reference,
                                    source_id=source_id,
                                    reason="The cited source redirected without a valid location.",
                                    warnings=["bad_source_redirect"],
                                )
                            )
                        current_url = _validate_public_url(
                            urljoin(current_url, redirect_target)
                        )
                        continue

                    response.raise_for_status()
                    body = _read_bounded_response(response)
                    content_type = _normalize_content_type(
                        response.headers.get("content-type")
                    )
                    detected_kind = _detect_source_kind(
                        final_url=str(response.url),
                        content_type=content_type,
                        fallback=reference.source_kind,
                    )
                    fetched_reference = reference.model_copy(
                        update={
                            "canonical_url": str(response.url),
                            "source_kind": detected_kind,
                        }
                    )
                    return SourceFetchOutcome(
                        payload=SourcePayload(
                            source_id=source_id,
                            reference=fetched_reference,
                            body=body,
                            content_type=content_type,
                        )
                    )
            except ValueError as exc:
                return SourceFetchOutcome(
                    failure_document=_build_failed_source_document(
                        reference=reference,
                        source_id=source_id,
                        reason=str(exc),
                        warnings=["blocked_source_url"],
                    )
                )
            except httpx.HTTPStatusError as exc:
                return SourceFetchOutcome(
                    failure_document=_build_failed_source_document(
                        reference=reference,
                        source_id=source_id,
                        reason=(
                            f"The cited source returned HTTP {exc.response.status_code} "
                            "during fetch."
                        ),
                        warnings=["source_fetch_failed"],
                    ),
                    http_status_code=exc.response.status_code,
                )
            except httpx.HTTPError as exc:
                warnings = ["source_fetch_failed"]
                if _is_timeout_like_fetch_error(exc):
                    warnings.append("source_fetch_timeout")
                return SourceFetchOutcome(
                    failure_document=_build_failed_source_document(
                        reference=reference,
                        source_id=source_id,
                        reason=f"The cited source could not be fetched: {exc}.",
                        warnings=warnings,
                    )
                )

    return SourceFetchOutcome(
        failure_document=_build_failed_source_document(
            reference=reference,
            source_id=source_id,
            reason="The cited source redirected too many times.",
            warnings=["too_many_redirects"],
        )
    )


def fetch_rendered_exact_source(
    reference: ReferenceEntry,
    source_id: str,
    *,
    renderer: Callable[[str], RenderedPage] | None = None,
) -> SourceFetchOutcome:
    canonical_url = (reference.canonical_url or "").strip()
    try:
        validated_url = _validate_public_url(canonical_url)
    except ValueError as exc:
        return SourceFetchOutcome(
            failure_document=_build_failed_source_document(
                reference=reference,
                source_id=source_id,
                reason=str(exc),
                warnings=["blocked_source_url"],
            )
        )

    try:
        rendered_page = (renderer or _render_with_browser)(validated_url)
        if (
            rendered_page.http_status_code is not None
            and rendered_page.http_status_code >= 400
        ):
            raise ValueError(
                f"The browser-rendered cited source returned HTTP "
                f"{rendered_page.http_status_code}."
            )
        final_url = _validate_public_url(rendered_page.final_url)
        body = rendered_page.html.encode("utf-8")
        if len(body) > settings.source_max_download_bytes:
            raise ValueError(
                "The browser-rendered cited source exceeded the download size limit."
            )
        rendered_reference = reference.model_copy(
            update={
                "canonical_url": final_url,
                "source_kind": SourceKind.HTML,
            }
        )
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=rendered_reference,
                body=body,
                content_type="text/html",
            ),
            http_status_code=rendered_page.http_status_code,
        )
    except (PlaywrightError, PlaywrightTimeoutError, OSError, ValueError) as exc:
        return SourceFetchOutcome(
            failure_document=_build_failed_source_document(
                reference=reference,
                source_id=source_id,
                reason=f"The cited source could not be rendered in an isolated browser: {exc}.",
                warnings=["browser_render_failed"],
            )
        )


def should_try_browser_fallback(
    reference: ReferenceEntry,
    fetch_outcome: SourceFetchOutcome,
) -> bool:
    if reference.source_kind != SourceKind.HTML:
        return False
    if fetch_outcome.http_status_code == 403:
        return True
    if fetch_outcome.failure_document is None:
        return False
    return "source_fetch_timeout" in fetch_outcome.failure_document.warnings


def _render_with_browser(url: str) -> RenderedPage:
    timeout_ms = int(settings.browser_render_timeout_seconds * 1000)
    validated_hosts: set[str] = set()

    with sync_playwright() as playwright:
        launch_kwargs: dict = {
            "headless": True,
            "args": [
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--no-first-run",
                "--disable-crash-reporter",
                "--disable-breakpad",
            ],
        }
        if settings.browser_executable_path:
            launch_kwargs["executable_path"] = settings.browser_executable_path

        browser = playwright.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(
                java_script_enabled=True,
                accept_downloads=False,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.0.0 Safari/537.36"
                ),
            )
            try:
                page = context.new_page()

                def handle_route(route) -> None:
                    request = route.request
                    if request.resource_type in {"image", "media", "font"}:
                        route.abort()
                        return
                    parsed = urlparse(request.url)
                    if parsed.scheme in {"data", "blob"}:
                        route.continue_()
                        return
                    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                        route.abort()
                        return
                    if parsed.hostname not in validated_hosts:
                        try:
                            _validate_public_url(request.url)
                        except ValueError:
                            route.abort()
                            return
                        validated_hosts.add(parsed.hostname)
                    route.continue_()

                page.route("**/*", handle_route)
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                main = page.locator("main")
                if main.count() == 1:
                    main.wait_for(state="attached", timeout=timeout_ms)
                    html = main.evaluate("element => element.outerHTML")
                else:
                    html = page.content()
                return RenderedPage(
                    final_url=page.url,
                    html=html,
                    http_status_code=response.status if response else None,
                )
            finally:
                context.close()
        finally:
            browser.close()


def _build_failed_source_document(
    *,
    reference: ReferenceEntry,
    source_id: str,
    reason: str,
    warnings: list[str],
) -> ExtractedSourceDocument:
    return ExtractedSourceDocument(
        source_record=SourceRecord(
            source_id=source_id,
            reference_id=reference.reference_id,
            source_kind=reference.source_kind,
            canonical_url=reference.canonical_url,
            fetch_status=SourceFetchStatus.FAILED,
            extraction_status=SourceExtractionStatus.PENDING,
            failure_reason=reason,
        ),
        blocks=[],
        warnings=warnings,
    )


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP/HTTPS cited sources can be fetched in this stage.")

    host = parsed.hostname
    if host.lower() == "localhost":
        raise ValueError("Loopback and private source addresses are blocked in this stage.")

    try:
        candidate_ip = ipaddress.ip_address(host)
        _assert_public_ip(candidate_ip)
        return url
    except ValueError:
        pass

    try:
        resolved = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValueError(f"The cited source hostname could not be resolved: {host}.") from exc

    for entry in resolved:
        sockaddr = entry[4]
        resolved_ip = ipaddress.ip_address(sockaddr[0])
        _assert_public_ip(resolved_ip)

    return url


def _assert_public_ip(candidate_ip: ipaddress._BaseAddress) -> None:
    if (
        candidate_ip.is_private
        or candidate_ip.is_loopback
        or candidate_ip.is_link_local
        or candidate_ip.is_multicast
        or candidate_ip.is_reserved
        or candidate_ip.is_unspecified
    ):
        raise ValueError("Loopback and private source addresses are blocked in this stage.")


def _read_bounded_response(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    for chunk in response.iter_bytes():
        total_size += len(chunk)
        if total_size > settings.source_max_download_bytes:
            raise ValueError("The cited source exceeded the download size limit for this stage.")
        chunks.append(chunk)
    return b"".join(chunks)


def _normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _detect_source_kind(
    *,
    final_url: str,
    content_type: str | None,
    fallback: SourceKind,
) -> SourceKind:
    if content_type == "application/pdf" or final_url.lower().endswith(".pdf"):
        return SourceKind.TEXT_PDF
    if content_type in {"text/html", "application/xhtml+xml"}:
        return SourceKind.HTML
    return fallback


def _is_timeout_like_fetch_error(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    return "timed out" in str(exc).lower()
