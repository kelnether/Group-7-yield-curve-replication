# 路线 A 三次样条收益率曲线复现说明

本文是路线 A 的技术手册。债券入门、安装和四人协作见 [项目首页](README.md)，官方数据接入和再应用见 [路线 B 使用说明](ROUTE_B.md)。

## 01 项目速览与运行

这个项目从**债券价格和付款安排**反推**零息利率曲线（zero-coupon yield curve）**。先重做教材算例，确认实现正确，再用模拟数据比较缺少中间期限报价时，线性插值与自然三次样条能把曲线和债券价格恢复到什么程度。

| 做了什么 | 怎么做 | 去哪里看 |
| --- | --- | --- |
| 复现教材的两组债券 | 录入表 6.1 的三只债券和图 6.3 的八只债券，校准利率节点，并重画图 6.4。 | `textbook.py`、`textbook.csv` |
| 测试缺少报价时的表现 | 用三条已知曲线生成价格。设两档报价密度，用两种插值各自校准，共 12 组。 | `run_experiment.py`、`metrics.csv` |
| 展示曲线和误差 | 读取同一批 CSV，展示参考曲线、拟合曲线、误差图和逐券价格。 | `results.ipynb` |

```text
教材数据 → 校准利率 → 与书中数值核对 → 重画教材曲线
参考曲线 → 生成模拟价格 → 留出部分债券 → 校准 → 比较误差
两条流程 → results/ 的 CSV → results.ipynb 的图表
```

**已验证结果**　三债例的 2 年期零息利率复现为 2.63125423%。在本项目的六个模拟配对中，样条的留出定价 MAE 和利率 RMSE 均低于线性插值。

### 从头运行

在终端进入项目的 `route_a` 目录，使用 Python 3.10 或更新版本。若已有安装好依赖的环境，可以直接运行后两行。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run_experiment.py
python -m jupyterlab results.ipynb
```

Windows PowerShell 将第二行换成 `.\.venv\Scripts\Activate.ps1`。脚本完成后，在 JupyterLab 中选择当前环境的 Python 内核，运行所有单元格。

**成功运行时**，终端报告教材核对表有 24 行、模拟校准 12/12 组收敛。默认输出写入项目下的 `results/`。要保留旧结果，可以运行 `python run_experiment.py --output-dir other_results`。Notebook 默认读取 `results/`，要查看另一个目录的结果，可修改第一个代码单元的 `results_dir`。

**阅读顺序**　02–04 节解释数据与方法，05–07 节按文件介绍每个函数，08–09 节是结果表字典，10 节说明 Notebook 和组内协作。

## 02 教材数据的来源与结构

原始材料为 *Professional Financial Computing Using Excel and VBA* 第 6 章 *Yield Curve Construction Using Cubic Spline*。项目从所提供的章节 PDF 录入数值。章末提到的 `yield_curve.xls` 未随章节附件提供，两组示例也没有注明市场报价日期。

| JSON 数据组 | 原文位置与内容 |
| --- | --- |
| `table_6_1` | 书页 67–68，PDF 第 1–2 页。表 6.1 给出三只债券，式（6.1）列出两年期债券的现金流。书页 75 的式（6.8）和正文给出校准方法及精确结果。 |
| `figure_6_3` | 书页 78，PDF 第 12 页。图 6.3 的 Excel 截图显示八只债券的输入及零息利率输出。书页 79 的图 6.4 是用这些节点生成的曲线。 |

`data/textbook_bonds.json` 的顶层有 `source`、`units` 及两组数据。每组的 `bonds` 是债券对象列表，`source_location` 标注出处。三债组另存 `rounded_short_rates_pct_used_on_p75`，八债组另有 `notes` 记录期限精度及付息日程的重建依据。

| 每只债券的字段 | 含义与用法 |
| --- | --- |
| `maturity` | 到期时间，以年计。也是候选曲线节点的横坐标。 |
| `price` | 教材给定的每只债券价格，用作价格校准目标。 |
| `face` | 面值（face value）。两组均为 100，到期加到最后一笔现金流。 |
| `semiannual_coupon` | 每半年支付的票息金额（coupon payment）。例如 5 表示每次支付 5。 |
| `coupon_count` | 付息次数。0 表示中间无票息，仍有到期本金。 |
| `reference_zero_rate_pct` | 教材的零息利率参考值，以百分数保存。通常用于核对输出。三债例固定的舍入短端利率另有专用字段。 |

### 读一行数据

三债例的两年期债券是 `maturity=2`、`price=114.26`、`face=100`、`semiannual_coupon=5`、`coupon_count=4`。它在 0.5、1、1.5、2 年支付 5、5、5、105。1.5 年有现金流，但表中没有同期限的债券报价。该债券在表 6.1 的利率列显示 2.63%，JSON 用书页 75 的精确结果 2.63125423% 作核对值。

八债例的期限为 0.083、0.25、0.5、1、2、4、7.5、18 年。前四只是零息债券，后四只半年付息。截图右侧未显示完的付款日按半年间隔重建。最短期限保留图示 `0.083`，程序另以 `1/12` 年做一次敏感度核对。

## 03 模拟数据的生成

### 先给定一条可核对的参考曲线

`run_experiment.py` 用下面三个函数生成参考零息利率。`t` 是年数，可传入单个期限或 NumPy 数组。函数返回连续复利（continuous compounding）的年化小数，例如 `0.03` 表示 3%。每种形状独立生成一组价格。

```python
def rising(t):
    return 0.02 + 0.02 * (1 - np.exp(-t / 3))

