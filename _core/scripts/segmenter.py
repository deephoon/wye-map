"""Wye backend/app/v2/ingestion/segmenter.py 사본(commit 3973709e). 설정값은 기본값으로 고정.

markdown → SourceSegment 초안 분할 (결정적).

V1은 segmentation을 브라우저가 소유했다. V2에서 Evidence의 Authority는
SourceRevision + SourceSegment(계약 §0-2)이므로 분할은 서버의 순수 함수여야 한다 —
같은 markdown은 언제나 같은 segment 목록을 낸다. LLM은 여기에 없다.

offset은 원본 markdown 문자열 기준이다. text는 언제나 markdown[start:end]와
바이트 단위로 같아야 한다 — 이 동일성이 깨지면 Evidence anchor 검증이 원문이 아닌
사본을 검증하게 된다.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
from hashlib import sha256

# Wye documents.images.FIGURE_HEADING 사본
FIGURE_HEADING = "## 문서에 실린 그림"

# 검증 anchor 탐색 비용과 프롬프트 예산을 함께 고려한 상한. 넘는 블록은 줄 경계에서 쪼갠다.
# 일반 문서·슬라이드 문단 한 개의 최대 글자 수. 녹취록 경로는 이 상한으로 쪼개지 않음.
# 기본 2,400, WYE_INGEST_MAX_SEGMENT_CHARS, 800~6,000
MAX_SEGMENT_CHARS = 2400
# 녹취록 병합 청크 목표 크기. 발언 조각 하나가 세그먼트가 되면 anchor에 붙을 문맥이 없다.
# 기본 1,200, WYE_INGEST_TRANSCRIPT_CHUNK_CHARS, 400~3,000
TRANSCRIPT_CHUNK_CHARS = 1200

# markdown 제목 줄("#"~"######" 뒤 공백·제목)
_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
# MarkItDown이 pptx 슬라이드 앞에 두는 주석. 슬라이드 하나가 제목·글머리표·비고 조각 서너 개로
# 오므로(실측 요구사항정의서: 문단 2,926개 중 2,912개가 289자 이하) 슬라이드 단위로 합친다.
_SLIDE_MARKER = re.compile(r"^<!--\s*Slide number:\s*(?P<number>\d+)\s*-->\s*$")
# "참석자 1 00:12" / "홍길동 1:03:22" 같은 발언자+타임스탬프 줄. 발언자 41자 이하
_SPEAKER_LINE = re.compile(r"^\S[^\n]{0,40}\s\d{1,2}:\d{2}(?::\d{2})?\s*$", re.MULTILINE)
# 쪽 표식(spec 123 FR-123-08). 변환기마다 쪽을 다르게 남긴다 — 로컬 PDF 변환(pdf_layout)은 쪽마다 "## N쪽",
# 슬라이드는 "## 슬라이드 N"(located)·"<!-- Slide number: N -->"(MarkItDown), 그 밖의 PDF 변환은 쪽 사이에 form feed(\f).
_PAGE_MARK = re.compile(r"^(?:## (\d+)쪽|## 슬라이드 (\d+)|<!--\s*Slide number:\s*(\d+)\s*-->)\s*$", re.MULTILINE)
# 그림 표식 줄(documents.images.figure_block) — 본문 뒤에 붙어 쪽 표식의 마지막 쪽을 이어받으면 거짓이 된다.
_FIGURE_LINE = re.compile(r"^\[그림 \d+\](?: \((\d+)쪽\))?$")


def is_transcript(markdown: str) -> bool:
    """결정적 휴리스틱: 발언자+타임스탬프 줄이 8개 이상이면 회의 녹취록으로 본다."""
    return isinstance(markdown, str) and len(_SPEAKER_LINE.findall(markdown)) >= 8


@dataclass(frozen=True)
class SegmentDraft:
    """저장 전의 분할 구간 하나. 원문 markdown에서의 시작과 끝 위치, 해시, 쪽 번호를 들고 SourceIngestService 결과로 나간다."""
    ordinal: int
    section: str
    text: str
    text_hash: str
    start_offset: int
    end_offset: int
    # 문단이 시작하는 쪽(1부터). 변환기가 쪽을 남기지 않은 형식(docx·md·txt…)은 None이다.
    page: int | None = None


def _hash(text: str) -> str:
    """문단 글자의 UTF-8 SHA-256 16진 문자열."""
    return sha256(text.encode("utf-8")).hexdigest()


def _trim_span(markdown: str, start: int, end: int) -> tuple[int, int]:
    """앞뒤 공백을 offset과 함께 걷어낸다. text와 원본 slice의 동일성을 지키기 위해
    strip한 문자열을 따로 만들지 않고 경계를 옮긴다."""
    while start < end and markdown[start] in " \t\r\n":
        start += 1
    while end > start and markdown[end - 1] in " \t\r\n":
        end -= 1
    return start, end


def _split_long(markdown: str, start: int, end: int) -> list[tuple[int, int]]:
    """MAX를 넘는 블록을 줄 경계에서 쪼갠다. 줄 경계가 없으면 강제로 자른다.

    - 자를 자리 = 현재 위치부터 MAX_SEGMENT_CHARS 안의 마지막 줄바꿈
    - 그 안에 줄바꿈이 없을 때: 지금 줄이 표 행("|"로 시작·끝)이면 그 행 끝까지 통째로, 아니면 MAX 글자에서 자름
    - 그래서 표 행 하나가 MAX보다 길면 그 구간은 MAX를 넘을 수 있음
    """
    spans: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > MAX_SEGMENT_CHARS:
        cut = markdown.rfind("\n", cursor, cursor + MAX_SEGMENT_CHARS)
        if cut <= cursor:
            # 표 행 하나는 나눌 수 없는 근거 구간. 칸 중간에서 자르면 분석 묶음에서
            # 열의 역할이 말없이 바뀜
            row_end = markdown.find("\n", cursor + 1, end)
            row_end = end if row_end < 0 else row_end
            row = markdown[cursor:row_end].strip()
            cut = row_end if row.startswith("|") and row.endswith("|") else cursor + MAX_SEGMENT_CHARS
        spans.append((cursor, cut))
        cursor = cut
    spans.append((cursor, end))
    return spans


def _pager(markdown: str):
    """offset → 쪽 번호. form feed가 있으면 그 수를 세고(앞에 있는 \f 수 + 1), 없으면 가장 가까운 앞 쪽 표식이다.
    둘 다 없으면 늘 None — 쪽을 지어내지 않는다."""
    # form feed 경로: \f 위치 목록을 만들어 offset 앞의 개수 + 1을 쪽으로 씀
    if "\f" in markdown:
        breaks = [index for index, char in enumerate(markdown) if char == "\f"]
        return lambda offset: bisect_right(breaks, offset) + 1
    # 쪽 표식 경로: 표식 시작 위치와 쪽 번호(세 꼴 중 잡힌 그룹 하나). offset 앞 표식이 없으면 None
    marks = [(match.start(), int(next(group for group in match.groups() if group)))
             for match in _PAGE_MARK.finditer(markdown)]
    if not marks:
        return lambda offset: None
    starts = [start for start, _ in marks]
    return lambda offset: marks[bisect_right(starts, offset) - 1][1] if bisect_right(starts, offset) else None


def _with_pages(markdown: str, drafts: list[SegmentDraft]) -> list[SegmentDraft]:
    """문단마다 시작 쪽을 단다(spec 123 FR-123-08 — 문단 표의 page 열이 늘 비어 있던 결함). 그림 표식 묶음의
    문단은 본문 쪽을 이어받지 않는다 — 표식이 가진 쪽(있으면)만 쓴다."""
    page_at = _pager(markdown)
    # 그림 표식 묶음 제목의 마지막 위치. 이 뒤에서 시작하는 문단은 그림 줄로 봄
    figures = markdown.rfind("\n" + FIGURE_HEADING + "\n")
    out = []
    for draft in drafts:
        if figures >= 0 and draft.start_offset > figures:
            found = _FIGURE_LINE.match(draft.text)
            page = int(found.group(1)) if found and found.group(1) else None
        else:
            page = page_at(draft.start_offset)
        out.append(replace(draft, page=page))
    return out


def segment_markdown(markdown: str) -> list[SegmentDraft]:
    """markdown을 근거 구간 목록으로 자른다. 회의 녹취록, 슬라이드, 일반 문서를 형식으로 가른다.
    빈 문자열이거나 문자열이 아니면 빈 목록을 돌려준다.

    - 판정 순서: 녹취록(is_transcript) → 슬라이드 표식 있음 → 일반 문서
    - 모든 경로가 끝에 문단마다 시작 쪽을 닮(_with_pages)
    """
    if not isinstance(markdown, str) or not markdown.strip():
        return []
    if is_transcript(markdown):
        return _with_pages(markdown, _segment_transcript(markdown))
    if "<!-- Slide number:" in markdown:
        return _with_pages(markdown, _segment_slides(markdown))
    return _with_pages(markdown, _segment_document(markdown))


def _segment_document(markdown: str) -> list[SegmentDraft]:
    """일반 문서 분할. 빈 줄로 나뉜 블록마다 문단 하나, MAX를 넘으면 _split_long으로 더 쪼갬.

    - 제목 줄 하나짜리 블록은 뒤 블록들의 section이 되고, 자신도 문단
    - 블록 찾기는 _document_blocks와 같은 규칙을 이 함수 안에서 다시 씀
    """
    # 블록 = 빈 줄로 구분된 연속 줄 묶음. 줄 단위로 훑으며 원본 offset을 유지한다.
    blocks: list[tuple[int, int]] = []
    block_start: int | None = None
    offset = 0
    for line in markdown.splitlines(keepends=True):
        if line.strip():
            if block_start is None:
                block_start = offset
        elif block_start is not None:
            blocks.append((block_start, offset))
            block_start = None
        offset += len(line)
    if block_start is not None:
        blocks.append((block_start, offset))

    # 블록마다 앞뒤 공백을 걷고, 제목 줄이면 section을 바꾼 뒤 MAX 기준으로 쪼개 문단으로 냄
    drafts: list[SegmentDraft] = []
    section = ""
    ordinal = 1  # V1 wire 계약(SourceSegmentIn.ordinal >= 1)과 정렬
    for raw_start, raw_end in blocks:
        start, end = _trim_span(markdown, raw_start, raw_end)
        if start >= end:
            continue
        first_line = markdown[start:end].split("\n", 1)[0]
        heading = _HEADING.match(first_line)
        if heading and "\n" not in markdown[start:end]:
            # 제목 줄 하나짜리 블록: 이후 블록들의 section이 되고, 자신도 segment다.
            section = heading.group("title")
        for span_start, span_end in _split_long(markdown, start, end):
            span_start, span_end = _trim_span(markdown, span_start, span_end)
            if span_start >= span_end:
                continue
            text = markdown[span_start:span_end]
            drafts.append(SegmentDraft(
                ordinal=ordinal, section=section, text=text, text_hash=_hash(text),
                start_offset=span_start, end_offset=span_end))
            ordinal += 1
    return drafts


def _segment_transcript(markdown: str) -> list[SegmentDraft]:
    """녹취록: 연속 발언 블록을 주제 청크로 병합한다. text는 여전히 원본 slice
    그대로다(빈 줄 포함) — offset·hash 동일성 규칙은 문서와 같다.

    - 앞에서부터 블록을 이어 붙이다 청크 시작부터 TRANSCRIPT_CHUNK_CHARS를 넘으면 새 청크 시작
    - 블록 하나가 그 크기를 넘어도 쪼개지 않음(MAX_SEGMENT_CHARS 분할 없음)
    - section은 늘 빈 문자열
    """
    base = _document_blocks(markdown)
    if not base:
        return []
    # 청크 시작부터 이 블록 끝까지가 목표 크기 안이면 이어 붙이고, 넘으면 새 청크
    merged: list[tuple[int, int]] = []
    span_start, span_end = base[0]
    for start, end in base[1:]:
        if end - span_start <= TRANSCRIPT_CHUNK_CHARS:
            span_end = end
        else:
            merged.append((span_start, span_end))
            span_start, span_end = start, end
    merged.append((span_start, span_end))
    drafts: list[SegmentDraft] = []
    for ordinal, (start, end) in enumerate(merged, start=1):
        start, end = _trim_span(markdown, start, end)
        if start >= end:
            continue
        text = markdown[start:end]
        drafts.append(SegmentDraft(ordinal=ordinal, section="", text=text,
                                   text_hash=_hash(text),
                                   start_offset=start, end_offset=end))
    return drafts


def _segment_slides(markdown: str) -> list[SegmentDraft]:
    """pptx: 슬라이드 안의 조각을 한 문단으로 합친다. 마커 주석은 경계일 뿐 문단이 아니다.
    text는 원본 slice 그대로다(조각 사이 빈 줄 포함) — offset·hash 규칙은 문서와 같다.
    슬라이드 하나가 MAX를 넘으면 문서와 같은 규칙으로 줄 경계에서 쪼갠다."""
    drafts: list[SegmentDraft] = []
    section = ""
    ordinal = 1
    span: tuple[int, int] | None = None

    def flush() -> None:
        """모아 둔 슬라이드 구간을 MAX 기준으로 쪼개 문단으로 내보내고 비움."""
        nonlocal ordinal, span
        if span is None:
            return
        for raw_start, raw_end in _split_long(markdown, *span):
            start, end = _trim_span(markdown, raw_start, raw_end)
            if start >= end:
                continue
            text = markdown[start:end]
            drafts.append(SegmentDraft(ordinal=ordinal, section=section, text=text,
                                       text_hash=_hash(text), start_offset=start, end_offset=end))
            ordinal += 1
        span = None

    # 마커 줄을 만나면 앞 슬라이드를 내보내고 section을 "Slide N"으로 바꿈. 그 밖 블록은 현재 슬라이드 구간에 이어 붙임
    for start, end in _document_blocks(markdown):
        marker = _SLIDE_MARKER.match(markdown[start:end].strip())
        if marker:
            flush()
            section = f"Slide {marker.group('number')}"
            continue
        span = (start, end) if span is None else (span[0], end)
    flush()
    return drafts


def _document_blocks(markdown: str) -> list[tuple[int, int]]:
    """빈 줄(공백만 있는 줄 포함)로 나뉜 연속 줄 묶음의 (시작, 끝) offset 목록. 끝은 마지막 줄바꿈 뒤."""
    blocks: list[tuple[int, int]] = []
    block_start: int | None = None
    offset = 0
    for line in markdown.splitlines(keepends=True):
        if line.strip():
            if block_start is None:
                block_start = offset
        elif block_start is not None:
            blocks.append((block_start, offset))
            block_start = None
        offset += len(line)
    if block_start is not None:
        blocks.append((block_start, offset))
    return blocks
