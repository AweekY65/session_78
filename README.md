# Local SAT Solver

一个完全本地运行的 SAT 求解器，仅依赖 Python 标准库。核心 DPLL 算法
自行实现，不调用 Z3、MiniSat 或任何云求解服务；所有 CNF 输入、求解
状态、模型与测试数据只存在于本地文件或内存中。

## 文件结构

- `sat_solver.py` — DIMACS 解析器、DPLL 求解器、模型验证与 CLI
- `tests/test_sat_solver.py` — 单元测试（含穷举 oracle 对照）

## DIMACS CNF 输入格式

```
c 注释行以 c 开头
p cnf <nvars> <nclauses>
1 -2 0
2 3 0
%
```

严格校验规则（违反即抛出 `DimacsError`）：

- 必须有且仅有一行 `p cnf <nvars> <nclauses>` 头，且出现在任何子句之前
- 每个文字是 `[−nvars, nvars]` 内的非零整数；子句以 `0` 结束，可跨行
- 实际子句数必须与头部声明完全一致
- 最后一个子句必须以 `0` 结束（文件结束标记校验）
- 可选的 `%` 结束标记之后只允许注释行，不允许再出现子句内容

### 确定语义

| 输入 | 语义 |
| --- | --- |
| 空公式（0 个子句） | SAT，模型可任意扩展（未受约束变量默认赋 True） |
| 空子句 | 公式 UNSAT |
| 重复文字 | 去重 |
| 重言式子句（同时含 `x` 与 `-x`） | 恒真，直接丢弃 |

## DPLL 流程

`DPLLSolver._dpll` 的每一层递归依次执行：

1. **Unit propagation（单元传播）**：反复找到长度为 1 的子句，强制赋值
   并化简公式，直到不动点；出现空子句即冲突，触发回溯。
2. **Pure literal elimination（纯文字消除）**：在剩余子句中只以单一极性
   出现的变量直接赋为满足值，循环至不再存在纯文字。
3. **变量选择（分支启发式）**：在未赋值变量中挑选在剩余子句中出现次数
   最多的变量（出现次数相同则取编号较小者），先尝试 `True` 再尝试
   `False`。
4. **回溯**：某一分支失败时撤销该分支引入的所有赋值，尝试另一极性；
   两极性都失败则向上一层报告冲突。UNSAT 结论由搜索空间穷尽得出，
   不依赖任何超时猜测。

### 统计输出

求解过程累计三项指标（`SolverStats`）：

- `propagations` — 强制赋值次数（unit propagation + pure literal）
- `decisions` — 分支决策次数
- `backtracks` — 失败分支回退次数

## 使用方法

```bash
python3 sat_solver.py path/to/formula.cnf
```

输出示例：

```
SAT
1 2 -3
stats: propagations=3 decisions=0 backtracks=0
```

SAT 时退出码为 0 并打印完整模型（每个变量都有赋值，可直接用
`verify_model` 复核所有子句）；UNSAT 时退出码为 1。

作为库调用：

```python
from sat_solver import parse_dimacs, DPLLSolver, verify_model

formula = parse_dimacs(open("f.cnf").read())
result = DPLLSolver(formula.num_vars, formula.clauses).solve()
if result.satisfiable:
    assert verify_model(formula.clauses, result.model)
```

## 运行测试

所有测试直接在终端执行：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：

- SAT / UNSAT 基本用例与模型完整性
- unit propagation 链与 pure literal elimination（无需决策即求解）
- 鸽巢原理（4 鸽 3 洞）触发的深度回溯，断言 `backtracks > 0`
- DIMACS 各类格式错误（缺头部、越界文字、子句未终止、子句数不符、
  `%` 之后出现内容等）
- 空公式 / 空子句 / 重复文字 / 重言式子句的确定语义
- 300 组随机小公式，与穷举全部赋值的 oracle 逐一比对结果
