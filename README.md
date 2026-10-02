# Local DPLL SAT Solver

一个完全本地运行的 SAT 求解器：所有 CNF 输入、求解状态、模型与测试数据
只保存在本地文件或内存中，不调用 Z3、MiniSat、云求解服务或任何外部服务。
仅使用 Python 标准库，核心 DPLL 算法在 `sat_solver.py` 中自行实现。

## 文件结构

- `sat_solver.py` — DIMACS 解析器、DPLL 求解器、模型验证器与 CLI。
- `tests/test_sat_solver.py` — 自动化测试（unittest）。

## DIMACS CNF 输入格式

```
c 注释行以 c 开头
p cnf <nvars> <nclauses>
1 -2 0
2 3 0
%
```

严格校验规则（违反即抛出 `DimacsError`，CLI 以退出码 1 报错）：

- 必须有且仅有一行 `p cnf <nvars> <nclauses>` 头部，且位于所有 clause 之前；
- 每个 literal 为整数，绝对值必须在 `1..nvars` 范围内；
- 每个 clause 必须以 `0` 结束（允许跨行书写），文件结束时不得有未闭合的 clause；
- 实际 clause 数量必须与头部声明完全一致；
- 可选的 `%` 作为文件结束标记，其后只允许空白；
- 非整数 token、重复头部、头部前出现 clause 均为错误。

### 确定语义

- **空公式**（0 个 clause）：恒为 SAT，返回全 False 的完整模型；
- **空 clause**：使公式恒为 UNSAT；
- **重复 literal**：在解析时折叠（clause 以 frozenset 存储）；
- **tautology clause**（同时含 `x` 与 `-x`）：恒真，解析时直接丢弃。

## DPLL 流程

`DPLLSolver.solve()` 返回 `(sat, model)`。递归搜索的每一层按以下顺序进行：

1. **冲突检测**：存在空 clause 则返回冲突，触发回溯；
2. **Unit propagation**：反复取长度为 1 的 clause，强制其唯一 literal 为真并化简公式；
3. **Pure literal elimination**：若某变量在剩余 clause 中只以一种极性出现，
   直接按该极性赋值并化简；
4. **决策（decision）**：选择分支变量，先尝试 `True` 再尝试 `False`，
   某个分支失败则回溯尝试另一分支。

### 变量选择启发式

采用按 clause 长度加权的出现频率启发式（类似 DLIS）：变量在每个剩余
clause 中贡献 `1/len(clause)` 的分数，选择总分最高的变量。短 clause 对
搜索约束更强，因此其中的变量权重更大。

### 模型

SAT 时返回的模型覆盖 `1..nvars` 的全部变量（完整赋值）：搜索未约束到的
变量统一补 `False`，因此模型可直接用于 `verify_model()` 逐 clause 验证。
UNSAT 由搜索空间穷尽确定，不依赖任何超时猜测。

### 统计

`Stats` 记录并输出四项指标：

- `propagations` — unit propagation 强制赋值的次数；
- `pure_literals` — pure literal elimination 赋值的次数；
- `decisions` — 分支尝试次数；
- `backtracks` — 分支失败回溯的次数。

## 使用方法

```bash
python3 -m sat_solver <file.cnf>
```

输出解析结果、SAT/UNSAT、完整模型（SAT 时）与搜索统计。

## 运行测试

```bash
python3 -m unittest discover -s tests
```

测试覆盖：SAT/UNSAT 实例、unit propagation 链、pure literal elimination、
深度回溯（4 鸽 3 洞鸽笼原理）、DIMACS 各类解析错误、空公式/空 clause/
重复 literal/tautology 语义，以及 300 组随机小公式与穷举 oracle 的对拍验证。
