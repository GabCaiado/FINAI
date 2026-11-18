"""Pick the importer from the file name AND the content: they must agree."""

from pathlib import PurePath
from typing import Literal

from app.parsers.failures import unsupported_file

FileFormat = Literal["csv", "ofx", "pdf"]

SNIFF_BYTES = 1024
PDF_SIGNATURE = b"%PDF-"
OFX_SIGNATURES = (b"OFXHEADER:", b"<OFX>", b"<?OFX")
FORMAT_BY_EXTENSION: dict[str, FileFormat] = {".csv": "csv", ".ofx": "ofx", ".pdf": "pdf"}


def detect_format(filename: str, content: bytes) -> FileFormat:
    """Return ``csv``, ``ofx`` or ``pdf``; ``unsupported_file`` when unknown or contradictory.

    CSV has no signature, so a ``.csv`` is accepted only when the content does not look like OFX
    or PDF. The extension is the client's claim; only its suffix is read.
    """
    declared = FORMAT_BY_EXTENSION.get(PurePath(filename).suffix.lower())
    if declared is None or _signature(content) != declared:
        raise unsupported_file()
    return declared


def _signature(content: bytes) -> FileFormat:
    head = content[:SNIFF_BYTES]
    if head.startswith(PDF_SIGNATURE):
        return "pdf"
    if any(signature in head for signature in OFX_SIGNATURES):
        return "ofx"
    return "csv"
