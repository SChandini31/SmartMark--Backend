
import re

from app.services.document_extraction_service import extract_text_from_file

path = r"C:\SmartMark--backend\uploads\documents\5320e3a52fe04b8aa9638eff57547d90.docx"

text = extract_text_from_file(path)

print(f"Total extracted characters: {len(text)}")
print("\nPossible headings in document order:\n")

heading_pattern = re.compile(
    r"^(?:"
    r"experiment\b|"
    r"\d+\s*(?:\([a-z]\))?\s*[:.)-]?\s+\S|"
    r"aim|objective|theory|components|apparatus|"
    r"circuit connections|procedure|program|code|"
    r"expected output|sample output|observation|"
    r"result|conclusion|log,?\s+analyse"
    r")",
    re.IGNORECASE,
)

for number, line in enumerate(text.splitlines(), start=1):
    line = line.strip()

    if line and len(line) <= 120 and heading_pattern.search(line):
        print(f"Line {number}: {line}")
