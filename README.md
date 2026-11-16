# Yield Curve Construction with Cubic Splines

**DSC6013 · Group 7: DENG Tianyu; XIA Tianquan; ZHANG Yue; LI Wenhao**

[中文说明](#中文说明)

Given bond prices and future payments, can we recover the zero rates used to discount those payments? When some quotes are withheld, how well do linear interpolation and a natural cubic spline recover the reference curve and reprice the same bonds?

This submission reproduces two examples from Chapter 6 of *Professional Financial Computing Using Excel and VBA* and applies the same pricing and calibration code to Bank of England data. The table below summarises the checked-in results.

| Experiment | Result |
|---|---|
| Textbook three-bond example | Using the textbook's rounded short-end rates, the calibrated two-year zero rate is **2.63125423%**, reproducing the two-year bond price of **114.26**. |
| Textbook eight-bond example | With the shortest maturity set to **1/12 year**, the maximum difference from the eight displayed textbook rates is **0.0486 bp**. The code also runs the printed **0.083-year** convention. |
| UK month-end experiment | All **48 fits** converged across 12 month-ends, 2 quote densities and 2 methods. |
| Matched UK comparisons | The spline had lower **holdout pricing MAE** and **full-grid zero-rate RMSE** in **24/24** comparisons. Its **holdout-maturity zero-rate RMSE** was lower in **20/24**. The four sparse-group exceptions were January, February, May and June. |

## Run the project

Use **Python 3.14.6**, the version used to verify this submission. Run the commands below from the repository root. The two source files under `data/route_b/` are bundled, so rerunning the experiments requires no data download after the Python dependencies are installed.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python run_project.py --output-dir results_check
python -m unittest discover -s tests -v
python tools/check_results.py --results results_check
```

On Windows PowerShell, create the environment with `py -3.14 -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`. The remaining commands are the same.

The checked-in reference outputs are under [`results/`](results/). Git preserves the CSV line endings so the UK release hashes survive a checkout. Keep a rerun in `results_check/` so you can compare the two. If that directory contains a different UK release, pass a new output directory to all commands that read or write results. Differences in Python or library versions can affect the last digits of floating-point results.

To regenerate the textbook curve, monthly paired errors and January rate-error figures, run:

```bash
python tools/make_figures.py --results results_check --output figures_check
```

## Data and provenance

| Input | Source and use |
|---|---|
| [`data/textbook_bonds.json`](data/textbook_bonds.json) | Bond prices, maturities, coupon amounts and reference rates transcribed from textbook Table 6.1 and Figure 6.3. Undisplayed coupon dates in the eight-bond example are reconstructed at six-month intervals. |
| `data/route_b/glcnominalmonthedata.zip` | Pinned archive of the Bank of England's UK government nominal month-end curves. The programme reads the workbook `GLC Nominal month end data_2025 to present.xlsx`, sheet `4. spot curve`, and checks six-month coverage against the short-end spot sheet. |
| `data/route_b/prosp210224.pdf` | UK Debt Management Office prospectus for the 4% Treasury Gilt 2031. Its 4% annual coupon, semiannual payment frequency and £100 face value inform the standardised cash flows. |
| [`data/route_b/sources.json`](data/route_b/sources.json) | Official URLs, source filenames, workbook and worksheet identifiers, rate units, and SHA-256 hashes used to verify the source files. |

The six-month rate is unavailable for July–December 2025 in the source worksheets. We use the common published grid of **19 maturities from 1 to 10 years in half-year increments** in every month. The one-year bond is a zero-coupon anchor with a single £100 payment. The longer standardised bonds pay £2 every six months from year one and repay £100 principal at maturity.

The UK component is a **semi-synthetic experiment**. The spot rates are the Bank of England's published estimates fitted to gilt market data. The reference prices are derived by discounting the project-defined cash flows at those rates. For example, `cashflow_valuation.csv` traces the 2.5-year reference price on 31 January 2025 to four payments and their original rate cells.

## Method and evaluation

1. **Build cash flows.** For each bond, record its payment times in years and the amount paid at each time. Discount each payment by `exp(-r(t) * t)`, where `r(t)` is the continuously compounded annual zero rate in decimal form. Sum the present values to obtain the bond price.
2. **Reproduce the textbook benchmarks.** In the three-bond example, fix the short-end rates and solve for the two-year rate. The rate used to discount the coupon paid at 1.5 years is read from the fitted zero-rate curve. In the eight-bond example, jointly solve for all eight knot rates.
3. **Construct monthly UK reference prices.** Use the published rate at each payment horizon to price the same 19 standardised bonds each month.
4. **Fix the holdouts before calibration.** Score the **2.5-, 5.5- and 8.5-year** bonds at both quote densities. The dense group uses 16 calibration prices. The sparse group drops six additional prices and uses only the ten whole-year maturities. Both methods see the same calibration inputs within a month and density.
5. **Calibrate and score.** Independently solve for the knot rates under linear interpolation and the natural cubic spline. Require solver success and a maximum absolute calibration price residual of at most `1e-8`. Reprice the three unseen bonds and compare fitted zero rates to the published reference rates.

**Holdout pricing MAE** averages absolute price errors for the three holdout bonds, in pounds per £100 face value. **Full-grid zero-rate RMSE** measures the rate error over all 19 published maturities in basis points. **Holdout-maturity zero-rate RMSE** uses the same rate-error calculation at the three holdout maturities only. A negative paired difference in `paired_metrics.csv` means the spline error is smaller.

The comparison applies to the 2025 month-ends, 1–10-year interpolation range, fixed holdouts and standardised cash flows used here. Actual gilt pricing and other markets would require a corresponding dataset and evaluation design.

## Repository map

| Path | What it contains |
|---|---|
| [`run_project.py`](run_project.py) | Entry point for the textbook and UK experiments. |
| [`curve.py`](curve.py) | Cash flow expansion, continuous discounting, interpolation and numerical calibration. |
| [`textbook.py`](textbook.py) | Three- and eight-bond replications, input-precision variants and curve sampling. |
| [`boe_data.py`](boe_data.py) | Source hash checks, workbook and cell validation, and the maturity coverage audit. |
| [`run_route_b.py`](run_route_b.py) | Monthly reference prices, cash flow provenance and verified UK output publication. |
| [`experiment.py`](experiment.py) | Dense and sparse quote sets, fixed holdouts, metrics and CSV output. |
| [`results/textbook/`](results/textbook/) | Benchmark comparison by bond and the 148-point eight-bond curve. |
| [`results/uk/`](results/uk/) | Source rates, coverage, cash flow valuations, standardised bonds, fitted curves, holdout prices, metrics and paired metrics. `release.json` records output row counts and hashes. |
| [`tests/`](tests/) | Regression tests for missing inputs, modified source bytes and result publication. |
| [`tools/check_results.py`](tools/check_results.py), [`tools/make_figures.py`](tools/make_figures.py) | Recompute benchmark and UK metrics from the output tables, and regenerate figures. |

## References

- Tung, Lai, Wong and Ng (2010), *Professional Financial Computing Using Excel and VBA*, Chapter 6, “Yield Curve Construction Using Cubic Spline”, pp. 67–84.
- [Bank of England, Yield curves and archive data](https://www.bankofengland.co.uk/statistics/yield-curves).
- [UK Debt Management Office, 4% Treasury Gilt 2031 issue prospectus](https://www.dmo.gov.uk/media/52dlkrjw/prosp210224.pdf).

## 中文说明

本项目复现教材第 6 章的三债和八债算例，再使用英格兰银行公布的 2025 年月末名义即期利率，比较线性插值与自然三次样条。代码注释和函数文档采用英中双语。

- **教材复现。** 三债用教材舍入后的短端利率，反推出两年期零息利率 **2.63125423%**，模型价回到 **114.26**。八债比较最短期限取 **1/12 年**和 **0.083 年**两种口径。
- **英国实验。** 对每月共同的 **19 个期限**，用官方利率逐笔贴现标准化现金流，计算参考价。固定留出 **2.5、5.5、8.5 年期**三只债券，较密组用 16 个报价校准，较疏组用 10 个。全部 **48 组**拟合收敛。
- **主要结果。** 相同月份和报价密度下，样条的留出定价 MAE 和全 19 点利率 RMSE 在 **24/24** 组比较中更低。只看三个留出期限的利率 RMSE 时，样条在 **20/24** 组中更低。
- **怎么运行。** 在仓库根目录按上方命令建立环境并安装依赖。用 `run_project.py` 复跑、`tools/check_results.py` 核对结果。现有结果见 [`results/`](results/)，数据来源和散列见 [`sources.json`](data/route_b/sources.json)。
