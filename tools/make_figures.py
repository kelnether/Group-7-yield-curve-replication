"""Generate experiment figures from a single verified run. 根据同次复跑结果生成实验图表。"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_route_b import verify_release

COLORS = {"linear": "#b75b27", "natural_cubic": "#00796d"}
LABELS = {"linear": "Linear interpolation", "natural_cubic": "Natural cubic spline"}
DENSITIES = {"dense": "Dense", "sparse": "Sparse"}


def read_rows(path):
    """Read a UTF-8 CSV result table. 读取以 UTF-8 保存的结果表。"""
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def save(fig, output):
    """Save at a resolution suitable for reports and printing. 按适合报告和印刷的分辨率保存。"""
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_textbook(results, directory):
    """Plot the calibrated knots and eight-bond spline. 重画八债校准节点和样条曲线。"""
    curve = read_rows(results / "textbook_curve.csv")
    knots = [row for row in read_rows(results / "textbook.csv") if row["variant"] == "one_month_1_over_12"]
    fig, ax = plt.subplots(figsize=(8, 2.7), layout="constrained")
    ax.plot([float(r["maturity_years"]) for r in curve],
            [float(r["fitted_rate_pct"]) for r in curve], color="#00796d")
    ax.scatter([float(r["maturity_years"]) for r in knots],
               [float(r["fitted_rate_pct"]) for r in knots], color="#064c45", s=22, label="Calibrated knots")
    ax.set(xlabel="Maturity (years)", ylabel="Zero rate (%)")
    ax.legend(frameon=False, loc="upper right")
    save(fig, directory / "textbook-curve.png")


def draw_paired(results, directory):
    """Show monthly paired error differences at both quote densities. 显示两种密度的逐月误差差值。"""
    pairs = read_rows(results / "paired_metrics.csv")
    fig, axes = plt.subplots(2, 1, figsize=(8, 4), sharex=True, layout="constrained")
    for ax, field, unit in zip(axes, ("mae_delta_spline_minus_linear", "rmse_delta_bp_spline_minus_linear"),
                               ("Pricing MAE delta (GBP)", "Rate RMSE delta (bp)"), strict=True):
        ax.axhline(0, color="#52666e", linewidth=0.9)
        for density, color in zip(DENSITIES, ("#00796d", "#b75b27"), strict=True):
            values = [float(row[field]) for row in pairs if row["density"] == density]
            ax.plot(range(1, 13), values, "o-", color=color, label=DENSITIES[density], markersize=3)
        ax.set_ylabel(unit)
    axes[0].legend(frameon=False, ncol=2)
    axes[0].set_title("Natural cubic spline minus linear interpolation")
    axes[-1].set(xticks=range(1, 13), xlabel="2025 month")
    save(fig, directory / "monthly-paired-errors.png")


def draw_january(results, directory):
    """Compare January rate errors at both quote densities. 比较一月两档密度的利率误差。"""
    curves = read_rows(results / "curves.csv")
    metrics = read_rows(results / "metrics.csv")
    date = metrics[0]["as_of_date"]
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.7), sharey=True, layout="constrained")
    for ax, density in zip(axes, DENSITIES, strict=True):
        ax.axhline(0, color="#52666e", linewidth=0.9)
        for tenor in (2.5, 5.5, 8.5):
            ax.axvline(tenor, color="#a6b2b7", linewidth=0.8, linestyle=":")
        for method, color in COLORS.items():
            rows = [row for row in curves if row["as_of_date"] == date
                    and row["density"] == density and row["method"] == method]
            ax.plot([float(r["maturity_years"]) for r in rows],
                    [1e4 * (float(r["fitted_rate"]) - float(r["reference_rate"])) for r in rows],
                    "o-", markersize=2.8, color=color, label=LABELS[method])
        ax.set(title=DENSITIES[density], xlabel="Maturity (years)")
    axes[0].set_ylabel("Fitted minus reference (bp)")
    axes[0].legend(frameon=False, fontsize=8, loc="best")
    fig.suptitle(date)
    save(fig, directory / "january-rate-errors.png")


def main():
    """Verify the UK release before building three figures. 校验英国结果清单后生成三张图。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "figures")
    args = parser.parse_args()
    verify_release(args.results / "uk")
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "axes.axisbelow": True, "grid.alpha": 0.24, "font.size": 10,
                         "axes.labelcolor": "#20363b", "text.color": "#20363b"})
    draw_textbook(args.results / "textbook", args.output)
    draw_paired(args.results / "uk", args.output)
    draw_january(args.results / "uk", args.output)


if __name__ == "__main__":
    main()
