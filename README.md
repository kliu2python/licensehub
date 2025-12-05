# License Hub

A lightweight FastAPI UI to organize license PDFs, extract registration codes, and capture expiration hints.

## Running locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Docker
Build and run the containerized app:
```bash
docker build -t license-hub .
docker run -p 8000:8000 -v $(pwd)/licenses:/app/licenses license-hub
```

Visit http://localhost:8000 to use the hub.