def inverted(t):
    return 0.06 - rising(t)

def humped(t):
    return 0.02 + 0.02 * (t / 3) * np.exp(1 - t / 3)
```

`rising` 随期限上升，`inverted` 随期限下降，`humped` 在 3 年处达到峰值。三条参考曲线由公式直接定义，便于独立检验线性和样条的拟合结果。生成过程没有抽样或报价噪声，同一实现重复运行使用同一批价格。

### 再把参考利率换成债券价格

`simulate_bonds(reference)` 遍历 `MATURITIES = np.arange(1, 21) / 2`，得到从 0.5 到 10 年的 20 个期限。`enumerate(..., start=1)` 同时给出到期前经过的半年数。每只债券的面值设为 100，半年期只还本金，其余每半年付 2，到期付 102。

```python
# simulate_bonds() 生成债券对象时采用的两项规则
"semiannual_coupon": 0 if half_years == 1 else 2,
"coupon_count": 0 if half_years == 1 else half_years,

# 根据参考曲线计算每只债券的价格
prices = np.array([
    present_value(reference, cash_flows(bond))
    for bond in bonds
])
```

`cash_flows()` 生成付款时间和金额。`present_value()` 在每个付款日期取参考利率，逐笔贴现后加总，得到与债券列表同序的 `prices` 数组。例如，上升曲线下的 2.5 年期债券在 0.5、1、1.5、2、2.5 年分别付 2、2、2、2、102，生成价格约为 **102.049925**。两个报价密度共用这个模拟价格，变化的是拟合时能看到哪些报价。

## 04 校准与比较的方法

### 固定测试集

| 报价密度 | 校准节点数 | 留出和额外移除规则 |
| --- | --- | --- |
| `dense` 较密 | 17 | 固定测试债券为 2.5、5.5、8.5 年。其余全部用于校准。 |
| `sparse` 较疏 | 11 | 测试集相同。另将 1.5、3.5、4.5、6.5、7.5、9.5 年从校准集中移除。 |

两档都保留 0.5 年零息债券和 10 年端点。移除某个期限的**债券报价**，其他债券在那个时间的票息仍要照常贴现。额外移除的六只债券只改变报价密度。

### 每种插值都单独校准

给定一组候选的节点利率，先插出各付款时间的利率，再算每只训练债券的模型价格。设第 $j$ 笔付款为 $CF_j$，付款时间为 $t_j$，价格公式为

$$
P_{\mathrm{model}}=\sum_{j=1}^{n}CF_j e^{-r(t_j)t_j}.
$$

求解器反复调整节点利率，目标是让每只训练债券的模型价格等于输入价格。线性插值（linear interpolation）用直线连接节点，自然三次样条（natural cubic spline）用平滑的分段三次曲线连接，且两端二阶导数为零。两种方法共用训练价格、现金流、初始值和收敛判据，各自求出节点利率。

### 三项指标各回答一个问题

| 指标 | 计算方法与单位 |
| --- | --- |
| 训练最大绝对价格残差 | 对训练债券取 $\lvert P_{\mathrm{model}}-P_{\mathrm{input}}\rvert$ 的最大值。用来判断价格是否还原，门槛为 $10^{-8}$。 |
| 留出定价 MAE | 对同三只测试债券取模型价与模拟价之差的绝对值，再平均。单位是每只面值 100 的债券的价格金额。 |
| 零息利率 RMSE | 在 0.5 至 10 年的 191 个共同网格点上，计算拟合与参考利率之差的均方根。内部是小数，乘 10,000 后以基点（bp）报告。 |

只有训练债券及对应价格进入 `calibrate()`。留出价格用于验证定价，参考利率用于评价曲线恢复。1 bp 等于 0.01 个百分点。训练残差接近零只说明已匹配输入价格。

## 05 定价与校准模块

`curve.py` 是两条工作流程共用的计算模块。它从债券对象生成现金流，把一组节点变成可查询的曲线，再用价格反求节点利率。

| 函数或对象 | 输入、处理与返回 |
| --- | --- |
| `cash_flows(bond)` | 输入一只债券对象，返回 `(dates, amounts)` 两个数组。零息债券返回到期时间和本金。付息债券从到期日按半年向前排出 `coupon_count` 个时间，按每期票息填入金额，最后一笔加面值。 |
| `present_value(curve, payments)` | 输入可调用的利率曲线和现金流数组。对每个付款时点计算贴现因子，再用 NumPy 点积将所有现值加总，返回一个价格。教材复现、模拟价格生成和留出定价都调用它。 |
| `implied_zero_rate(price, face, maturity)` | 输入零息债券价格、面值和年期限，按 $r=-\ln(P/F)/T$ 反推连续复利利率。返回年化小数。 |
| `interpolate(maturities, rates, method)` | 输入同序的期限和节点利率。`linear` 使用 `interp1d`，`natural_cubic` 使用 `CubicSpline` 并设 `bc_type="natural"`。返回可查询任意区间内付款日利率的函数对象。实现关闭样条外推，线性超界时会报错。 |
| `solve_rates(residuals, starting_rates)` | 输入价格残差函数和节点初值。用 SciPy `root` 的 `hybr` 方法，求解器的 `tol` 为 `1e-10`。只有求解器报告成功、最大残差有限且不超过 `PRICE_TOLERANCE`，结果才标为收敛。原文的求解器采用 VBA 牛顿法。 |
| `calibrate(bonds, prices, method)` | 输入按期限升序排列的债券、对齐的价格和方法。先生成现金流并检查最短债券为零息。用最短债券隐含利率初始化所有节点，再调用 `solve_rates()`。返回一组利率和求解诊断。 |
| `Calibration` | 数据类。`rates` 是节点利率数组，`max_price_error` 是最大价格残差，`converged` 是按本项目阈值判定的成功标记，`solver_message` 是求解器原始消息。 |

`calibrate()` 内部的 `residuals(rates)` 接受一组候选节点，调用 `interpolate()` 构造曲线，逐只定价后返回**模型价减输入价**的向量。一只训练债券对应一个残差，求解器把它们一起压到接近零。模拟实验传入的节点数量是 17 或 11，八债例传入 8 个。

## 06 教材复现模块

`textbook.py` 读取教材 JSON，复用 `curve.py`，输出教材对照表和重画曲线的坐标。`DATA_PATH` 以模块所在位置定位输入文件，运行目录变化时也能找到 JSON。

| 函数 | 输入、处理与返回 |
| --- | --- |
| `result_row(...)` | 将单个期限的期限、角色、复算利率、原文参考值、输入和模型价格写成字典。把年化小数乘 100 转成百分数，将利率差换算为基点。有价格时保存有符号价格误差。 |
| `table_example(table)` | 输入 `table_6_1` 数据组。两种短端口径分别固定前两个利率，只求使两年期债券价格等于 114.26 的第三个利率。每种口径输出三只债券和 1.5 年付款日，共 4 行。 |
| `figure_example(figure)` | 输入 `figure_6_3` 数据组。分别将最短期限按 1/12 年与 0.083 年处理，用 `calibrate()` 各求出 8 个节点。返回 16 行核对记录和 1/12 年版本的绘图点。 |
| `reproduce_examples()` | 读取 JSON，运行前两个算例函数，返回以 CSV 文件名为键的字典。入口脚本统一写文件。 |

### 三只债券的局部求解

`table_example()` 内的 `make_curve(long_rate)` 把两个固定短端利率和候选两年期利率合成样条。局部 `residuals(long_rate)` 只计算两年期的模型价减 114.26。每次调整两年期节点时，1.5 年利率也会随样条一起更新。

| 短端口径 | 2 年期复算利率 | 如何解释 |
| --- | --- | --- |
| `rounded_short_rates` | 2.63125423% | 固定教材的 2.13% 和 2.38%。半年和 1 年价格残差可能因舍入而略偏离零。 |
| `price_implied_short_rates` | 2.63135786% | 用 JSON 的 98.94 和 97.65 反推短端利率，再校准两年期。 |

在八债例中，图示的 0.083 年重算得到最短利率约 4.4661%，按一个月 1/12 年得到约 4.4482%。后者的八个节点均与图示利率相差不到 0.05 bp。重画图 6.4 时，每个相邻节点间取 20 个内部点，加上 8 个节点共 **148 点**。教材算例若校准失败会抛出错误，中止整次运行。

## 07 实验入口与流程控制

`run_experiment.py` 把配置、模拟、校准、评价与导出串起来。`REFERENCE_CURVES` 是曲线名到生成函数的映射。`DENSITIES` 存放每档额外移除的期限，`METHODS` 列出两种插值法，`HOLDOUT` 存放固定测试期限，`GRID` 是两种方法共用的评价网格。

| 函数 | 输入、处理与返回 |
| --- | --- |
| `rising(t)` | 上升情景。返回随期限从低向高变化的参考利率。 |
| `inverted(t)` | 倒挂情景。用 `0.06 - rising(t)` 构造从高向低的参考利率。 |
| `humped(t)` | 驼峰情景。返回中间期限较高、长端回落的参考利率。 |
| `simulate_bonds(reference)` | 输入一条参考曲线，返回 20 只债券的列表及同序价格数组。现金流规则见 03 节。 |
| `partition(maturity, extra_removed)` | 输入一只债券期限和本档额外移除列表。先查固定测试集，再查额外移除列表，返回 `holdout`、`removed` 或 `train`。 |
| `evaluate_reference(scenario, bonds, prices, reference_rates, grid)` | 接收一组债券及其对齐的价格数组、共同网格上的参考利率、网格和情景标识。用固定规则划分训练与留出，再分别校准两种方法，返回四张结果表。路线 A 和 B 共用此函数。 |
| `run_simulation()` | 遍历三条解析参考曲线，生成各自的债券价格，调用 `evaluate_reference()`，合并三种情景的四张模拟结果表。 |
| `write_results(output_dir, tables)` | 创建目标目录。先把各表写入该目录下的临时目录，再将生成好的 CSV 逐一替换到目标位置。文件使用 UTF-8，每列名取自表的首行字段。 |
| `main()` | 读取可选的 `--output-dir`，执行教材复现和模拟，合并六张表后写出，打印行数、收敛数和输出目录。全部模拟组收敛时返回 0，否则返回 1。 |

### 核心循环如何使用数据

1. **按曲线生成价格。** 每种形状只生成一次 20 只债券及价格，随后在两档报价密度间复用。
2. **按报价密度划分。** 用 `partition()` 形成训练掩码，固定测试掩码。保存分组供复查。
3. **按方法校准。** 用 `calibrate(train_bonds, prices[train], method)` 训练。成功时，在统一网格上生成拟合利率，并用留出债券现金流算模型价格。
4. **写明成功与失败。** 每组都保留求解状态和训练最大残差。若模拟组未收敛，其曲线估计、留出估价和误差指标留空，参考利率与模拟价格仍保留以便排查。

直接执行文件时，`if __name__ == "__main__"` 将 `main()` 的返回值传给 `SystemExit`。导入模块时可以复用函数。

## 08 数据与曲线文件字典

下列行数为当前配置下的数据行数，均不含 CSV 表头。`results/` 可以由入口脚本重新生成。

| 文件 | 一行代表什么 | 当前行数 |
| --- | --- | --- |
| `textbook.csv` | 一个教材算例版本中的一个期限。 | 24 |
| `textbook_curve.csv` | 图 6.4 复现曲线的一个绘图点。 | 148 |
| `simulated_bonds.csv` | 一条参考曲线、一档密度下的一只模拟债券。 | 120 |
| `curves.csv` | 一组拟合结果在一个期限网格点上的利率。 | 2,292 |

### 教材核对表与绘图点

`textbook.csv` 用 `example` 区分 `table_6_1` 和 `figure_6_3`，用 `variant` 区分各自的两个重算版本。`maturity_years` 为年数，`role` 标识短端锚点（`short_anchor`）、校准节点（`calibrated_node`）或仅插值的付息日（`interpolated_payment_date`）。`fitted_rate_pct` 和 `textbook_rate_pct` 是百分数，`rate_difference_bp` 是前者减后者后的基点差。

`input_price` 是教材价格，`fitted_price` 是重算价格，`price_error` 是重算减教材。三债例的 1.5 年行只对应付款日，原文价格和参考利率留空。`textbook_curve.csv` 只有 `maturity_years` 和 `fitted_rate_pct`，取八债例 1/12 年版本供重画曲线。

### 模拟债券与利率网格

`simulated_bonds.csv` 的 `shape` 和 `density` 是参考曲线与报价密度。`partition` 记录 `train`、`holdout` 或 `removed`。`maturity`、`face`、`semiannual_coupon`、`coupon_count` 描述债券，`simulated_price` 由参考曲线生成。三种形状各有 20 只债券，两个报价密度各存一次，合计 120 行。同形状、同期限的模拟价格在两档密度里相同。

`curves.csv` 用 `shape`、`density`、`method` 标记实验组。`maturity_years` 是 191 点网格上的年期限。`reference_rate` 与 `fitted_rate` 均为年化小数，画百分比图时乘 100，计算基点误差时将差值乘 10,000。`is_training_node` 表示该网格点是否也是校准用债券的到期节点。每组 191 行，12 组共 2,292 行。

## 09 指标与逐券结果文件字典

### 查看每组的整体误差

`metrics.csv` 有 12 行，每行由 `shape`、`density`、`method` 确定。`shape` 取 `rising`、`inverted`、`humped`，`density` 取 `dense`、`sparse`，`method` 取 `linear`、`natural_cubic`。

| 字段 | 怎么读 |
| --- | --- |
| `train_count`、`holdout_count` | 校准用债券数和固定测试债券数。训练数为 17 或 11，测试数为 3。 |
| `converged` | 求解成功且残差通过门槛时为 `True`。 |
| `max_train_price_error` | 训练债券的最大绝对价格残差。 |
| `holdout_price_mae` | 留出债券的平均绝对定价误差。 |
| `zero_rate_rmse_bp` | 共同网格上参考与拟合利率的 RMSE，单位为基点。 |
| `solver_message` | SciPy 求解器消息，用来诊断未收敛情形。 |

### 查到误差来自哪只债券

`holdout_prices.csv` 每组 3 行，共 36 行。通过 `shape`、`density`、`method` 与指标表匹配，再按 `maturity_years` 找到 2.5、5.5 或 8.5 年的债券。`simulated_price` 是生成价格，`fitted_price` 是用拟合曲线折现同一只债券的全部付款得到的估价。`price_error` 保留正负号，等于拟合价减模拟价。对这三行的 `price_error` 取绝对值再平均，即可复算指标表的 MAE。

### 当前结果示例

| 驼峰曲线与稀疏报价 | 留出定价 MAE | 零息利率 RMSE |
| --- | --- | --- |
| 线性插值 | 0.040789 | 1.9555 bp |
| 自然三次样条 | 0.002408 | 0.2916 bp |

当前最大训练残差约为 $1.64\times10^{-10}$。从较密切换到较疏时，两种方法的利率 RMSE 在三种形状下都上升，但线性的留出定价 MAE 略降。曲线误差衡量整段期限，留出定价只衡量三只债券，且同一只债券的各笔现金流折现误差可能相互抵消。该比较对应本项目设定的平滑参考曲线、固定留出期限和无噪声价格。

## 10 Notebook 与四人协作

`results.ipynb` 负责读取和解释结果。代码单元用 pandas 组织表格、用 Matplotlib 绘图。要更改模型或实验参数，请修改对应的 Python 文件并重跑入口，再刷新 Notebook。

| 代码单元 | 读什么与展示什么 |
| --- | --- |
| 1　加载数据 | 检查 `metrics.csv` 是否存在，读取教材核对表、教材绘图点、实验指标、曲线与留出债券估价。 |
| 2　复核教材 | 列出三债例的两个短端口径和八债例的节点对照，展示最短期限按 0.083 年时的复算利率，重画图 6.4。 |
| 3　查看误差表 | 汇报收敛组数，展示 12 组训练最大残差、留出定价 MAE 和利率 RMSE。 |
| 4　查看一条拟合曲线 | 用稀疏报价的驼峰案例叠加参考、线性和样条曲线，标出样条训练节点。 |
| 5　查看六组期限误差 | 画出三种参考形状和两档密度下两种方法的有符号利率误差。竖虚线标记测试债券到期日。 |
| 6　比较与追查 | 用 `pivot()` 配对两种方法，仅比较两者都有结果的组，统计样条误差较低的次数，并列出稀疏驼峰案例的逐券估价。 |

### 按任务定位文件

| 成员负责的工作 | 主要文件 |
| --- | --- |
| 教材数据核对 | `data/textbook_bonds.json`、`textbook.py` |
| 定价和校准 | `curve.py` |
| 数据生成与评估 | `run_experiment.py` |
| 结果解释和图表 | `results.ipynb` |

`requirements.txt` 声明依赖。NumPy 和 SciPy 用于运算与求解，pandas、Matplotlib、JupyterLab 和 ipykernel 用于读取与展示。`.gitignore` 排除虚拟环境、缓存、Notebook 检查点和可重新生成的 `results/`。若用 Git 协作，建议由一位组员维护 Notebook，合并变动后重跑命令行和 Notebook，核对报告引用的是同一次运行。
