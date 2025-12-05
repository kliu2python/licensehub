import os
import re
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from PyPDF2 import PdfReader

LICENSE_ROOT = Path("licenses")
templates = Jinja2Templates(directory="templates")

app = FastAPI()


def extract_code(pdf: Path):
    try:
        reader = PdfReader(str(pdf))
    except:
        return None

    text = ""
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"

    m = re.search(r"Registration Code\s*:\s*([A-Z0-9\-]+)", text)
    return m.group(1) if m else None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/project/{project}", response_class=HTMLResponse)
def project_page(project: str, request: Request):
    project_path = LICENSE_ROOT / project
    project_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(project_path.glob("*.pdf"))
    licenses = []

    for pdf in pdf_files:
        code = extract_code(pdf)
        licenses.append({
            "filename": pdf.name,
            "code": code or "Not Found"
        })

    return templates.TemplateResponse("project.html", {
        "request": request,
        "project": project,
        "licenses": licenses
    })


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

        # Save PDF
        with open(save_path, "wb") as f:
            f.write(await file.read())

        uploaded.append(file.filename)

    return {
        "uploaded": uploaded,
        "skipped": skipped
    }


@app.delete("/project/{project}/delete/{filename}")
def delete_license(project: str, filename: str):
    pdf_path = LICENSE_ROOT / project / filename

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File does not exist")

    os.remove(pdf_path)
    return {"status": "deleted"}
