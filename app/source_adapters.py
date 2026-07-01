from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO

from pypdf import PdfReader

from app.review_models import (
    ExtractedSourceDocument,
    ReferenceEntry,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceLocator,
    SourceRecord,
    SourceTextBlock,
)


class SourceAdapterError(ValueError):
    """Raised when a source cannot be extracted by the selected adapter."""


@dataclass(frozen=True)
class SourcePayload:
    source_id: str
    reference: ReferenceEntry
    body: bytes
    content_type: str | None = None


class SourceAdapter(ABC):
    source_kind: SourceKind

    @abstractmethod
    def extract(self, payload: SourcePayload) -> ExtractedSourceDocument:
        """Return normalized source text blocks for the payload."""


class HtmlSourceAdapter(SourceAdapter):
    source_kind = SourceKind.HTML

    def extract(self, payload: SourcePayload) -> ExtractedSourceDocument:
        html_text = payload.body.decode("utf-8", errors="ignore")
        parser = _HtmlBlockParser()
        parser.feed(html_text)
        parser.close()

        parsed_blocks = (
            [block for block in parser.blocks if block.in_main]
            if parser.saw_main
            else parser.blocks
        )
        blocks: list[SourceTextBlock] = []
        for index, block in enumerate(parsed_blocks, start=1):
            cleaned = _normalize_whitespace(block.text)
            if not cleaned:
                continue
            blocks.append(
                SourceTextBlock(
                    block_id=f"{payload.source_id}-block-{index}",
                    source_id=payload.source_id,
                    text=cleaned,
                    locator=SourceLocator(
                        heading=block.heading,
                        text_span_label=f"html-block-{index}",
                    ),
                )
            )

        source_record = SourceRecord(
            source_id=payload.source_id,
            reference_id=payload.reference.reference_id,
            source_kind=payload.reference.source_kind,
            canonical_url=payload.reference.canonical_url,
            fetch_status=SourceFetchStatus.FETCHED,
            extraction_status=(
                SourceExtractionStatus.EXTRACTED
                if blocks
                else SourceExtractionStatus.EXTRACTION_FAILED
            ),
            failure_reason=None
            if blocks
            else "No readable text blocks were found in the HTML source.",
        )

        return ExtractedSourceDocument(
            source_record=source_record,
            blocks=blocks,
            warnings=[] if blocks else ["empty_html_text"],
        )


