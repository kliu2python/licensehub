import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from dateutil import parser
from pdf2image import convert_from_path
import pytesseract
from PyPDF2 import PdfReader

LICENSE_ROOT = Path("licenses")
templates = Jinja2Templates(directory="templates")
app = FastAPI(title="License Hub")


def ensure_license_root():
    LICENSE_ROOT.mkdir(parents=True, exist_ok=True)


def parse_date(text: str) -> Optional[str]:
    """Attempt to parse a date string into ISO format (YYYY-MM-DD)."""
    try:
        dt = parser.parse(text, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (parser.ParserError, ValueError, TypeError):
        return None


KEYWORD_PATTERNS: dict[str, list[str]] = {
    "FGT": ["FORTIGATE", "FGT"],
    "FAC": ["FORTIAUTHENTICATOR", "FAC"],
    "FTM": ["FORTITOKEN", "FORTITOKENS", "FTM"],
    "FIC": ["FORTIIDENTITY CLOUD", "FORTIIDENTITYCLOUD", "FIC"],
}


def find_keyword(text: str) -> Optional[str]:
    upper_text = text.upper()

    for keyword, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            if pattern in upper_text:
                return keyword

    return None


def extract_license_info(pdf: Path) -> dict[str, Optional[str]]:
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return {"code": None, "expiration": None, "keyword": None}

    text_chunks: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_chunks.append(page_text)
    text = "\n".join(text_chunks)

    code_patterns = [
        r"Registration Code\s*:\s*([A-Z0-9\-]+)",
        r"Contract Registration Code\s*:\s*([A-Z0-9\-]+)",
        r"Activation Code\s*:?\s*([A-Z0-9\-]+)",
    ]

    code = None

    for pattern in code_patterns:
        code_match = re.search(pattern, text, re.IGNORECASE)
        if code_match:
            code = code_match.group(1).upper()
            break
    expiration_match = re.search(
        r"(Expiration|Expiry|Expires)\s*(Date)?\s*:?\s*([A-Za-z0-9,\-/ ]{6,30})",
        text,
        re.IGNORECASE,
    )

    raw_expiration = expiration_match.group(3).strip() if expiration_match else None
    expiration = parse_date(raw_expiration) if raw_expiration else None

    keyword = find_keyword(text)

    if keyword == "FTM" and not code:
        code = extract_ftm_activation_code(pdf)

    return {
        "code": code,
        "expiration": expiration,
        "keyword": keyword,
    }


def extract_ftm_activation_code(pdf: Path) -> Optional[str]:
    try:
        images = convert_from_path(pdf)
    except Exception:
        return None

    for image in images:
        try:
            text = pytesseract.image_to_string(image).upper()
        except Exception:
            continue

        match = re.search(r"[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}", text)
        if match:
            return match.group(0)

    return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    ensure_license_root()
    projects = sorted([p.name for p in LICENSE_ROOT.iterdir() if p.is_dir()])
    return templates.TemplateResponse(
        "index.html", {"request": request, "projects": projects}
    )


@app.get("/project/{project}", response_class=HTMLResponse)
def project_page(project: str, request: Request):
    project_path = LICENSE_ROOT / project
    project_path.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(project_path.glob("*.pdf"))
    licenses = []

    for pdf in pdf_files:
        info = extract_license_info(pdf)
        licenses.append(
            {
                "filename": pdf.name,
                "code": info["code"] or "Not Found",
                "expiration": info["expiration"] or "Unknown",
                "keyword": info["keyword"] or "Unknown",
            }
        )

    return templates.TemplateResponse(
        "project.html",
        {
            "request": request,
            "project": project,
            "licenses": licenses,
        },
    )


@app.post("/project/{project}/upload")
async def upload_multiple_pdfs(project: str, files: list[UploadFile] = File(...)):
    project_path = LICENSE_ROOT / project
    project_path.mkdir(parents=True, exist_ok=True)

    uploaded = []
    skipped = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            skipped.append(file.filename)
            continue

        save_path = project_path / file.filename
        with open(save_path, "wb") as f:
            f.write(await file.read())

        uploaded.append(file.filename)

    return {"uploaded": uploaded, "skipped": skipped}


@app.delete("/project/{project}/delete/{filename}")
def delete_license(project: str, filename: str):
    pdf_path = LICENSE_ROOT / project / filename

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File does not exist")

    os.remove(pdf_path)
    return {"status": "deleted"}


@app.get("/project/{project}/download/{filename}")
def download_license(project: str, filename: str):
    pdf_path = LICENSE_ROOT / project / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File does not exist")
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@app.get("/project/{project}/license/{filename}")
def get_license_metadata(project: str, filename: str):
    pdf_path = LICENSE_ROOT / project / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File does not exist")

    info = extract_license_info(pdf_path)
    return {
        "filename": filename,
        "code": info["code"],
        "expiration": info["expiration"],
        "keyword": info["keyword"],
    }
