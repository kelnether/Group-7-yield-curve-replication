"""Run the two textbook examples and the Route A missing-maturity experiment."""

import argparse
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from curve import calibrate, cash_flows, interpolate, present_value
from textbook import reproduce_examples


RESULTS_DIR = Path(__file__).resolve().parent / "results"
MATURITIES = np.arange(1, 21) / 2
GRID = np.linspace(0.5, 10, 191)
HOLDOUT = (2.5, 5.5, 8.5)
SPARSE_EXTRA = (1.5, 3.5, 4.5, 6.5, 7.5, 9.5)
DENSITIES = {"dense": (), "sparse": SPARSE_EXTRA}
METHODS = ("linear", "natural_cubic")


def rising(t):
    return 0.02 + 0.02 * (1 - np.exp(-t / 3))


def inverted(t):
    return 0.06 - rising(t)


def humped(t):
    return 0.02 + 0.02 * (t / 3) * np.exp(1 - t / 3)


REFERENCE_CURVES = {"rising": rising, "inverted": inverted, "humped": humped}


def simulate_bonds(reference):
    bonds = [
        {
            "maturity": float(maturity),
            "face": 100,
            "semiannual_coupon": 0 if half_years == 1 else 2,
            "coupon_count": 0 if half_years == 1 else half_years,
        }
        for half_years, maturity in enumerate(MATURITIES, start=1)
    ]
    prices = np.array([present_value(reference, cash_flows(bond)) for bond in bonds])
    return bonds, prices


def partition(maturity, extra_removed):
    if maturity in HOLDOUT:
        return "holdout"
    if maturity in extra_removed:
        return "removed"
    return "train"


def evaluate_reference(scenario, bonds, prices, reference_rates, grid):
    """Evaluate the same prices and holdouts for both interpolators."""
    metrics, curves, holdout_prices, simulated_bonds = [], [], [], []
    maturities = np.array([bond["maturity"] for bond in bonds])
    test = np.isin(maturities, HOLDOUT)

    for density, extra_removed in DENSITIES.items():
        partitions = [partition(maturity, extra_removed) for maturity in maturities]
        train = np.array(partitions) == "train"
        train_bonds = [bond for bond, keep in zip(bonds, train, strict=True) if keep]
        test_payments = [cash_flows(bond) for bond, keep in zip(bonds, test, strict=True) if keep]
        training_nodes = np.isin(grid, maturities[train])

        for bond, price, group in zip(bonds, prices, partitions, strict=True):
            simulated_bonds.append({
                **scenario, "density": density, "partition": group,
                **bond, "simulated_price": float(price),
            })

        for method in METHODS:
            key = {**scenario, "density": density, "method": method}
            fit = calibrate(train_bonds, prices[train], method)
            fitted_rates = [None] * len(grid)
            fitted_prices = price_errors = [None] * len(HOLDOUT)
            price_mae = rate_rmse = None
            if fit.converged:
                curve = interpolate(maturities[train], fit.rates, method)
                fitted_rates = curve(grid)
                fitted_prices = np.array([present_value(curve, payments) for payments in test_payments])
                price_errors = fitted_prices - prices[test]
                price_mae = float(np.mean(np.abs(price_errors)))
                rate_rmse = float(1e4 * np.sqrt(np.mean((fitted_rates - reference_rates) ** 2)))

            metrics.append({
                **key, "train_count": len(train_bonds), "holdout_count": len(HOLDOUT),
                "converged": fit.converged, "max_train_price_error": fit.max_price_error,
                "holdout_price_mae": price_mae, "zero_rate_rmse_bp": rate_rmse,
                "solver_message": fit.solver_message,
            })
            curves.extend({
                **key, "maturity_years": maturity, "reference_rate": truth,
                "fitted_rate": estimate, "is_training_node": bool(is_node),
            } for maturity, truth, estimate, is_node in zip(
                grid, reference_rates, fitted_rates, training_nodes, strict=True,
            ))
            holdout_prices.extend({
                **key, "maturity_years": maturity, "simulated_price": truth,
                "fitted_price": estimate, "price_error": error,
            } for maturity, truth, estimate, error in zip(
                maturities[test], prices[test], fitted_prices, price_errors, strict=True,
            ))
    return {
        "metrics.csv": metrics,
        "curves.csv": curves,
        "holdout_prices.csv": holdout_prices,
        "simulated_bonds.csv": simulated_bonds,
    }


def run_simulation():
    tables = {}
    for shape, reference in REFERENCE_CURVES.items():
        bonds, prices = simulate_bonds(reference)
        for filename, rows in evaluate_reference(
            {"shape": shape}, bonds, prices, reference(GRID), GRID,
        ).items():
            tables.setdefault(filename, []).extend(rows)
    return tables


def write_results(output_dir, tables):
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as staging:
        for filename, rows in tables.items():
            with (Path(staging) / filename).open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        for filename in tables:
            (Path(staging) / filename).replace(output_dir / filename)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    textbook = reproduce_examples()
    tables = run_simulation()
    write_results(args.output_dir, {**textbook, **tables})
    metrics = tables["metrics.csv"]
    converged = sum(row["converged"] for row in metrics)
    print(f"Textbook: {len(textbook['textbook.csv'])} audit rows. Simulation: {converged}/{len(metrics)} fits converged.")
    print(f"Results written to {args.output_dir.resolve()}")
    return int(converged != len(metrics))


if __name__ == "__main__":
    raise SystemExit(main())
