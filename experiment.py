"""Fixed holdouts, model comparison and CSV export. 固定留出、模型比较和 CSV 导出。"""

import csv
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from curve import calibrate, cash_flows, interpolate, present_value


HOLDOUT = (2.5, 5.5, 8.5)
SPARSE_EXTRA = (1.5, 3.5, 4.5, 6.5, 7.5, 9.5)
DENSITIES = {"dense": (), "sparse": SPARSE_EXTRA}
METHODS = ("linear", "natural_cubic")


def partition(maturity, extra_removed):
    """Fixed holdouts take precedence over additional removals. 固定留出优先于额外移除。"""
    if maturity in HOLDOUT:
        return "holdout"
    if maturity in extra_removed:
        return "removed"
    return "train"


def evaluate_reference(scenario, bonds, prices, reference_rates, grid):
    """Use the same prices and holdouts for both interpolators. 对两种方法使用同一批价格和留出债券。"""
    metrics, curves, holdout_prices, standardized_bonds = [], [], [], []
    maturities = np.array([bond["maturity"] for bond in bonds])
    test = np.isin(maturities, HOLDOUT)

    # Split the visible prices first, then use the same training and holdout bonds for both methods.
    # 先划分可见价格，再为两种方法使用同一批训练及留出债券。
    for density, extra_removed in DENSITIES.items():
        partitions = [partition(maturity, extra_removed) for maturity in maturities]
        train = np.array(partitions) == "train"
        train_bonds = [bond for bond, keep in zip(bonds, train, strict=True) if keep]
        test_payments = [cash_flows(bond) for bond, keep in zip(bonds, test, strict=True) if keep]
        training_nodes = np.isin(grid, maturities[train])

        for bond, price, group in zip(bonds, prices, partitions, strict=True):
            standardized_bonds.append({
                **scenario, "density": density, "partition": group,
                **bond, "benchmark_price_gbp": float(price),
            })

        for method in METHODS:
            key = {**scenario, "density": density, "method": method}
            fit = calibrate(train_bonds, prices[train], method)
            fitted_rates = [None] * len(grid)
            fitted_prices = price_errors = [None] * len(HOLDOUT)
            price_mae = rate_rmse = None
            # Score the curve on the common grid and reprice the three held-out bonds.
            # 用统一网格评估整条曲线，同时给三只留出债券重新定价。
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
                **key, "maturity_years": maturity, "benchmark_price_gbp": truth,
                "fitted_price": estimate, "price_error": error,
            } for maturity, truth, estimate, error in zip(
                maturities[test], prices[test], fitted_prices, price_errors, strict=True,
            ))
    return {
        "metrics.csv": metrics,
        "curves.csv": curves,
        "holdout_prices.csv": holdout_prices,
        "standardized_bonds.csv": standardized_bonds,
    }


def write_results(output_dir, tables):
    """Stage the CSVs before replacing each table. 先写暂存文件再替换各表。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as staging:
        for filename, rows in tables.items():
            with (Path(staging) / filename).open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        for filename in tables:
            (Path(staging) / filename).replace(output_dir / filename)
