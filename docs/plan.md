# 数据分析Agent 实施计划

> 分支: `feature/data-analysis-agent`
> 创建: 2026-04-29
> 状态: 进行中

## 目标

构建电池实验数据分析Agent，核心能力：
1. 对比任意几组实验设计-数据-失效分析结果
2. 分析设计因子X对失效结果的影响及可能机制
3. 诊断DOE漏洞，推荐补充实验设计
4. 给定新数据，自动检索高对比度历史数据
5. 验证/挑战已有结论

## 基本信息

| 项目 | 值 |
|------|---|
| 仓库 | LMBAgent |
| 分支 | feature/data-analysis-agent |
| autobattery集成 | pip install -e ../autobattery，直接import |
| 交互方式 | 全部通过LLM工具调用 + Streamlit Web UI |
| 节奏 | 核心先行，4周 |
| 用户 | 先单人，后续多人 |

## 架构总览

```
现有 (Phase 0)：
  单数据集 → 加载 → 可视化 → 报告

目标 (Phase 1-4)：
  多实验 + 设计元数据 → SQLite持久化 → 对比分析 → 退化分解 → DOE诊断 → 历史检索 → 结论验证
  ↑ Week 1                ↑ Week 2       ↑ Week 3                      ↑ Week 4
```

### 新增模块结构

```
src/lmbagent/
├── data/
│   ├── models.py          # 扩展: +ExperimentDesign, +FailureAnalysis
│   ├── loader.py          # 扩展: +Neware/Arbin/多格式
│   ├── transformer.py     # 扩展: +dQ/dV, +特征提取
│   ├── store.py           # 重写: SQLite持久化替代内存DataStore
│   ├── schema.py          # 新增: 设计因子元数据Schema定义
│   └── catalog.py         # 新增: 文件服务器目录扫描+批量导入
├── comparison/            # 新增模块
│   ├── overlay.py         # 叠加对比图(容量/CE/电压)
│   ├── delta.py           # 差异分析(ΔV, Δ容量)
│   └── metrics.py         # 跨实验指标统计表
├── degradation/           # 新增模块
│   ├── features.py        # 从循环数据提取统计特征
│   ├── signatures.py      # 退化签名矩阵计算
│   ├── decomposition.py   # NNLS退化模式分解
│   └── doe_checker.py     # DOE完备性检查+推荐
├── search/                # 新增模块
│   ├── vectorizer.py      # 数据→特征向量
│   ├── indexer.py         # 向量索引
│   └── engine.py          # 相似/对比度搜索引擎
├── conclusions/           # 新增模块
│   ├── models.py          # 结论数据模型
│   ├── store.py           # 结论CRUD
│   └── verifier.py        # 新数据→结论验证
└── agent.py               # 扩展: +10个新LLM工具
```

---

## Week 1: 数据基础层

**里程碑**: 能从文件服务器批量加载PEC/Neware/Arbin数据，每个实验绑定设计因子元数据，持久化到SQLite。

### W1.1 定义 ExperimentDesign Schema
- **文件**: `data/schema.py`, `configs/experiment_template.yaml`
- **内容**: Pydantic模型定义设计因子(电极设计/电解液/隔膜/化成protocol/测试条件)
- **依赖**: 无

### W1.2 扩展 BatteryDataset
- **文件**: `data/models.py` 修改
- **内容**: 增加 `experiment_design: Optional[ExperimentDesign]` 字段
- **依赖**: W1.1

### W1.3 SQLite持久化
- **文件**: `data/store.py` 重写
- **表结构**:
  - `experiments`: experiment_id, cell_id, chemistry, source_file, design_json, loaded_at
  - `cycle_summaries`: experiment_id, cycle_index, charge/discharge_cap, CE, ...
  - `failure_analyses`: experiment_id, method, modes_json, created_at
  - `conclusions`: conclusion_id, statement, evidence_ids, created_at, status
- **兼容**: 保留内存DataStore接口，内部改用SQLite
- **依赖**: W1.2

### W1.4 移植多格式加载器
- **文件**: `data/loader.py` 扩展
- **来源**: autobattery `src/data/loader.py`
- **格式**: Neware .npy/.xlsx, Arbin CSV, 通用CSV(30+列名别名)
- **依赖**: autobattery, W1.2

### W1.5 文件服务器目录扫描+批量导入
- **文件**: `data/catalog.py` 新增
- **功能**: scan_directory() + batch_import() + 自动匹配设计元数据YAML
- **依赖**: W1.3, W1.4

### W1.6 测试+文档
- **文件**: tests/test_store_sqlite.py, tests/test_loader_multi.py, docs/worklog.md
- **依赖**: 以上全部

---

## Week 2: 多实验对比引擎

**里程碑**: 选择任意多组实验，自动生成叠加对比图、差异分析、指标排名表。

### W2.1 叠加对比图
- **文件**: `comparison/overlay.py`
- **功能**: overlay_capacity_fade(), overlay_ce(), overlay_voltage_curves()
- **样式**: 多色+图例标注cell_id

### W2.2 差异分析
- **文件**: `comparison/delta.py`
- **功能**: compute_delta_v(), compute_capacity_difference() 热力图

### W2.3 跨实验指标统计表
- **文件**: `comparison/metrics.py`
- **功能**: build_comparison_table(), rank_by_metric()