class TextPdfSourceAdapter(SourceAdapter):
    source_kind = SourceKind.TEXT_PDF

    def extract(self, payload: SourcePayload) -> ExtractedSourceDocument:
        try:
            reader = PdfReader(BytesIO(payload.body))
        except Exception as exc:  # pragma: no cover - library error surface
            raise SourceAdapterError("The PDF could not be parsed.") from exc

        blocks: list[SourceTextBlock] = []
        carried_table_context: tuple[str | None, str | None] | None = None
        table_index = 0

        for page_number, page in enumerate(reader.pages, start=1):
            extracted_text = page.extract_text() or ""
            if not _normalize_whitespace(extracted_text):
                continue

            layout_text = self._extract_layout_text(page)
            table_blocks, carried_table_context = self._extract_table_like_blocks(
                layout_text=layout_text,
                source_id=payload.source_id,
                page_number=page_number,
                table_index_start=table_index,
                carried_context=carried_table_context,
            )
            table_index += len(table_blocks)

            prose_text = self._extract_pdf_prose_text(extracted_text)
            if prose_text:
                blocks.append(
                    SourceTextBlock(
                        block_id=f"{payload.source_id}-page-{page_number}",
                        source_id=payload.source_id,
                        text=prose_text,
                        locator=SourceLocator(
                            page_number=page_number,
                            text_span_label=f"page-{page_number}",
                        ),
                    )
                )

            blocks.extend(table_blocks)

        extraction_status = (
            SourceExtractionStatus.EXTRACTED
            if blocks
            else SourceExtractionStatus.OCR_REQUIRED
        )
        failure_reason = (
            None
            if blocks
            else "The PDF does not expose a usable text layer in this stage."
        )

        return ExtractedSourceDocument(
            source_record=SourceRecord(
                source_id=payload.source_id,
                reference_id=payload.reference.reference_id,
                source_kind=payload.reference.source_kind,
                canonical_url=payload.reference.canonical_url,
                fetch_status=SourceFetchStatus.FETCHED,
                extraction_status=extraction_status,
                failure_reason=failure_reason,
            ),
            blocks=blocks,
            warnings=[] if blocks else ["ocr_required"],
        )

    def _extract_layout_text(self, page) -> str:
        """Use pypdf's layout mode only as a conservative table-reading aid.

        Standard extraction remains the prose source because it usually reads
        sentences more naturally. Layout mode preserves horizontal spacing well
        enough to isolate many financial-table rows, but can make prose noisy.
        Older pypdf versions may not support this mode, so it is optional.
        """

        try:
            return page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError):
            return ""

    def _extract_pdf_prose_text(self, extracted_text: str) -> str:
        """Keep ordinary PDF prose while dropping dense lines duplicated as table rows."""

        kept_lines: list[str] = []
        for raw_line in extracted_text.splitlines():
            line = _normalize_whitespace(raw_line)
            if not line or self._is_pdf_page_chrome(line):
                continue
            if self._is_dense_pdf_table_line(line):
                continue
            kept_lines.append(line)
        return _normalize_whitespace(" ".join(kept_lines))

    def _extract_table_like_blocks(
        self,
        *,
        layout_text: str,
        source_id: str,
        page_number: int,
        table_index_start: int,
        carried_context: tuple[str | None, str | None] | None,
    ) -> tuple[list[SourceTextBlock], tuple[str | None, str | None] | None]:
        """Create row-level evidence only when layout extraction shows a real table.

        The method deliberately does not assign a specific number to a specific
        header column. It preserves the original row order and supplies nearby
        table/header context, which is useful for retrieval without pretending to
        have reconstructed an arbitrary PDF table perfectly.
        """

        if not layout_text:
            return [], carried_context

        lines = [line.rstrip() for line in layout_text.splitlines()]
        carried_title, carried_headers = carried_context or (None, "")
        active_title: str | None = None
        header_parts: list[str] = []
        candidates = [self._is_pdf_table_row_candidate(line) for line in lines]
        blocks: list[SourceTextBlock] = []
        active_table_number = table_index_start
        last_context_line_index: int | None = None
        last_row_line_index: int | None = None

        for index, raw_line in enumerate(lines):
            line = _normalize_whitespace(raw_line)
            if not line or self._is_pdf_page_chrome(line):
                continue

            if self._is_pdf_table_title(line):
                active_title = line
                header_parts = []
                last_context_line_index = index
                continue

            if self._is_pdf_table_header(line):
                header_parts.append(line)
                header_parts = header_parts[-3:]
                last_context_line_index = index
                continue

            if self._is_pdf_table_section_label(line) and active_title:
                header_parts = [line]
                last_context_line_index = index
                continue

            if not candidates[index]:
                continue

            nearby_rows = sum(
                candidates[neighbor]
                for neighbor in range(max(0, index - 3), min(len(lines), index + 4))
            )
            has_current_context = bool(active_title and header_parts)
            numeric_count = self._pdf_numeric_token_count(line)
            can_use_carried_context = bool(
                carried_title
                and carried_headers
                and index <= 10
                and numeric_count >= 3
            )
            if nearby_rows < 3 and not has_current_context and not can_use_carried_context:
                continue
            if len(blocks) >= 48:
                break

            if not has_current_context and can_use_carried_context:
                active_title = carried_title
                header_parts = [part for part in carried_headers.split(" | ") if part]

            header_context = " | ".join(header_parts)
            parts: list[str] = []
            if active_title:
                parts.append(f"Table: {active_title}.")
            if header_context:
                parts.append(f"Headers: {header_context}.")
            parts.append(f"Row: {line}.")

            active_table_number += 1
            blocks.append(
                SourceTextBlock(
                    block_id=(
                        f"{source_id}-page-{page_number}-"
                        f"table-{active_table_number}-row-{len(blocks) + 1}"
                    ),
                    source_id=source_id,
                    text=" ".join(parts),
                    locator=SourceLocator(
                        heading=active_title,
                        page_number=page_number,
                        text_span_label=(
                            f"page-{page_number}-table-{active_table_number}-"
                            f"row-{len(blocks) + 1}"
                        ),
                    ),
                )
            )
            last_row_line_index = index

        next_context = (
            (active_title, " | ".join(header_parts))
            if active_title
            and header_parts
            and last_context_line_index is not None
            and last_context_line_index >= max(0, len(lines) - 12)
            and (
                last_row_line_index is None
                or last_context_line_index > last_row_line_index
            )
            else None
        )
        return blocks, next_context

    def _is_pdf_page_chrome(self, line: str) -> bool:
        lowered = line.lower()
        return bool(
            re.match(r"^\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}\s+(?:am|pm)\b", lowered)
            or lowered.startswith(("http://", "https://", "www."))
            or re.search(r"\b(?:page\s+)?\d+\s*/\s*\d+\s*$", lowered)
            or lowered == "view all news"
            or lowered.startswith("investors news events")
        )

    def _is_dense_pdf_table_line(self, line: str) -> bool:
        return self._pdf_numeric_token_count(line) >= 6 and not re.search(
            r"[.!?][\"'”)]?$", line
        )

    def _is_pdf_table_title(self, line: str) -> bool:
        letters = re.findall(r"[A-Za-z]", line)
        if len(letters) < 6 or len(line) > 140:
            return False

        uppercase_ratio = sum(letter.isupper() for letter in letters) / len(letters)
        normalized = line.lower()
        return bool(
            uppercase_ratio >= 0.75
            or re.search(
                r"\b(?:summary|statements? of|balance sheets?|cash flows?|"
                r"reconciliation|outlook|schedule)\b",
                normalized,
            )
        )

    def _is_pdf_table_header(self, line: str) -> bool:
        normalized = line.lower()
        if "in millions" in normalized or "in thousands" in normalized:
            return True
        if re.search(r"\b(?:q[1-4]\s*fy\d{2,4}|q/q|y/y|three months ended|six months ended|nine months ended|year ended)\b", normalized):
            return True

        month_names = (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        )
        month_count = sum(
            len(re.findall(rf"\b{month}\b", normalized))
            for month in month_names
        )
        return month_count >= 2

    def _is_pdf_table_section_label(self, line: str) -> bool:
        return line.strip().lower() in {"gaap", "non-gaap", "unaudited"}

    def _pdf_numeric_token_count(self, line: str) -> int:
        return len(
            re.findall(
                r"(?<![A-Za-z0-9])\(?-?\$?\s*\d[\d,]*(?:\.\d+)?"
                r"(?:%|\s+(?:pts?|points?))?(?![A-Za-z])",
                line,
            )
        )

    def _is_pdf_table_row_candidate(self, raw_line: str) -> bool:
        line = raw_line.strip()
        if not line or self._is_pdf_page_chrome(_normalize_whitespace(line)):
            return False
        if not re.search(r"\s{3,}", raw_line):
            return False
        if not re.match(r"[A-Za-z(]", line):
            return False
        if self._pdf_numeric_token_count(line) < 1:
            return False

        return not re.search(r"[.!?][\"'”)]?$", line)

