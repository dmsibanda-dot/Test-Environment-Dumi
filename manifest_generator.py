#!/usr/bin/env python3
"""Generate shipment manifests for clinical samples."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REQUIRED_FIELDS = {
    "sample_id",
    "patient_id",
    "collection_datetime",
    "specimen_type",
    "volume_ml",
    "storage_temp_c",
    "priority",
    "destination_lab",
}


@dataclass(frozen=True)
class SampleRecord:
    sample_id: str
    patient_id: str
    collection_datetime: str
    specimen_type: str
    volume_ml: float
    storage_temp_c: float
    priority: str
    destination_lab: str
    notes: str = ""


class ValidationError(Exception):
    pass


def load_records(input_file: Path) -> list[dict[str, str]]:
    with input_file.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValidationError("Input CSV is missing a header row.")

        missing = REQUIRED_FIELDS - {field.strip() for field in reader.fieldnames}
        if missing:
            raise ValidationError(
                f"Input CSV is missing required fields: {', '.join(sorted(missing))}"
            )

        return [dict(row) for row in reader]


def parse_iso8601(value: str, field_name: str) -> str:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(
            f"{field_name} must be ISO-8601 datetime. Got '{value}'."
        ) from exc

    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def validate_row(index: int, row: dict[str, str]) -> SampleRecord:
    def required(name: str) -> str:
        value = (row.get(name) or "").strip()
        if not value:
            raise ValidationError(f"Row {index}: '{name}' is required.")
        return value

    sample_id = required("sample_id")
    if not re.fullmatch(r"[A-Z0-9\-]{4,32}", sample_id):
        raise ValidationError(
            f"Row {index}: sample_id '{sample_id}' must be 4-32 chars using A-Z, 0-9, -."
        )

    patient_id = required("patient_id")
    collection_datetime = parse_iso8601(required("collection_datetime"), "collection_datetime")
    specimen_type = required("specimen_type")

    try:
        volume_ml = float(required("volume_ml"))
    except ValueError as exc:
        raise ValidationError(f"Row {index}: volume_ml must be numeric.") from exc
    if volume_ml <= 0:
        raise ValidationError(f"Row {index}: volume_ml must be > 0.")

    try:
        storage_temp_c = float(required("storage_temp_c"))
    except ValueError as exc:
        raise ValidationError(f"Row {index}: storage_temp_c must be numeric.") from exc

    priority = required("priority").upper()
    if priority not in {"ROUTINE", "STAT"}:
        raise ValidationError(f"Row {index}: priority must be ROUTINE or STAT.")

    destination_lab = required("destination_lab")
    notes = (row.get("notes") or "").strip()

    return SampleRecord(
        sample_id=sample_id,
        patient_id=patient_id,
        collection_datetime=collection_datetime,
        specimen_type=specimen_type,
        volume_ml=volume_ml,
        storage_temp_c=storage_temp_c,
        priority=priority,
        destination_lab=destination_lab,
        notes=notes,
    )


def build_manifest(shipment_id: str, courier: str, records: Iterable[SampleRecord]) -> dict:
    records = list(records)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "shipment_id": shipment_id,
        "generated_at": generated_at,
        "courier": courier,
        "sample_count": len(records),
        "samples": [record.__dict__ for record in records],
    }


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Input CSV path")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument("--shipment-id", required=True, help="Unique shipment identifier")
    parser.add_argument("--courier", required=True, help="Courier or transport partner")
    args = parser.parse_args()

    rows = load_records(args.input)
    validated = [validate_row(index=i, row=row) for i, row in enumerate(rows, start=2)]
    manifest = build_manifest(args.shipment_id, args.courier, validated)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    print(
        f"Manifest generated: {args.output} ({manifest['sample_count']} samples, shipment={args.shipment_id})"
    )


if __name__ == "__main__":
    run()
