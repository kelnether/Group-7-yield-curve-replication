"""Bond cash flows, interpolation and price calibration. 债券现金流、插值与价格校准。"""

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline, interp1d
from scipy.optimize import root


PRICE_TOLERANCE = 1e-8


@dataclass
class Calibration:
    """Solver result and convergence diagnostics. 求解结果与收敛诊断。"""
    rates: np.ndarray
    max_price_error: float
    converged: bool
    solver_message: str


def cash_flows(bond):
    """Return payment times in years and cash amounts. 按年返回付款时点及各笔金额。"""
    count = bond["coupon_count"]
    if count == 0:
        return np.array([bond["maturity"]]), np.array([bond["face"]])

    dates = bond["maturity"] - np.arange(count - 1, -1, -1) / 2
    amounts = np.full(count, bond["semiannual_coupon"], dtype=float)
    amounts[-1] += bond["face"]
    return dates, amounts


def present_value(curve, payments):
    """Discount each cash flow at its continuous spot rate and sum. 按各期零息利率连续贴现再加总。"""
    dates, amounts = payments
    return float(amounts @ np.exp(-curve(dates) * dates))


def implied_zero_rate(price, face, maturity):
    """Infer the annual spot rate from a zero-coupon price. 从零息债券报价反算年化利率。"""
    return -np.log(price / face) / maturity


def interpolate(maturities, rates, method):
    """Select linear or natural cubic interpolation within the knot domain. 在线性与自然三次样条中选择，限节点区间。"""
    if method == "natural_cubic":
        return CubicSpline(maturities, rates, bc_type="natural", extrapolate=False)
    if method == "linear":
        return interp1d(maturities, rates, kind="linear", bounds_error=True, assume_sorted=True)
    raise ValueError(f"Unknown interpolation method: {method}")


def solve_rates(residuals, starting_rates):
    """Find a root of the price residuals and check the maximum absolute error. 求价格残差的根并核查最大绝对误差。"""
    result = root(residuals, starting_rates, method="hybr", tol=1e-10)
    max_error = float(np.max(np.abs(result.fun)))
    converged = bool(result.success and np.isfinite(max_error) and max_error <= PRICE_TOLERANCE)
    return Calibration(result.x, max_error, converged, str(result.message))


def calibrate(bonds, prices, method):
    """Solve one spot-rate knot per visible bond. 仅用可见债券价格求每个到期节点的零息利率。"""
    maturities = np.array([bond["maturity"] for bond in bonds])
    payments = [cash_flows(bond) for bond in bonds]
    if bonds[0]["coupon_count"] != 0 or not np.all(np.diff(maturities) > 0):
        raise ValueError("Calibration requires increasing maturities and a shortest zero-coupon bond.")

    def residuals(rates):
        """Map current knots to model-minus-input prices. 将当前利率节点转换成模型价与输入价之差。"""
        curve = interpolate(maturities, rates, method)
        return np.array([present_value(curve, payment) for payment in payments]) - prices

    initial_rate = implied_zero_rate(prices[0], bonds[0]["face"], maturities[0])
    return solve_rates(residuals, np.full(len(bonds), initial_rate))