def build_source_adapter(source_kind: SourceKind) -> SourceAdapter:
    if source_kind == SourceKind.HTML:
        return HtmlSourceAdapter()
    if source_kind == SourceKind.TEXT_PDF:
        return TextPdfSourceAdapter()
    raise SourceAdapterError(f"Unsupported source kind: {source_kind}")


class _HtmlBlock:
    def __init__(self, text: str, heading: str | None, *, in_main: bool) -> None:
        self.text = text
        self.heading = heading
        self.in_main = in_main


@dataclass
class _HtmlCaptureFrame:
    """One heading or candidate prose container currently open in the DOM."""

    tag: str
    in_main: bool
    is_heading: bool = False
    is_generic_container: bool = False
    text_parts: list[str] = field(default_factory=list)
    has_nested_content_container: bool = False


@dataclass
class _HtmlTableCell:
    is_header: bool
    colspan: int = 1
    rowspan: int = 1
    text: str = ""
    text_parts: list[str] = field(default_factory=list)


@dataclass
class _HtmlTableRow:
    cells: list[_HtmlTableCell] = field(default_factory=list)
    section: str | None = None


@dataclass
class _HtmlTableFrame:
    in_main: bool
    heading: str | None
    caption_parts: list[str] = field(default_factory=list)
    rows: list[_HtmlTableRow] = field(default_factory=list)
    current_row: _HtmlTableRow | None = None
    current_cell: _HtmlTableCell | None = None
    in_caption: bool = False
    section_stack: list[str] = field(default_factory=list)


