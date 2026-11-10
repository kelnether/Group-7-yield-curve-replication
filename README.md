# 三次样条收益率曲线的复现与再应用

**从几只债券的价格，反推一整条零息利率曲线。** 这个项目先复现 Tung、Lai、Wong 和 Ng 的教材 *Professional Financial Computing Using Excel and VBA* 第 6 章 *Yield Curve Construction Using Cubic Spline*（2010，页 67–84），再用英格兰银行的月末曲线检验同一种方法。适合第一次接触债券、会用 Python 的同学。[Wiley 教材目录](https://onlinelibrary.wiley.com/doi/book/10.1002/9781118390405)

| 路线 | 做了什么 | 先看哪里 |
| --- | --- | --- |
| **A · 原文复现与受控实验** | 重做教材的 3 只和 8 只债券算例。用三条明确写出公式的参考曲线，比较缺少中间期限报价时的两种插值方法。 | [路线 A 逐函数说明](ROUTE_A.md) · [路线 A Notebook](results.ipynb) |
| **B · 英国市场基准再应用** | 使用 2025 年 12 个月末、228 个英格兰银行公布的零息利率。先算出标准化债券的参考价格，再比较两种方法如何从稀疏价格恢复曲线。 | [路线 B 数据与代码说明](ROUTE_B.md) · [路线 B Notebook](results_b.ipynb) |

**先记住两个数。** 路线 A 重现教材的 **2 年期零息利率 2.63125423%**。路线 B 的 **48 组校准全部收敛**，在两档报价密度下，样条各有 **12/12 个月**的留出定价 MAE 和利率 RMSE 都比线性插值低。结果适用于本实验指定的样本和现金流规则。

## 1 从一只债券理解整个项目

### 债券价格是几笔未来收入的现值

假设你买入教材里价格为 **114.26** 的两年期债券。你今天付出 114.26，接下来每半年收到 5 元票息（coupon）。满两年时，还能收回面值（face value）100 元。

| 距今天的年数 | 0.5 | 1.0 | 1.5 | 2.0 |
| --- | ---: | ---: | ---: | ---: |
| 收到的金额 | 5 | 5 | 5 | 105 |

最后一笔 105 包含票息和本金。把不同日期的收款折算成今天的价值叫**贴现（discounting）**。每笔付款用它自己那个期限的利率。设未来付款金额为 $CF_j$，距定价日 $t_j$ 年，模型价格为

$$
P=\sum_j CF_j\,e^{-r(t_j)t_j}.
$$

这里的 $r(t)$ 是年化的**零息利率（zero rate / spot rate）**，用于贴现 $t$ 年后的单笔收入。票息 5 是合同规定的收款金额，零息利率是用来换算现值的利率。程序里百分数 2.13% 写成小数 `0.0213`。

**最简单的例子**是教材里价格 98.94 的半年期零息债券。它在半年后一次性还 100，所以 $98.94=100e^{-r(0.5)\times0.5}$。反推得到半年期利率约 **2.1313%**。这个例子只需要一个期限的利率。

### 为什么要用插值和校准

教材有 0.5、1、2 年的债券价格，2 年期债券却在 **1.5 年**也要付息。模型因此需要补出 1.5 年的零息利率。**线性插值（linear interpolation）**用直线连接已知节点，**自然三次样条（natural cubic spline）**用平滑的分段三次曲线连接节点，两端的二阶导数为零。

节点利率通常也要从债券价格反推。程序先猜一组节点利率，用相应的插值给每笔现金流定价，再调整节点，让模型价格贴近输入价格。这个过程叫**价格校准（price calibration）**。线性法和样条法各自校准一组节点。

### 怎么知道补得好不好

**留出（holdout）**一只债券，就是把它的价格藏起来，用其他可见债券校准曲线，最后再给这只债券定价。比如隐藏 2.5 年期债券的报价后，期限更长的债券仍可能在 2.5 年付息，这笔钱仍须用模型估计的 2.5 年利率来折现。

| 指标 | 初学者可以怎样读 |
| --- | --- |
| 训练最大绝对价格残差 | 输入价格还原得有多准。它主要检查求解是否成功，不能单独说明缺失期限估得准。 |
| 留出定价 MAE | 三只留出债券的平均绝对定价差。路线 B 按每 £100 面值的价格金额计，越小越好。 |
| 零息利率 RMSE | 在共同期限点上，将曲线利率差平方后取平均再开方。以基点（bp）计，越小越好。1 bp 等于 0.01 个百分点。 |

## 2 两条路线如何衔接

### 路线 A 先验证实现

1. **教材算例。** `data/textbook_bonds.json` 记录第 6 章表 6.1 和图 6.3 的数据、书页和原文利率。三债例用教材舍入后的短端利率重现两年期结果。八债例核对节点与定价残差，并重画图 6.4。
2. **受控实验。** 代码明确给出上升、倒挂和驼峰三条解析曲线，按公式生成参考价格。这三个情景用于检验算法。期限为 0.5–10 年，三条曲线、两档报价密度、两种方法共 12 组。
3. **查看结果。** 先看 `results/textbook.csv` 的三债和八债核对，再看 `results/metrics.csv` 的模拟指标。A 的 Notebook 里有教材曲线和各情景的误差图。

[路线 A 的完整方法、函数和表字段](ROUTE_A.md)

### 路线 B 把参考曲线换成市场基准

英格兰银行（Bank of England，BoE）公布的英国国债**名义即期利率（nominal spot rates）**是基于市场数据拟合的曲线估计，采用连续复利年化口径。我们用发布的利率折现标准化债券的每笔现金流，得到**衍生参考价格**。常规年票息 4%、半年付款频率和 £100 计价面值取自英国债务管理办公室（UK DMO）的 4% Treasury Gilt 2031 发行文件。实验各期限的付款安排按统一规则构造，属于**半合成实验（semi-synthetic experiment）**。[英格兰银行数据与方法](https://www.bankofengland.co.uk/statistics/yield-curves) · [UK DMO 发行文件](https://www.dmo.gov.uk/media/52dlkrjw/prosp210224.pdf)

原始档案中 2025 年 7–12 月的半年期利率在两张即期表都为空。B 因此用全年完整的 **1、1.5、2，直至 10 年**共 19 个期限。1 年期到期付 £100，更长期限的标准化债券从第 1 年起每半年付 £2，到期另还 £100。全年保留 12 个官方月末截面，输入利率没有填补值。

| 一条路线 B 记录怎样追溯 | 示例 |
| --- | --- |
| 原始发布值 | 2025-01-31、1 年期，来自工作表 `4. spot curve` 的 `C5`，原值约 4.069581%。 |
| 程序输入 | 除以 100 后约为 `0.04069581`，保留完整精度。 |
| 衍生参考价格 | 将一年后收到的 £100 按该利率贴现，约为 **£96.0121**。 |
| 输出位置 | `reference_rates.csv` 记录源单元格和原值，`cashflow_valuation.csv` 记录贴现因子及每笔现值，`standardized_bonds.csv` 记录合计价格。 |

每个月单独运行。两档都留出 **2.5、5.5、8.5 年**。较密组用 16 只债券校准，较疏组额外移除六个中间期限后用 10 只。两种方法看到相同的输入。B 在 19 个官方期限上计算利率 RMSE，A 的原实验使用 191 个网格点，付款日程也有差别。阅读报告时，优先在**同一路线、同一情景和同一报价密度**内比较两种方法。

[路线 B 的工作簿定位、发布校验和完整字段](ROUTE_B.md)

## 3 第一次运行

进入仓库根目录，也就是能看到 `curve.py` 和 `requirements.txt` 的目录。使用 **Python 3.10 或更新版本**。macOS/Linux 可以执行下列命令。Windows PowerShell 把第二行换成 `.\.venv\Scripts\Activate.ps1`，其余命令相同。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run_experiment.py
```

路线 A 成功时会输出 `Textbook: 24 audit rows. Simulation: 12/12 fits converged.`。第一次学习可先做完 A，再准备路线 B。

### 路线 B 需要两份固定版本的原始文件

仓库中的 [来源清单](data/route_b/sources.json) 记录官方地址、文件名和 SHA-256。按发布方条款获取与清单完全匹配的两份文件，放在 `data/route_b/` 下。

- `glcnominalmonthedata.zip`，英格兰银行月度名义即期利率档案。
- `prosp210224.pdf`，英国 DMO 的票息条款来源。

官方 ZIP 的同一地址会更新。如果个人下载的文件与清单哈希不同，请向数据负责人取得这次实验已核验、可按条款使用的固定版本。程序会对原始文件做哈希核验，所需日期、期限、单位或利率异常时会停止。更换数据版本应作为单独变更，重新核验来源、覆盖和结果。

```bash
python run_route_b.py
python -m unittest discover -s tests -v
python -m jupyterlab
```

路线 B 成功时会输出 `Route B: 228 official spot rates, 48 converged fits.`。打开 `results.ipynb` 和 `results_b.ipynb`，选当前环境的 Python 内核，运行全部单元格。两条路线的 CSV 分别生成在 `results/` 和 `results_b/`。若 B 提示目标目录已有其他版本，使用 `python run_route_b.py --output-dir another_release`，并把 Notebook 第一格的 `results_dir` 改为同一目录。

### 推荐的读图顺序

1. **A 的教材图。** 找到 2 年期的 2.63125423%，再指出 1.5 年付款日为什么需要插值。
2. **B 的覆盖表。** 打开 `coverage_audit.csv`，找到 2025 年 7 月对应的两个半年期单元格，再在 `reference_rates.csv` 找到该月纳入的利率。
3. **B 的按月配对图。** `paired_metrics.csv` 的差值定义为**样条减线性**。负值表示样条的误差更低。利率 RMSE 的配对中位差为较密约 **−0.0710 bp**、较疏约 **−0.1580 bp**。
4. **B 的逐笔例子。** 从 `cashflow_valuation.csv` 选一个月和一只债券，加总 `present_value_gbp`，再与 `standardized_bonds.csv` 的 `benchmark_price_gbp` 核对。用同一个月、密度和方法，到 `holdout_prices.csv` 查留出估价。

## 4 找到要读或要改的文件

| 想了解什么 | 从哪里入手 |
| --- | --- |
| 一只债券何时付款、如何贴现 | [curve.py](curve.py) 的 `cash_flows()` 和 `present_value()`。 |
| 如何从价格反求利率 | [curve.py](curve.py) 的 `interpolate()`、`calibrate()` 和 `solve_rates()`。 |
| 教材三债和八债怎样复现 | [textbook.py](textbook.py) 的 `table_example()`、`figure_example()`，配合 [教材输入 JSON](data/textbook_bonds.json)。 |
| 两种方法如何公平比较 | [run_experiment.py](run_experiment.py) 的 `evaluate_reference()` 是两条路线共享的留出、校准和评分流程。`run_simulation()` 为 A 提供三条解析参考曲线。 |
| 路线 B 怎样读取和验证数据 | [boe_data.py](boe_data.py) 的 `load_inputs()`、`extract_panel()`，配合 [来源清单](data/route_b/sources.json)。 |
| 路线 B 如何生成价格和发布 | [run_route_b.py](run_route_b.py) 中，`value_month()` 逐月定价，`paired_metrics()` 生成配对结果，`publish_results()` 和 `verify_release()` 管理完整结果与哈希校验。 |
| 校验损坏数据时的行为 | [test_route_b.py](tests/test_route_b.py) 测试必需利率缺失、原始档案改动和结果文件损坏。 |
| 图表如何生成 | 两个 Notebook 从对应 CSV 读数据、画图。算法和实验配置在 Python 文件中维护。 |

## 5 GitHub 打包与四人协作

### 仓库文件与本地数据

以当前项目目录作为仓库根目录。仓库版保留 README、路线说明、Python 文件、依赖、测试、教材数值 JSON、来源清单和**清空输出的 Notebook**。原始档案、发行文件和运行产物在本地按来源清单管理。英格兰银行的法律页面区分网站资源、数据库和第三方内容，收益率页面也提示数据可能修订。上传原始档案、源数据摘录或含源数据的 Notebook 输出前，按发布方条款核对分享范围。[英格兰银行使用条款](https://www.bankofengland.co.uk/legal) · [收益率档案说明](https://www.bankofengland.co.uk/statistics/yield-curves) · [UK DMO 使用条款](https://www.dmo.gov.uk/terms-of-use/)

`.gitignore` 已排除两份原始文件、生成的结果目录、虚拟环境和缓存。首次提交时，在用于上传的项目副本中清空 Notebook 输出，再核对实际暂存文件。下面的命令适用于已初始化的仓库。先用第 3 节装好依赖的 Python 环境运行。

```bash
python -m nbconvert --clear-output --inplace results.ipynb results_b.ipynb
git add .gitignore README.md ROUTE_A.md ROUTE_B.md requirements.txt
git add curve.py textbook.py run_experiment.py boe_data.py run_route_b.py
git add data/textbook_bonds.json data/route_b/sources.json tests/test_route_b.py
git add results.ipynb results_b.ipynb
git diff --cached --name-only
```

将本地仓库连接 GitHub 的步骤见官方指南。组员克隆后按第 3 节运行，代码与本地数据目录可分别更新。[GitHub 导入本地仓库指南](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

### 四个人怎么分

| 负责内容 | 改动时一起核对 |
| --- | --- |
| **数据与出处** | 核对原始单元格、日期、利率单位和 SHA-256。 |
| **定价与校准** | 手算一笔现金流，复跑三债例，再查训练残差。 |
| **实验与评价** | 核对两种方法用到相同的训练价格、留出期限和评分网格。 |
| **图表与报告** | 维护 Notebook。报告的数字能追到同一次运行的 CSV。 |

每项修改开一个分支，通过 Pull Request 合并。PR 写明改了什么、运行了什么命令、指标是否变化。合并前由另一位组员复跑受影响路线。适合第一次组会的验收是**每人能解释 1.5 年利率为何出现，并能从路线 B 的一笔价格找到原始利率单元格**。

