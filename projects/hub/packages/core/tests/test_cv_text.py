"""The text of a CV, as `read_freelancer_cv` answers it (ORB-206)."""

from orbiters_core.cv_text import MAX_CHARS, MAX_PAGES, TRUNCATION_MARKER, CvText, extract_text
from orbiters_core.perks import guide_bytes


def test_a_real_pdf_answers_its_pages_and_its_text() -> None:
    read = extract_text(guide_bytes(), "guida.pdf")
    assert (read.filename, read.pagine, read.troncato) == ("guida.pdf", 6, False)
    assert "prima fattura" in read.testo
    assert TRUNCATION_MARKER not in read.testo


def test_a_pdf_with_no_readable_text_answers_empty_text_and_no_truncation() -> None:
    # A header on nothing: pypdf cannot count a page in it, and that is not a document
    # cut short, it is a document with nothing to read.
    read = extract_text(b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF\n", "vuoto.pdf")
    assert read == CvText(filename="vuoto.pdf", pagine=0, testo="", troncato=False)


def test_bytes_that_are_not_a_pdf_answer_the_same_and_never_raise() -> None:
    assert extract_text(b"not a pdf at all", "x.pdf").testo == ""
    empty = CvText(filename="x.pdf", pagine=0, testo="", troncato=False)
    assert extract_text(b"", "x.pdf") == empty


def test_the_ceilings_are_the_ones_the_tool_documents() -> None:
    assert MAX_PAGES == 20
    assert MAX_CHARS == 200_000
