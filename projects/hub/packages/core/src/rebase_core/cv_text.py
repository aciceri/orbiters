"""The text of a stored CV, as `pypdf` reads it, for an agent that has to match a card
against a request without leaving the MCP (ORB-206).

Extraction happens on read, not at upload: a CV weighs five megabytes at most and there
are a few dozen, so the work is cheap, and a text computed on the way out can never fall
behind the bytes it came from. No OCR: a scanned CV answers empty text and says so
through `pagine`, so the caller can tell a scan from a card without a file.

Every failure of the PDF itself is the same answer, empty text with the pages it managed
to count, never an exception: an encrypted file, a truncated one, a `%PDF` header on
something that is not a PDF. `pypdf` raises its own `PdfReadError` for some
malformations and plain `KeyError`/`ValueError`/`struct.error` for others, and a list
of them is a list the next release breaks, which is why the `except` is that broad.
The shape follows the one PigroCRM measured for its documents; it is written again here
because the hub imports nothing from the CRM.
"""

from io import BytesIO

from pydantic import BaseModel
from pypdf import PdfReader

# A CV is two pages and a designer's portfolio-as-CV ten; twenty is past both, and it
# keeps a mis-uploaded book from being read to the end for nothing.
MAX_PAGES = 20
# Characters, not tokens: two hundred thousand is fifty pages of dense prose, and an
# MCP client that has to carry the answer in a context window has to stop somewhere.
MAX_CHARS = 200_000
TRUNCATION_MARKER = "\n\n[…] testo troncato"


class CvText(BaseModel):
    """What `read_freelancer_cv` answers: the text, page by page joined with a newline,
    with the count of pages the file has and whether the text was cut short, by the page
    ceiling or the character one."""

    filename: str
    pagine: int
    testo: str
    troncato: bool


def extract_text(content: bytes, filename: str) -> CvText:
    pages: list[str] = []
    held = 0
    total = 0
    truncated = False
    try:
        reader = PdfReader(BytesIO(content))
        total = len(reader.pages)
        truncated = total > MAX_PAGES
        for page in reader.pages[:MAX_PAGES]:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)
            held += len(text)
            if held > MAX_CHARS:
                truncated = True
                break
    except Exception:  # noqa: BLE001 - see the module docstring
        return CvText(filename=filename, pagine=total, testo="", troncato=False)
    joined = "\n".join(pages)
    if len(joined) > MAX_CHARS:
        joined = joined[:MAX_CHARS] + TRUNCATION_MARKER
    elif truncated:
        joined = joined + TRUNCATION_MARKER
    return CvText(filename=filename, pagine=total, testo=joined, troncato=truncated)
