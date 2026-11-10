"""Reapply the curve method to a validated Bank of England 2025 data snapshot."""

import argparse
import json
import sys
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from boe_data import PUBLISHED_GRID, STUDY_YEAR, load_inputs, verified_payload
from curve import cash_flows, present_value
from run_experiment import DENSITIES, HOLDOUT, METHODS, evaluate_reference, write_results


ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "data" / "route_b"
RESULTS_DIR = ROOT / "results_b"
PRICE_KIND = "boe_spot_implied_standardized_bond_price"
EXPECTED_ROWS = {
    "reference_rates.csv": 228,
    "coverage_audit.csv": 12,
    "cashflow_valuation.csv": 2280,
    "metrics.csv": 48,
    "curves.csv": 912,
    "holdout_prices.csv": 144,
    "standardized_bonds.csv": 456,
    "paired_metrics.csv": 24,
}


def standardized_bonds(terms):
    """One 1Y zero-coupon anchor and coupon bonds with payments starting at 1Y."""
    face = terms["face_gbp"]
    coupon = face * terms["annual_coupon_decimal"] / terms["payments_per_year"]
    return [
        {
            "maturity": float(maturity), "face": face,
            "semiannual_coupon": 0 if count == 1 else coupon,
            "coupon_count": 0 if count == 1 else count,
        }
        for count, maturity in enumerate(PUBLISHED_GRID, start=1)
    ]


def value_month(day, observations, bonds, terms):
    # A dictionary lookup requires an exact published tenor for every cash flow.
    points = {row["maturity_years"]: row for row in observations}

    def reference(times):
        return np.array([points[float(t)]["zero_rate_decimal"] for t in times])

    prices, valuation = [], []
    for bond in bonds:
        payments = cash_flows(bond)
        dates, amounts = payments
        rates = reference(dates)
        discounts = np.exp(-rates * dates)
        prices.append(present_value(reference, payments))
        for t, amount, rate, discount in zip(dates, amounts, rates, discounts, strict=True):
            valuation.append({
                "as_of_date": day, "bond_maturity_years": bond["maturity"],
                "payment_years": float(t), "cashflow_gbp": float(amount),
                "zero_rate_decimal": float(rate), "discount_factor": float(discount),
                "present_value_gbp": float(amount * discount),
                "source_sheet": points[float(t)]["source_sheet"],
                "source_cell": points[float(t)]["source_cell"],
                "coupon_terms_sha256": terms["sha256"],
                "price_kind": PRICE_KIND,
            })
    return np.array(prices), valuation


def paired_metrics(metrics):
    pairs = defaultdict(dict)
    for row in metrics:
        pairs[row["as_of_date"], row["density"]][row["method"]] = row
    result = []
    for (date, density), pair in pairs.items():
        line, spline = pair["linear"], pair["natural_cubic"]
        result.append({
            "as_of_date": date, "density": density,
            "linear_holdout_price_mae": line["holdout_price_mae"],
            "spline_holdout_price_mae": spline["holdout_price_mae"],
            "mae_delta_spline_minus_linear": spline["holdout_price_mae"] - line["holdout_price_mae"],
            "linear_zero_rate_rmse_bp": line["zero_rate_rmse_bp"],
            "spline_zero_rate_rmse_bp": spline["zero_rate_rmse_bp"],
            "rmse_delta_bp_spline_minus_linear": spline["zero_rate_rmse_bp"] - line["zero_rate_rmse_bp"],
        })
    return result


