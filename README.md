# Clinical Sample Shipment Manifest App

Web + CLI app to generate shipment manifests for clinical samples.

## Security defaults

- API key is required for manifest generation and audit access (`x-api-key`).
- Default key in code is for local development only; rotate before production.
- Audit logs are written to `logs/audit.log` as JSON lines with hashed sample identifiers.

## One-command run (Docker)

```bash
docker compose up --build
```

Then open `http://127.0.0.1:8000`.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Drag-and-drop web workflow

1. Open `/`.
2. Enter API key, shipment ID, and courier.
3. Drag/drop CSV file.
4. Click **Generate & Download Manifest** to download a `.json` file response.

## API endpoints

- `GET /health` — health check
- `POST /manifests/generate` — authenticated CSV upload and downloadable JSON response
- `GET /audit` — authenticated audit log access

## CLI fallback

```bash
python3 manifest_generator.py \
  --input sample_input.csv \
  --output manifests/manifest_2026-05-07.json \
  --shipment-id SHIP-20260507-001 \
  --courier MedTransit
```
