"""표준 라이브러리만으로 쓰는 작은 xlsx 쓰기. Excel·Numbers·LibreOffice에서 열림.

- 시트 여러 개, 머리 행(굵게·바탕색·틀 고정), 열 폭, 숨은 열, 행 바탕색(상태 색), 줄바꿈
- 값은 글자(inline string)와 숫자만. 수식·병합·차트는 없음
- 읽기는 하지 않음 — 고객이 채운 파일은 convert.py(markitdown)가 자료로 읽음
"""

from __future__ import annotations

import zipfile
from xml.sax.saxutils import escape

# 상태 색(연한 바탕). 키는 행에 붙이는 이름
FILLS = {"header": "FFE8E6E1", "ok": "FFE3F4E6", "warn": "FFFFF4D6", "bad": "FFFDE2E1", "info": "FFE6EEFB", "muted": "FFF1F1EF"}
_FILL_INDEX = {name: index + 2 for index, name in enumerate(FILLS)}


def _col(index: int) -> str:
    """0부터 → A, B, … Z, AA."""
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _clean(text: str) -> str:
    """XML에 못 들어가는 제어 문자 제거 후 이스케이프."""
    return escape("".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32))


def _styles() -> str:
    """스타일: 0 기본, 1 머리(굵게·바탕), 2.. 상태 바탕. 모두 위 정렬·줄바꿈."""
    fills = '<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    fills += "".join(f'<fill><patternFill patternType="solid"><fgColor rgb="{rgb}"/></patternFill></fill>' for rgb in FILLS.values())
    xfs = '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
    xfs += f'<xf numFmtId="0" fontId="1" fillId="{_FILL_INDEX["header"]}" borderId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
    xfs += "".join(f'<xf numFmtId="0" fontId="0" fillId="{_FILL_INDEX[name]}" borderId="0" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
                   for name in FILLS)
    count = 2 + len(FILLS)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            f'<fills count="{len(FILLS) + 2}">{fills}</fills><borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{count}">{xfs}</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def _sheet(sheet: dict) -> str:
    """시트 XML. sheet = {name, header[], rows[[...]], widths[], hidden[열 번호], fills[행별 상태 이름 또는 None]}."""
    widths = sheet.get("widths") or []
    hidden = set(sheet.get("hidden") or [])
    hide = ' hidden="1"'
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"{hide if i in hidden else ""}/>'
                   for i, w in enumerate(widths))
    rows_xml = []
    all_rows = [sheet["header"], *sheet["rows"]]
    fills = [None, *(sheet.get("fills") or [None] * len(sheet["rows"]))]
    for r, row in enumerate(all_rows, start=1):
        style = 1 if r == 1 else (_FILL_INDEX[fills[r - 1]] if fills[r - 1] in FILLS else 0)
        cells = []
        for c, value in enumerate(row):
            ref = f"{_col(c)}{r}"
            attr = f' s="{style}"' if style else ""
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"{attr}><v>{value}</v></c>')
            elif value not in (None, ""):
                cells.append(f'<c r="{ref}"{attr} t="inlineStr"><is><t xml:space="preserve">{_clean(str(value))}</t></is></c>')
            elif style:
                cells.append(f'<c r="{ref}"{attr}/>')
        rows_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
    pane = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{pane}{f"<cols>{cols}</cols>" if cols else ""}<sheetData>{"".join(rows_xml)}</sheetData></worksheet>')


def write(path, sheets: list[dict]) -> None:
    """xlsx 파일 쓰기. 시트 이름은 31자까지, 금지 글자는 _로."""
    names = []
    for sheet in sheets:
        name = "".join("_" if ch in '[]:*?/\\' else ch for ch in sheet["name"])[:31] or "Sheet"
        names.append(name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(len(sheets))) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{_clean(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                             for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   + "</Relationships>")
        z.writestr("xl/styles.xml", _styles())
        for i, sheet in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet(sheet))
