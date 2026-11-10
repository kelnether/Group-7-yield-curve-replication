"""Reproduce the textbook examples and return audit rows for the notebook."""

import json
from pathlib import Path

import numpy as np

from curve import calibrate, cash_flows, implied_zero_rate, interpolate, present_value, solve_rates


DATA_PATH = Path(__file__).resolve().parent / "data" / "textbook_bonds.json"


def result_row(example, variant, maturity, role, rate, reference_pct=None, price=None, fitted_price=None):
    rate_pct = float(rate * 100)
    return {
        "example": example,
        "variant": variant,
        "maturity_years": maturity,
        "role": role,
        "fitted_rate_pct": rate_pct,
        "textbook_rate_pct": reference_pct,
        "rate_difference_bp": None if reference_pct is None else (rate_pct - reference_pct) * 100,
        "input_price": price,
        "fitted_price": fitted_price,
        "price_error": None if price is None else fitted_price - price,
    }


def table_example(table):
    bonds = table["bonds"]
    maturities = [bond["maturity"] for bond in bonds]
    long_bond = bonds[-1]
    long_payments = cash_flows(long_bond)
    rounded = np.array(table["rounded_short_rates_pct_used_on_p75"]) / 100
    implied = np.array([
        implied_zero_rate(bond["price"], bond["face"], bond["maturity"])
        for bond in bonds[:2]
    ])
    rows = []
    for variant, short_rates in (("rounded_short_rates", rounded), ("price_implied_short_rates", implied)):
        def make_curve(long_rate):
            return interpolate(maturities, np.r_[short_rates, long_rate], "natural_cubic")

        def residuals(long_rate):
            return np.array([present_value(make_curve(long_rate), long_payments) - long_bond["price"]])

        fit = solve_rates(residuals, short_rates[-1:])
        if not fit.converged:
            raise RuntimeError(f"Table 6.1, {variant}: {fit.solver_message} ({fit.max_price_error:.3g})")
        curve = make_curve(fit.rates)
        for bond, role in zip(bonds, ("short_anchor", "short_anchor", "calibrated_node"), strict=True):
            maturity = bond["maturity"]
            rows.append(result_row(
                "table_6_1", variant, maturity, role, curve(maturity),
                bond["reference_zero_rate_pct"], bond["price"], present_value(curve, cash_flows(bond)),
            ))
        rows.append(result_row("table_6_1", variant, 1.5, "interpolated_payment_date", curve(1.5)))
    return rows


def figure_example(figure):
    source_bonds = figure["bonds"]
    rows = []
    curve_rows = []
    for variant, first_maturity in (
        ("one_month_1_over_12", 1 / 12),
        ("printed_0_083", source_bonds[0]["maturity"]),
    ):
        bonds = [dict(source_bonds[0], maturity=first_maturity), *source_bonds[1:]]
        prices = np.array([bond["price"] for bond in bonds])
        fit = calibrate(bonds, prices, "natural_cubic")
        if not fit.converged:
            raise RuntimeError(f"Figure 6.3, {variant}: {fit.solver_message} ({fit.max_price_error:.3g})")
        maturities = [bond["maturity"] for bond in bonds]
        curve = interpolate(maturities, fit.rates, "natural_cubic")
        for bond, rate in zip(bonds, fit.rates, strict=True):
            rows.append(result_row(
                "figure_6_3", variant, bond["maturity"], "calibrated_node", rate,
                bond["reference_zero_rate_pct"], bond["price"], present_value(curve, cash_flows(bond)),
            ))
        if variant == "one_month_1_over_12":
            # Figure 6.4 uses twenty interior points between each pair of nodes.
            grid = np.concatenate([
                *(np.linspace(left, right, 21, endpoint=False)
                  for left, right in zip(maturities[:-1], maturities[1:], strict=True)),
                [maturities[-1]],
            ])
            curve_rows = [
                {"maturity_years": maturity, "fitted_rate_pct": rate * 100}
                for maturity, rate in zip(grid, curve(grid), strict=True)
            ]
    return rows, curve_rows


def reproduce_examples():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    figure_rows, curve_rows = figure_example(data["figure_6_3"])
    return {
        "textbook.csv": table_example(data["table_6_1"]) + figure_rows,
        "textbook_curve.csv": curve_rows,
    }
