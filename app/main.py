from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from manifest_generator import ValidationError, build_manifest, validate_row

APP_API_KEY = "change-me-in-production"
AUDIT_LOG_PATH = Path("logs/audit.log")

app = FastAPI(title="Clinical Manifest Generator", version="1.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _require_api_key(x_api_key: str | None) -> None:
    if x_api_key != APP_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_audit(event: dict) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/manifests/generate")
async def generate_manifest(
    request: Request,
    file: UploadFile = File(...),
    shipment_id: str = Form(...),
    courier: str = Form(...),
    x_api_key: str | None = Header(default=None),
):
    _require_api_key(x_api_key)

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Input CSV is missing a header row.")

    rows = [dict(row) for row in reader]

    try:
        validated = [validate_row(index=i, row=row) for i, row in enumerate(rows, start=2)]
        manifest = build_manifest(shipment_id=shipment_id, courier=courier, records=validated)
    except ValidationError as exc:
        _write_audit(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "manifest_generation_failed",
                "shipment_id": shipment_id,
                "reason": str(exc),
                "request_ip": request.client.host if request.client else "unknown",
            }
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _write_audit(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "manifest_generated",
            "shipment_id": shipment_id,
            "courier": courier,
            "sample_count": manifest["sample_count"],
            "sample_fingerprints": [_sha256(item["sample_id"]) for item in manifest["samples"]],
            "request_ip": request.client.host if request.client else "unknown",
        }
    )

    payload = json.dumps(manifest, indent=2) + "\n"
    filename = f"manifest_{shipment_id}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=payload, media_type="application/json", headers=headers)


@app.get("/audit", response_class=JSONResponse)
def audit_entries(x_api_key: str | None = Header(default=None)):
    _require_api_key(x_api_key)
    if not AUDIT_LOG_PATH.exists():
        return JSONResponse(content=[])
    rows = [json.loads(line) for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines() if line]
    return JSONResponse(content=rows)