def run_route_b(source_dir):
    sources, (reference_rates, coverage) = load_inputs(source_dir)
    terms = sources["coupon_terms"]
    observations = defaultdict(list)
    for row in reference_rates:
        observations[row["as_of_date"]].append(row)

    bonds = standardized_bonds(terms)
    tables = {
        "reference_rates.csv": reference_rates,
        "coverage_audit.csv": coverage,
        "cashflow_valuation.csv": [],
        "metrics.csv": [],
        "curves.csv": [],
        "holdout_prices.csv": [],
        "standardized_bonds.csv": [],
    }
    for date, month in observations.items():
        prices, valuation = value_month(date, month, bonds, terms)
        targets = np.array([row["zero_rate_decimal"] for row in month])
        result = evaluate_reference({"as_of_date": date}, bonds, prices, targets, PUBLISHED_GRID)
        for fit in result["metrics.csv"]:
            if not fit["converged"]:
                raise ValueError(
                    f"{date} {fit['density']} {fit['method']} failed: {fit['solver_message']}; "
                    f"max price error={fit['max_train_price_error']:.6g}"
                )
        tables["cashflow_valuation.csv"].extend(valuation)
        tables["metrics.csv"].extend(result["metrics.csv"])
        tables["curves.csv"].extend(result["curves.csv"])
        for file, rows in (
            ("holdout_prices.csv", result["holdout_prices.csv"]),
            ("standardized_bonds.csv", result["simulated_bonds.csv"]),
        ):
            for row in rows:
                row["benchmark_price_gbp"] = row.pop("simulated_price")
                row["price_kind"] = PRICE_KIND
                if file == "standardized_bonds.csv":
                    row["coupon_terms_sha256"] = terms["sha256"]
            tables[file].extend(rows)
    tables["paired_metrics.csv"] = paired_metrics(tables["metrics.csv"])
    return sources, tables


def publish_results(output_dir, sources, tables):
    if {name: len(rows) for name, rows in tables.items()} != EXPECTED_ROWS:
        raise ValueError("Route B result tables do not match the full-year experiment coverage.")
    for name, rows in tables.items():
        for row in rows:
            for field, value in row.items():
                if value is None or value == "" or (isinstance(value, (float, np.floating)) and not np.isfinite(value)):
                    raise ValueError(f"Incomplete output in {name}, field {field}: {row}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir.parent) as temp:
        staged = Path(temp) / "release"
        write_results(staged, tables)
        release = {
            "study_year": STUDY_YEAR,
            "maturity_grid_years": PUBLISHED_GRID.tolist(),
            "first_payment_years": 1.0,
            "holdout_years": list(HOLDOUT),
            "additional_removed_by_density": DENSITIES,
            "methods": list(METHODS),
            "price_kind": PRICE_KIND,
            "sources": sources,
            "files": {
                name: {"rows": len(rows), "sha256": sha256((staged / name).read_bytes()).hexdigest()}
                for name, rows in tables.items()
            },
        }
        (staged / "release.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
        if output_dir.exists():
            if all(
                (output_dir / path.name).is_file()
                and (output_dir / path.name).read_bytes() == path.read_bytes()
                for path in staged.iterdir()
            ):
                return
            raise FileExistsError(f"{output_dir} contains another release; use a new --output-dir.")
        staged.rename(output_dir)


def verify_release(output_dir):
    """Require every table to match the published release before reading it."""
    release = json.loads((output_dir / "release.json").read_text(encoding="utf-8"))
    sources = json.loads((SOURCE_DIR / "sources.json").read_text(encoding="utf-8"))
    if release["sources"] != sources or release["study_year"] != STUDY_YEAR:
        raise ValueError("Route B release source or study year mismatch.")
    if {name: meta["rows"] for name, meta in release["files"].items()} != EXPECTED_ROWS:
        raise ValueError("Route B release is missing expected tables or coverage.")
    for name, meta in release["files"].items():
        verified_payload(output_dir / name, meta["sha256"])
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    try:
        sources, tables = run_route_b(SOURCE_DIR)
        publish_results(args.output_dir, sources, tables)
    except (ValueError, OSError, KeyError) as error:
        print(f"Route B stopped: {error}", file=sys.stderr)
        return 1
    print(
        f"Route B: {len(tables['reference_rates.csv'])} official spot rates, "
        f"{len(tables['metrics.csv'])} converged fits. Results: {args.output_dir.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
