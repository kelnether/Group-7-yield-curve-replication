"""Recompute experiment metrics from bond prices and the rate grid. 从逐券价格和利率网格复算实验指标。"""

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment import HOLDOUT
from run_route_b import verify_release


def read(path):
    """Read CSV rows. 读取 CSV 行。"""
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def check_results(root):
    """Verify textbook outputs and UK metrics and pairings. 核对教材结果，以及每组英国实验的误差和配对。"""
    textbook = read(root / "textbook" / "textbook.csv")
    three = next(r for r in textbook if r["variant"] == "rounded_short_rates" and r["maturity_years"] == "2.0")
    assert abs(float(three["fitted_rate_pct"]) - 2.63125423) < 1e-8
    assert abs(float(three["fitted_price"]) - 114.26) < 1e-8
    eight = [r for r in textbook if r["variant"] == "one_month_1_over_12"]
    assert len(eight) == 8 and max(abs(float(r["rate_difference_bp"])) for r in eight) < 0.05
    assert len(read(root / "textbook" / "textbook_curve.csv")) == 148

    uk = root / "uk"
    verify_release(uk)
    prices, rates, held_rates = defaultdict(list), defaultdict(list), defaultdict(list)
    metrics = read(uk / "metrics.csv")

    # Recalculate price and rate errors directly from the detail tables.
    # 直接从明细计算定价误差和利率误差。
    for row in read(uk / "holdout_prices.csv"):
        key = row["as_of_date"], row["density"], row["method"]
        prices[key].append(abs(float(row["fitted_price"]) - float(row["benchmark_price_gbp"])))
    for row in read(uk / "curves.csv"):
        key = row["as_of_date"], row["density"], row["method"]
        error = (1e4 * (float(row["fitted_rate"]) - float(row["reference_rate"]))) ** 2
        rates[key].append(error)
        if float(row["maturity_years"]) in HOLDOUT:
            held_rates[key].append(error)
    for row in metrics:
        key = row["as_of_date"], row["density"], row["method"]
        assert row["converged"] == "True" and float(row["max_train_price_error"]) <= 1e-8
        assert len(prices[key]) == len(held_rates[key]) == 3 and len(rates[key]) == 19
        assert math.isclose(fmean(prices[key]), float(row["holdout_price_mae"]), abs_tol=1e-12)
        assert math.isclose(math.sqrt(fmean(rates[key])), float(row["zero_rate_rmse_bp"]), abs_tol=1e-10)

    paired = read(uk / "paired_metrics.csv")
    for density in ("dense", "sparse"):
        selected = [row for row in paired if row["density"] == density]
        mae_deltas, rmse_deltas, holdout_exceptions = [], [], []
        for row in selected:
            date = row["as_of_date"]
            spline = date, density, "natural_cubic"
            linear = date, density, "linear"
            mae_delta = fmean(prices[spline]) - fmean(prices[linear])
            rmse_delta = math.sqrt(fmean(rates[spline])) - math.sqrt(fmean(rates[linear]))
            assert math.isclose(mae_delta, float(row["mae_delta_spline_minus_linear"]), abs_tol=1e-12)
            assert math.isclose(rmse_delta, float(row["rmse_delta_bp_spline_minus_linear"]), abs_tol=1e-10)
            mae_deltas.append(mae_delta)
            rmse_deltas.append(rmse_delta)
            if fmean(held_rates[spline]) >= fmean(held_rates[linear]):
                holdout_exceptions.append(date)
        print(f"{density}: MAE {sum(v < 0 for v in mae_deltas)}/12, "
              f"RMSE {sum(v < 0 for v in rmse_deltas)}/12, "
              f"median deltas {median(mae_deltas):.6f}, {median(rmse_deltas):.4f}; "
              f"held-rate exceptions: {', '.join(holdout_exceptions) or 'none'}")
    print(f"Validated two textbook examples and {len(metrics)} UK fits.")


def main():
    """Read the result directory and run the checks. 解析结果目录并执行复核。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    check_results(parser.parse_args().results)


if __name__ == "__main__":
    main()