### W2.4 新增LLM工具
| 工具名 | 参数 | 功能 |
|--------|------|------|
| `list_experiments` | chemistry, design_factor_filter | 列出/筛选实验 |
| `compare_experiments` | data_ids[], metrics | 对比多组实验 |
| `overlay_plot` | data_ids[], plot_type, cycle | 叠加对比图 |

### W2.5 Streamlit页面
- **文件**: `web/app/views/page_comparison.py`
- **页面**: "实验对比" 多选→对比图+指标表

---

## Week 3: 退化分解 + DOE智能分析

**里程碑**: 自动分解失效模式(7种)，关联设计因子与失效模式，诊断DOE漏洞。

### W3.1 循环数据特征提取
- **文件**: `degradation/features.py`
- **特征**: 容量衰减率/knee点, CE趋势, 电压滞后, dQ/dV峰值, IR增长

### W3.2 退化签名矩阵
- **文件**: `degradation/signatures.py`
- **来源**: autobattery scripts/28_degradation_modes.py
- **签名**: 7种退化模式的 dV/d(mode_j) 灵敏度

### W3.3 NNLS退化模式分解
- **文件**: `degradation/decomposition.py`
- **算法**: ΔV(t) = Σ w_j × signature_j, scipy.optimize.nnls

### W3.4 DOE完备性检查+推荐
- **文件**: `degradation/doe_checker.py`
- **功能**: 设计因子分组对比, 方差分析, 参数空间覆盖度, 缺失组合推荐

### W3.5 新增LLM工具
| 工具名 | 参数 | 功能 |
|--------|------|------|
| `analyze_failure_modes` | data_id, method | 退化模式分解 |
| `analyze_design_impact` | data_ids[], design_factor | 设计因子影响分析 |
| `check_doe_coverage` | data_ids[] | DOE完备性诊断 |
| `recommend_experiments` | data_ids[], focus_factor | 推荐补充实验 |

### W3.6 Streamlit页面
- "退化分析": 分解→雷达图/堆叠面积图
- "DOE分析": 参数空间覆盖热力图+推荐

---

## Week 4: 历史检索 + 结论管理

**里程碑**: 给定新数据，自动匹配高对比度历史数据，验证/挑战已有结论。

### W4.1 数据向量化
- **文件**: `search/vectorizer.py`
- **向量**: 设计因子编码 + 性能特征 + 退化权重

### W4.2 搜索引擎
- **文件**: `search/engine.py`
- **模式**: 相似搜索(余弦相似度), 对比搜索(设计因子近/失效模式异)

### W4.3 结论管理
- **文件**: `conclusions/models.py`, `conclusions/store.py`
- **模型**: Conclusion(statement, scope, evidence, confidence, status)

### W4.4 结论验证
- **文件**: `conclusions/verifier.py`
- **流程**: 新数据→特征→搜索历史→对比→支持/挑战结论

### W4.5 新增LLM工具
| 工具名 | 参数 | 功能 |
|--------|------|------|
| `search_similar` | data_id, mode(similar/contrast) | 搜索相似/对比历史 |
| `manage_conclusion` | action, statement, evidence | 增删改查结论 |
| `verify_with_new_data` | data_id | 新数据验证已有结论 |

### W4.6 Streamlit页面
- "历史检索": 新数据→匹配历史→并排对比
- "结论管理": 结论列表→支撑证据→验证状态

---

## 后续阶段 (MVP后)

| 阶段 | 内容 |
|------|------|
| Phase 5 | 实验数据微调退化分解模型(替换仿真签名为实验签名) |
| Phase 6 | 在线实验自适应模型更新(流式数据+incremental learning) |
| Phase 7 | 多用户支持(认证+共享DB+权限) |
| Phase 8 | autobattery FNO深度集成(快速仿真+设计优化) |
| Phase 9 | 云端部署(AgentScope) |

## 依赖变化

```toml
# pyproject.toml 新增
dependencies = [
    # ... existing ...
    "scipy>=1.11",    # NNLS decomposition
    "numpy>=1.24",    # vector operations
]
```

autobattery 作为本地依赖: `pip install -e ../autobattery`

## 进度追踪

- [x] 创建分支 feature/data-analysis-agent
- [x] Week 1: 数据基础层
  - [x] W1.1 定义 ExperimentDesign Schema
  - [x] W1.2 扩展 BatteryDataset
  - [x] W1.3 SQLite持久化
  - [x] W1.4 移植多格式加载器
  - [x] W1.5 目录扫描+批量导入
  - [x] W1.6 测试+文档
- [x] Week 2: 多实验对比引擎
  - [x] W2.1 叠加对比图
  - [x] W2.2 差异分析
  - [x] W2.3 跨实验指标统计表
  - [x] W2.4 新增LLM工具
  - [x] W2.5 Streamlit对比页面
  - [x] W2.6 测试+文档
- [x] Week 3: 退化分解 + DOE智能分析
  - [x] W3.1 循环数据特征提取
  - [x] W3.2 退化签名矩阵
  - [x] W3.3 NNLS退化模式分解
  - [x] W3.4 DOE完备性检查+推荐
  - [x] W3.5 新增4个LLM工具
  - [x] W3.6 Streamlit退化+DOE页面
  - [x] W3.7 测试+文档
- [x] Week 4: 历史检索 + 结论管理
