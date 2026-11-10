"""Cash flows, interpolation, and price calibration shared by both experiments."""

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline, interp1d
from scipy.optimize import root


PRICE_TOLERANCE = 1e-8


@dataclass
class Calibration:
    rates: np.ndarray
    max_price_error: float
    converged: bool
    solver_message: str


def cash_flows(bond):
    """Return payment dates in years and currency amounts per bond."""
    count = bond["coupon_count"]
    if count == 0:
        return np.array([bond["maturity"]]), np.array([bond["face"]])

    dates = bond["maturity"] - np.arange(count - 1, -1, -1) / 2
    amounts = np.full(count, bond["semiannual_coupon"], dtype=float)
    amounts[-1] += bond["face"]
    return dates, amounts


def present_value(curve, payments):
    dates, amounts = payments
    return float(amounts @ np.exp(-curve(dates) * dates))


def implied_zero_rate(price, face, maturity):
    return -np.log(price / face) / maturity


def interpolate(maturities, rates, method):
    if method == "natural_cubic":
        return CubicSpline(maturities, rates, bc_type="natural", extrapolate=False)
    if method == "linear":
        return interp1d(maturities, rates, kind="linear", bounds_error=True, assume_sorted=True)
    raise ValueError(f"Unknown interpolation method: {method}")


def solve_rates(residuals, starting_rates):
    result = root(residuals, starting_rates, method="hybr", tol=1e-10)
    max_error = float(np.max(np.abs(result.fun)))
    converged = bool(result.success and np.isfinite(max_error) and max_error <= PRICE_TOLERANCE)
    return Calibration(result.x, max_error, converged, str(result.message))


def calibrate(bonds, prices, method):
    """Solve a zero-rate node at each maturity using only the supplied bonds."""
    maturities = np.array([bond["maturity"] for bond in bonds])
    payments = [cash_flows(bond) for bond in bonds]
    if bonds[0]["coupon_count"] != 0 or not np.all(np.diff(maturities) > 0):
        raise ValueError("Calibration requires increasing maturities and a shortest zero-coupon bond.")

    def residuals(rates):
        curve = interpolate(maturities, rates, method)
        return np.array([present_value(curve, payment) for payment in payments]) - prices

    initial_rate = implied_zero_rate(prices[0], bonds[0]["face"], maturities[0])
    return solve_rates(residuals, np.full(len(bonds), initial_rate))
