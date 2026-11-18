"""B2b: ``detect_format`` trusts neither the extension nor the content alone."""

import pytest

from app.errors import AppError
from app.parsers.dispatch import detect_format

CSV = b"data;descricao;valor\n01/09/2026;CAFE;-1,00\n"
OFX_V1 = b"OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\n\n<OFX></OFX>"
OFX_V2 = b'<?xml version="1.0"?>\n<?OFX OFXHEADER="200" VERSION="220"?>\n<OFX></OFX>'
OFX_BARE = b"\n  <OFX><SIGNONMSGSRSV1></SIGNONMSGSRSV1></OFX>"
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("extrato.csv", CSV, "csv"),
        ("EXTRATO.CSV", CSV, "csv"),
        ("pasta/extrato.csv", CSV, "csv"),
        ("extrato.ofx", OFX_V1, "ofx"),
        ("extrato.OFX", OFX_V2, "ofx"),
        ("extrato.ofx", OFX_BARE, "ofx"),
        ("extrato.pdf", PDF, "pdf"),
        ("extrato.csv", b"", "csv"),  # an empty file is the CSV parser's problem, not ours
    ],
)
def test_matching_extension_and_content(filename: str, content: bytes, expected: str) -> None:
    assert detect_format(filename, content) == expected


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("extrato.csv", OFX_V1),  # extension swapped
        ("extrato.csv", OFX_V2),
        ("extrato.csv", PDF),
        ("extrato.ofx", CSV),
        ("extrato.ofx", PDF),
        ("extrato.pdf", CSV),
        ("extrato.pdf", OFX_V1),
        ("extrato.txt", CSV),
        ("extrato", CSV),
        ("", CSV),
        ("extrato.csv.exe", CSV),
        ("extrato.xlsx", CSV),
        (".csv", OFX_V1),
    ],
)
def test_contradictions_and_unknown_extensions_are_unsupported(
    filename: str, content: bytes
) -> None:
    with pytest.raises(AppError) as caught:
        detect_format(filename, content)

    assert (caught.value.code, caught.value.status_code) == ("unsupported_file", 422)
