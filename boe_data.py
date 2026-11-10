"""Read the pinned Bank of England monthly spot-rate archive without imputation."""

import json
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from math import isfinite
from zipfile import ZipFile

import numpy as np
from openpyxl import load_workbook


STUDY_YEAR = 2025
PUBLISHED_GRID = np.arange(2, 21) / 2  # Common complete 1–10Y grid.


def verified_payload(path, expected_hash):
    payload = path.read_bytes()
    actual_hash = sha256(payload).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected_hash}, got {actual_hash}")
    return payload


def monthly_rows(sheet, first_row):
    """Find the single official source date for each month of the study year."""
    rows = {}
    for cell, in sheet.iter_rows(min_row=first_row, max_col=1):
        value = cell.value
        if value is None:
            continue
        if not isinstance(value, datetime):
            raise ValueError(f"Invalid date at {sheet.title}!{cell.coordinate}: {value!r}")
        if value.year != STUDY_YEAR:
            continue
        if value.month in rows:
            raise ValueError(f"Multiple {STUDY_YEAR}-{value.month:02d} rows in {sheet.title}")
        rows[value.month] = (value.date().isoformat(), cell.row)
    missing = sorted(set(range(1, 13)) - rows.keys())
    if missing:
        raise ValueError(f"Missing {STUDY_YEAR} months in {sheet.title}: {missing}")
    return rows


def published_rate(cell, source):
    value = cell.value
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"Missing or invalid required rate at {cell.parent.title}!{cell.coordinate}")
    if cell.number_format != source["cell_number_format"]:
        raise ValueError(f"Unexpected rate format at {cell.parent.title}!{cell.coordinate}")
    return float(value)


def load_inputs(source_dir):
    sources = json.loads((source_dir / "sources.json").read_text(encoding="utf-8"))
    source = sources["bank_of_england"]
    coupon = sources["coupon_terms"]
    if source["rate_unit"] != "annual_continuously_compounded_percentage_points":
        raise ValueError("Route B requires the verified annual continuously compounded percent unit.")
    if (coupon["annual_coupon_decimal"], coupon["payments_per_year"], coupon["face_gbp"]) != (0.04, 2, 100):
        raise ValueError("Coupon terms differ from the reviewed DMO prospectus.")

    payload = verified_payload(source_dir / source["archive"], source["sha256"])
    verified_payload(source_dir / coupon["file"], coupon["sha256"])
    with ZipFile(BytesIO(payload)) as archive:
        workbook_bytes = archive.read(source["workbook"])
    if sha256(workbook_bytes).hexdigest() != source["workbook_sha256"]:
        raise ValueError(f"SHA-256 mismatch for workbook {source['workbook']}")

    workbook = load_workbook(BytesIO(workbook_bytes), data_only=True)
    try:
        return sources, extract_panel(workbook, source)
    finally:
        workbook.close()


def extract_panel(workbook, source):
    sheet = workbook[source["sheet"]]
    short_end = workbook[source["short_end_sheet"]]
    if (sheet["B1"].value, sheet["A4"].value) != (source["worksheet_title"], "years:"):
        raise ValueError("The source sheet is not the expected nominal spot curve in years.")
    if (short_end["B1"].value, short_end["A3"].value) != ("UK nominal spot curve, short end", "months:"):
        raise ValueError("The short-end sheet is not the expected nominal spot curve in months.")

    maturities = {}
    for cell in sheet[4][1:]:
        term = cell.value
        if type(term) in (int, float) and term in np.r_[0.5, PUBLISHED_GRID]:
            if term in maturities:
                raise ValueError(f"Duplicate maturity {term} in {sheet.title}")
            maturities[term] = cell.column
    if set(maturities) != set(np.r_[0.5, PUBLISHED_GRID]):
        raise ValueError("The workbook does not contain the required half-year maturity headers.")
    short_columns = [cell.column for cell in short_end[3][1:] if cell.value == 6]
    if len(short_columns) != 1:
        raise ValueError("Expected exactly one six-month column in the short-end sheet.")
    short_column, = short_columns

    rows = monthly_rows(sheet, 5)
    short_rows = monthly_rows(short_end, 6)
    rates, coverage = [], []
    for month in range(1, 13):
        date, row = rows[month]
        short_date, short_row = short_rows[month]
        if date != short_date:
            raise ValueError(f"Monthly date mismatch in the two spot sheets for {date}")
        main_half = sheet.cell(row, maturities[0.5])
        short_half = short_end.cell(short_row, short_column)
        if main_half.value is None and short_half.value is None:
            half_year_status = "not_published"
        else:
            if published_rate(main_half, source) != published_rate(short_half, source):
                raise ValueError(f"Conflicting published six-month rates for {date}")
            half_year_status = "published_outside_common_grid"
        coverage.append({
            "as_of_date": date, "maturity_years": 0.5, "status": half_year_status,
            "full_curve_cell": f"{sheet.title}!{main_half.coordinate}",
            "short_end_cell": f"{short_end.title}!{short_half.coordinate}",
            "analysis_policy": "excluded_for_all_months",
        })
        for maturity in PUBLISHED_GRID:
            cell = sheet.cell(row, maturities[maturity])
            rate_percent = published_rate(cell, source)
            rates.append({
                "as_of_date": date, "maturity_years": float(maturity),
                "source_rate_percent": rate_percent, "zero_rate_decimal": rate_percent / 100,
                "source_kind": "official_published_estimate",
                "source_workbook": source["workbook"], "source_sheet": sheet.title,
                "source_cell": cell.coordinate, "source_url": source["url"],
                "source_archive_sha256": source["sha256"],
            })
    return rates, coverage