class _HtmlBlockParser(HTMLParser):
    """Extract ordered, heading-aware prose blocks from ordinary HTML.

    The parser still favors semantic text tags such as ``p`` and ``li``. It also
    captures *leaf-like* ``div``/``section``/``article`` containers when modern
    sites place visible prose there instead of inside paragraphs. Parent layout
    wrappers are not emitted when they contain a more specific child container,
    which prevents whole-page duplicates.
    """

    _BLOCK_TAGS = {"p", "li", "blockquote", "figcaption", "pre"}
    _GENERIC_TEXT_TAGS = {"div", "section", "article", "dd"}
    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _SKIP_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "template",
        "canvas",
        "iframe",
        "object",
        "embed",
        "button",
        "input",
        "select",
        "textarea",
        "option",
    }
    _VOID_SKIP_TAGS = {"embed", "input"}
    _EXCLUDED_REGIONS = {"nav", "footer", "aside"}
    _EXCLUDED_ROLES = {
        "alertdialog",
        "banner",
        "complementary",
        "contentinfo",
        "dialog",
        "menu",
        "menubar",
        "navigation",
        "search",
        "tablist",
        "toolbar",
    }
    _TABLE_SECTION_TAGS = {"thead", "tbody", "tfoot"}
    _MAX_TABLE_ROWS = 40

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[_HtmlBlock] = []
        self._active_heading: str | None = None
        self._capture_stack: list[_HtmlCaptureFrame] = []
        self._skip_depth = 0
        self._excluded_depth = 0
        self._excluded_tag_stack: list[str] = []
        self._main_depth = 0
        self.saw_main = False
        self._table_stack: list[_HtmlTableFrame] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            # Void tags such as <input> do not emit matching end tags in
            # ordinary HTML, so they must not leave skip mode stuck for the
            # rest of the page.
            if tag not in self._VOID_SKIP_TAGS:
                self._skip_depth += 1
            return

        if tag in self._EXCLUDED_REGIONS or self._has_excluded_role(attrs):
            self._excluded_depth += 1
            self._excluded_tag_stack.append(tag)
            return

        if tag == "main":
            self.saw_main = True
            self._main_depth += 1

        if self._skip_depth or self._excluded_depth:
            return

        if self._table_stack:
            self._handle_table_starttag(tag, attrs)
            return

        if tag == "table":
            self._table_stack.append(
                _HtmlTableFrame(
                    in_main=self._main_depth > 0,
                    heading=self._active_heading,
                )
            )
            return

        is_heading = tag in self._HEADING_TAGS
        is_block = tag in self._BLOCK_TAGS
        is_generic = tag in self._GENERIC_TEXT_TAGS
        if not (is_heading or is_block or is_generic):
            return

        if not is_heading and self._capture_stack:
            self._capture_stack[-1].has_nested_content_container = True

        self._capture_stack.append(
            _HtmlCaptureFrame(
                tag=tag,
                in_main=self._main_depth > 0,
                is_heading=is_heading,
                is_generic_container=is_generic,
            )
        )

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return

        if (
            self._excluded_tag_stack
            and self._excluded_tag_stack[-1] == tag
            and self._excluded_depth
        ):
            self._excluded_tag_stack.pop()
            self._excluded_depth -= 1
            return

        if self._skip_depth or self._excluded_depth:
            return

        if self._table_stack:
            if self._handle_table_endtag(tag):
                return

        if self._capture_stack and self._capture_stack[-1].tag == tag:
            self._emit_frame(self._capture_stack.pop())

        if tag == "main" and self._main_depth:
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._excluded_depth:
            return
        if self._table_stack:
            table = self._table_stack[-1]
            if table.current_cell is not None:
                table.current_cell.text_parts.append(data)
            elif table.in_caption:
                table.caption_parts.append(data)
            return
        if not self._capture_stack:
            return
        self._capture_stack[-1].text_parts.append(data)

    def close(self) -> None:
        while self._table_stack:
            self._emit_table(self._table_stack.pop())
        while self._capture_stack:
            self._emit_frame(self._capture_stack.pop())
        super().close()

    def _emit_frame(self, frame: _HtmlCaptureFrame) -> None:
        text = _normalize_whitespace("".join(frame.text_parts))
        if not text:
            return

        if frame.is_heading:
            self._active_heading = text
            return

        if frame.is_generic_container and not self._should_emit_generic_container(
            frame, text
        ):
            return

        self.blocks.append(
            _HtmlBlock(
                text=text,
                heading=self._active_heading,
                in_main=frame.in_main,
            )
        )

    def _handle_table_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        table = self._table_stack[-1]
        if tag in self._TABLE_SECTION_TAGS:
            table.section_stack.append(tag)
            return
        if tag == "caption":
            table.in_caption = True
            return
        if tag == "tr":
            table.current_row = _HtmlTableRow(
                section=table.section_stack[-1] if table.section_stack else None
            )
            return
        if tag in {"td", "th"} and table.current_row is not None:
            table.current_cell = _HtmlTableCell(
                is_header=(tag == "th"),
                colspan=self._parse_table_span(attrs, "colspan"),
                rowspan=self._parse_table_span(attrs, "rowspan"),
            )

    def _handle_table_endtag(self, tag: str) -> bool:
        table = self._table_stack[-1]
        if tag in self._TABLE_SECTION_TAGS:
            if table.section_stack and table.section_stack[-1] == tag:
                table.section_stack.pop()
            return True
        if tag == "caption":
            table.in_caption = False
            return True
        if tag in {"td", "th"}:
            self._finish_table_cell(table)
            return True
        if tag == "tr":
            self._finish_table_row(table)
            return True
        if tag == "table":
            self._emit_table(self._table_stack.pop())
            return True
        return True

    def _finish_table_cell(self, table: _HtmlTableFrame) -> None:
        if table.current_row is None or table.current_cell is None:
            return
        table.current_cell.text = _normalize_whitespace(
            "".join(table.current_cell.text_parts)
        )
        table.current_row.cells.append(table.current_cell)
        table.current_cell = None

    def _finish_table_row(self, table: _HtmlTableFrame) -> None:
        if table.current_row is None:
            return
        if any(cell.text for cell in table.current_row.cells):
            table.rows.append(table.current_row)
        table.current_row = None
        table.current_cell = None

    def _emit_table(self, table: _HtmlTableFrame) -> None:
        caption = _normalize_whitespace("".join(table.caption_parts))
        for row_text in self._build_table_row_texts(table.rows, caption):
            self.blocks.append(
                _HtmlBlock(
                    text=row_text,
                    heading=table.heading,
                    in_main=table.in_main,
                )
            )

    def _build_table_row_texts(
        self,
        rows: list[_HtmlTableRow],
        caption: str,
    ) -> list[str]:
        if not rows:
            return []

        header_rows, body_rows = self._split_table_rows(rows)
        header_labels = self._build_column_headers(header_rows)

        emitted: list[str] = []
        for row in body_rows:
            row_text = self._linearize_table_row(row, header_labels, caption)
            if row_text:
                emitted.append(row_text)
            if len(emitted) >= self._MAX_TABLE_ROWS:
                break
        return emitted

    def _split_table_rows(
        self,
        rows: list[_HtmlTableRow],
    ) -> tuple[list[_HtmlTableRow], list[_HtmlTableRow]]:
        explicit_header_rows = [row for row in rows if row.section == "thead"]
        if explicit_header_rows:
            return explicit_header_rows, [row for row in rows if row.section != "thead"]

        header_rows: list[_HtmlTableRow] = []
        body_start = 0
        for index, row in enumerate(rows):
            if row.cells and all(cell.is_header for cell in row.cells):
                header_rows.append(row)
                body_start = index + 1
                continue
            break
        return header_rows, rows[body_start:]

    def _build_column_headers(self, header_rows: list[_HtmlTableRow]) -> list[str | None]:
        if not header_rows:
            return []

        grid = self._build_logical_table_grid(header_rows)
        header_columns: list[list[str]] = []
        for row_values in grid:
            for index, value in enumerate(row_values):
                while len(header_columns) <= index:
                    header_columns.append([])
                if value and value not in header_columns[index]:
                    header_columns[index].append(value)
        return [" ".join(parts) if parts else None for parts in header_columns]

    def _linearize_table_row(
        self,
        row: _HtmlTableRow,
        header_labels: list[str | None],
        caption: str,
    ) -> str | None:
        expanded_cells = self._expand_row_cells(row)
        if len(expanded_cells) < 2:
            return None

        row_label = next((text for text in expanded_cells if text), "")
        value_cells = expanded_cells[1:]
        if not row_label or not any(
            self._looks_numeric_or_quantitative(text) for text in value_cells if text
        ):
            return None

        statements: list[str] = []
        if caption:
            statements.append(f"Table: {caption}.")
        statements.append(f"Row: {row_label}.")

        value_fragments: list[str] = []
        for index, text in enumerate(value_cells, start=1):
            if not text:
                continue
            header = header_labels[index] if index < len(header_labels) else None
            if header:
                value_fragments.append(f"{header}: {text}")
            elif len(expanded_cells) == 2:
                value_fragments.append(f"Value: {text}")
            else:
                value_fragments.append(f"Column {index + 1}: {text}")

        if not value_fragments:
            return None

        statements.extend(f"{fragment}." for fragment in value_fragments)
        return " ".join(statements)

    def _build_logical_table_grid(self, rows: list[_HtmlTableRow]) -> list[list[str | None]]:
        active_spans: list[tuple[int, str | None] | None] = []
        grid: list[list[str | None]] = []

        for row in rows:
            values: list[str | None] = []
            column_index = 0

            for cell in row.cells:
                column_index = self._fill_active_span_values(
                    values, active_spans, column_index
                )
                cell_text = cell.text or None
                for _ in range(max(cell.colspan, 1)):
                    while len(active_spans) <= column_index:
                        active_spans.append(None)
                    values.append(cell_text)
                    active_spans[column_index] = (
                        (cell.rowspan - 1, cell_text) if cell.rowspan > 1 else None
                    )
                    column_index += 1

            self._fill_active_span_values(values, active_spans, column_index, drain=True)
            grid.append(values)

        return grid

    def _fill_active_span_values(
        self,
        values: list[str | None],
        active_spans: list[tuple[int, str | None] | None],
        column_index: int,
        *,
        drain: bool = False,
    ) -> int:
        while column_index < len(active_spans):
            span = active_spans[column_index]
            if span is None and not drain:
                break
            if span is None and drain:
                values.append(None)
                column_index += 1
                continue
            remaining_rows, span_text = span
            values.append(span_text)
            active_spans[column_index] = (
                (remaining_rows - 1, span_text) if remaining_rows > 1 else None
            )
            column_index += 1
        return column_index

    def _expand_row_cells(self, row: _HtmlTableRow) -> list[str | None]:
        expanded: list[str | None] = []
        for cell in row.cells:
            for _ in range(max(cell.colspan, 1)):
                expanded.append(cell.text or None)
        return expanded

    def _parse_table_span(
        self,
        attrs: list[tuple[str, str | None]],
        attr_name: str,
    ) -> int:
        for name, value in attrs:
            if name.lower() != attr_name:
                continue
            try:
                parsed = int((value or "").strip())
            except ValueError:
                return 1
            return parsed if parsed > 0 else 1
        return 1

    def _looks_numeric_or_quantitative(self, text: str) -> bool:
        return bool(
            re.search(
                r"\d|%|percent|percentage points|basis points|bps|\$|usd|eur|gbp|cad|million|billion|trillion",
                text,
                re.IGNORECASE,
            )
        )

    def _should_emit_generic_container(
        self,
        frame: _HtmlCaptureFrame,
        text: str,
    ) -> bool:
        """Keep prose-bearing leaf containers, but reject layout wrappers/chrome."""

        if frame.has_nested_content_container:
            return False

        word_count = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9&'-]*", text))
        if len(text) >= 40 and word_count >= 5:
            return True

        # Keep compact fact statements such as "Revenue rose 15% to $281.7B",
        # while still dropping short buttons and navigation labels.
        return len(text) >= 16 and word_count >= 3 and bool(re.search(r"\d", text))

    def _has_excluded_role(self, attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name.lower() == "role" and (value or "").strip().lower() in self._EXCLUDED_ROLES:
                return True
        return False


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def extract_source_document(payload: SourcePayload) -> ExtractedSourceDocument:
    adapter = build_source_adapter(payload.reference.source_kind)
    return adapter.extract(payload)
