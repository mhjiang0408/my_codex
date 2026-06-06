# AGENTS.md

## 0. 入口规则

**Required Skills**: `cognition`, `planning-with-files`, `linear-cli`, `change-gate`, `uv-package-manager`,
`software-architecture`, `modular-code`, `error-roadmap`, `unit-test`, `harness-bench`,
`experiment-handbook`, `refinement`, `multi-agent`, `system-contract`, `code-review-with-logs`

所有非闲聊、非纯问候、非 `[quick check]` 的任务都必须先走 `linear-cli` start-task hook，
并使用文件化记录。`AGENTS.md` 只保留仓库级硬约束；可复用细节必须沉淀到对应 skill。
Linear default project: Agent Swarm
每个任务对应的 Linear issue 必须作为中文 architecture/module-level cognition card；
Linear issue description 不得作为低层任务 trace、实现步骤、命令日志或文件清单。
`.codex_record/<CODEX_THREAD_ID>/` 才是详细执行 trace 的 source of truth。
在所有任务开始前请必须先阅读`refinement`这个skill的Failure Modes，并在整个任务执行过程中牢记
planning 阶段的实质行动前必须先使用 `cognition` 通过 Linear issue description 检索
已有 cognition，确认当前计划符合已有探索经验；`cognition` 不得替代 `.codex_record`、
`.codex_idea`、review 或 Feishu 收口。

实现阶段首要硬约束：所有代码实现、bug 修复、pipeline 调整、运行失败诊断和异常处理设计，
在进入实现前必须首先遵守 `error-roadmap`。必须先建立 execution roadmap、roadmap path、
stage/module/function 错误边界、结构化异常上下文和完整日志定位方式；不得先用 fallback、
硬编码、静默吞错、泛 `except` 或绕过式 patch 让报错消失。实现阶段的第一目标是让失败可定位：
明确核心错误类型、原始异常链、完整 `tee` 日志位置和最小负责模块。

核心例外：
- 当用户要求以 `[quick check]` 开始时，只做快速总结，不调用 Linear、规划、review 等流程化记录。
- 用户交互必须使用简体中文；代码、注释和 `.codex/` 文档可使用英文。
- 新发现的工具行为、API 兼容性、用户纠正过的工作流概念，必须更新到对应 skill。
- 在执行任务过程中**务必**尽可能把可以并行的局部任务拆分并通过subagent来并行完成。

## Agentic Engineering Loop

仓库基础设施改动默认遵循小步、可验证、可复核的工作闭环：

1. Understand：先确认用户可见目标、影响面、现有约束和最窄可用验证命令。
2. Scope：选择满足目标的最小 coherent change，通过`software-architecture`先识别业务能力、领域边界、职责分层和系统约束，再通过`modular-code`确保每个模块单职责、单输入/输出、明确可编辑边界；不要混入无关清理、格式化、依赖升级或历史入口恢复。涉及 Pipeline 调整或 Benchmark 反馈的任务，必须声明 `primary feedback target module` 或明确的 module set。尽可能避免多模块之间的耦合。
3. Plan：基于 `software-architecture` 先用软件架构师语言说明业务能力、领域边界、责任分配、实现路径和验收模型，再落到文件、模块或函数层面的执行步骤；不要只堆文件名、模块名或函数名。跨模块、公共接口、数据/安全、构建/发布、实验运行契约或大文件重构前，先写短计划并确认不放宽本文件约束。plan至少要有一个section用自然语言基于software architecture的形式告诉我你的实现路径。Pipeline / Benchmark 计划必须写明 baseline score 来源、after score 口径、预期 `score delta` 归因对象、artifact root、stage/module 可观测性和失败分类。
4. Implement：实现阶段必须先应用 `error-roadmap`：建立 execution roadmap、roadmap path、stage/module/function 错误边界、结构化 try-except 上下文和完整日志索引，再写具体业务改动；不得用 fallback、硬编码或静默吞错替代定位核心报错模块。沿用本仓库既有模式，保持 diff 可审阅；公共 API、manifest/schema、runner CLI、service contract 默认保持兼容。Pipeline 模块必须提供足够的 pipeline observability：stage/module 状态、关键输入输出摘要、日志或结构化产物、失败类型，确保失败可沿模块边界逐层下钻。
5. Validate：先跑 focused/static check；基础设施改动默认跑 `system-contract`。若运行失败，必须先根据 `error-roadmap` 的结构化异常锁定错误类型和 roadmap path，再读取完整 `tee` 日志确认原始 traceback，不得直接猜测或补 fallback。验证时应采用分层下钻的 Evaluation 策略：先从端到端 Pipeline 或外部 Benchmark 观察整体是否达标；如果整体失败，再沿着 Pipeline 的模块边界逐层拆解，从高层流程到子模块、组件、函数分别构造最小测试用例。通过每一层测试的通过/失败反馈，逐步缩小问题范围，判断失败来自模块自身实现、模块间接口，模块的确在该下游benchmark上表现不佳还是评测环境中的集成问题。Pipeline 调整后 rerun 同一 Benchmark，`score delta = after - before` 默认作为本次 Pipeline change 的外层反馈；单模块 change 归因到声明的 target module，多模块 change 归因到声明的 module set，除非分层诊断进一步锁定单模块。
6. Review：收口前检查 `code-review-with-logs` 和实际 diff，确认没有无关 churn、generated/cache、本地实验产物、secret-like 字符串或私有端点。Benchmark / Pipeline closeout 必须复核 benchmark before/after、`score delta`、归因模块或 module set、artifact root、失败分类和 cognition verdict。
7. Report：说明改了什么、验证结果、未跑验证及原因、剩余风险或需要人工复核的位置。若 Benchmark 产生 `score delta`，报告必须写清是否形成 module-effect cognition；未写入 cognition 时必须说明是 blocked、inconclusive、证据不足还是多模块归因未拆开。


## 1. Skill 路由

| 场景 | 必用 skill | 责任 |
|---|---|---|
| planning 前置长期认知、Linear cognition issue、研究/论文/实验洞察沉淀 | `cognition` | 在实质行动前通过 Linear issue description 检索 cognition，确保计划复用已有架构和实验边界经验；不要维护本地 cognition graph/index/seed。 |
| 多步任务、任务记录、上下文恢复 | `planning-with-files` | 维护文件化计划、发现、进度；本仓库写入 `.codex_record/<CODEX_THREAD_ID>/`。 |
| 任务登记、Linear 复用/reopen/sub-issue/closeout | `linear-cli` | 唯一拥有 Linear 细节规则；AGENTS 不重复展开。 |
| 代码、测试、配置、依赖、构建、文档行为或 agent-rule 改动 | `change-gate` | 工程闭环、scope control、repo hygiene、自检和报告纪律。 |
| 本地 Python 执行、依赖、工具命令 | `uv-package-manager` | 所有本地 Python 相关执行必须使用 `uv` / `uvx` / `uv tool run`。 |
| 软件开发架构计划、领域划分、业务实现路径、验收模型 | `software-architecture` | Plan 阶段必须先用架构语言说明业务能力、领域边界、责任分配、实现路径和验收模型，再细化到文件/模块层面。 |
| Python 模块边界、职责拆分、edit boundary | `modular-code` | 单职责、单输入/输出、明确可编辑边界。 |
| 所有代码实现、bug 修复、pipeline 调整、运行失败诊断、异常处理设计、反 fallback/硬编码 | `error-roadmap` | 实现阶段首要硬约束；先建立 execution roadmap、roadmap path、结构化 try-except 错误边界和完整 `tee` 日志回溯，再定位核心报错模块。 |
| 任务级验收、fail-before/pass-after、lint/type gate | `unit-test` | 普通验收测试不得放入 `tests/bench`。 |
| 定量评估、benchmark 方法学、`tests/bench/**` | `harness-bench` | 只有明确 benchmark / 效果评估任务才使用。 |
| 实验运行方法、命令、artifact、环境前提、复现实验流程 | `experiment-handbook` | 所有可复用实验运行方法必须记录在该 skill。 |
| AGENTS 或 skill 不好用、规则失效、agent 行为失败 | `refinement` | 记录 failure mode，改进 owning skill/rule，并由另一个 agent 或独立验证确认 failure mode 不再复现。 |
| tmux Codex subagents、多 Codex session 并行探索或分工实现 | `multi-agent` | 负责额外 Codex session 的启动命令、`CODEX_HOME=./.codex`、`codex --yolo`、window 命名、owner、edit boundary 和 merge point。 |
| AGENTS、skill、workflow、repo hygiene 规则检查 | `system-contract` | 运行 skill-local repository contract gate。 |
| 任务结束、运行失败、测试失败、正式 review report | `code-review-with-logs` | Stop hook 收口、可靠性检查、Feishu 完整报告、高信号 review。 |

如果入口 skill 遇到更适合的子问题，必须路由给 companion skill，而不是复制其规则。

实验规则与工作流修正规则：
- 所有实验运行方法、复现实验命令、artifact 说明、环境前提和已知运行 failure modes，必须记录到 `experiment-handbook`，不要长期散落在 `AGENTS.md`、聊天或一次性报告中。
- 当用户指出 `AGENTS.md` 或任一 skill 不好用、含糊、过宽、过窄或导致错误 agent 行为时，必须使用 `refinement`：先记录可复现 failure mode，再修改 owning rule/skill，最后由另一个 agent 或独立验证步骤确认该 failure mode 不再存在。

## 2. Traceability 硬约束

- Externalize thinking to files, not just context.
- Keep working docs inside `.codex/`, `.codex_record`, and `.codex_idea` only.
- Do not introduce `.agent_record` or a standalone `idea_record` directory in this repository.
- Start-task tracking must be completed by the `linear-cli` Codex hook before substantive implementation.
- Hook failure is hard-blocking. Repair the Linear / record chain before implementation continues.
- Linear 细节规则只在 `linear-cli` skill 中展开。用户纠正 Linear 工作流时，优先更新该 skill。
- Linear issue description 必须是中文 cognition 正文，记录架构/模块假设、边界、证据和结论；
  不得镜像 `.codex_record` 中的计划、命令、日志、diff、review report 或 Feishu 内容。
- 执行阶段优先并行agent，优先通过多个worker来分解任务，但必须有清晰 ownership。需要共享上下文的 subagent 工作由 main agent 维护 Linear issue topology。

### 并行 Codex Sessions

- 需要 tmux Codex subagents 时必须使用 `multi-agent` skill；`AGENTS.md` 只保留硬约束，不复制完整流程。
- 需要尽可能并行时，main agent 在 tmux session `codex` 中开启最多 5 个额外 Codex sessions，优先并行探索，main 负责调度、合并和最终验证。
- `window-name` 使用两个单词 `<project>-<task>`，例如 `swarm-schema`；同一任务多个 window 使用 `swarm-schema`, `swarm-schema1`, `swarm-schema2`。
- 尽可能将任务拆分为若干个并行任务交给 subagent 来完成；同一模块需要多个并行修改任务时，先拆成互不重叠的 edit boundary、owner 和 merge point，再分线程执行。

### `.codex_record`

确定当前线程 ID：优先使用 `CODEX_THREAD_ID`，缺省为 `main`。创建并只写入：

| File | Purpose |
|---|---|
| `.codex_record/<CODEX_THREAD_ID>/task_plan.md` | Goals, phases, status |
| `.codex_record/<CODEX_THREAD_ID>/progress.md` | Operation log, errors; source of truth |
| `.codex_record/<CODEX_THREAD_ID>/findings.md` | Discoveries and architecture decisions |

可读取其他线程记录以共享上下文，但只能写入当前线程目录。`progress.md` 只能增量追加，不得删除旧记录。

### `.codex_idea`

科研、实验、benchmark、论文复现、模型与框架评测、controller 对比、pipeline smoke/full run
等任务必须创建并只写入：

| File | Purpose |
|---|---|
| `.codex_idea/<CODEX_THREAD_ID>/idea_plan.md` | 用户科研 idea、核心假设、idea-to-code 映射、实验设计 |
| `.codex_idea/<CODEX_THREAD_ID>/idea_progress.md` | 执行日志和四个保真检查点状态 |
| `.codex_idea/<CODEX_THREAD_ID>/idea_findings.md` | 实验结果和结论 |

所有实验（包括评测、复现、pipeline smoke试跑任务等）的 `idea_plan.md` 必须在执行前写明可由 `code-review-with-logs`
抽取的 `命令参数要求` / `实验命令` / `required parameters`，至少包含：
模型名、controller mode、task_count、`runtime.stop_targets`、外层 timeout、
artifact root、validator/score 口径、baseline score 来源、target pipeline/module、
`score delta` 归因声明。若用户要求“论文复现”或“复现口径”，必须明确写出
paper/legacy 期望参数，并禁止用 smoke/diagnostic 参数替代。

实验任务 closeout 时，`.codex_idea` 缺失、参数要求缺失、或实际命令/artifact facts
与 `idea_plan.md` 记录不一致，必须使 reliable check `FAIL` 或 `BLOCKED`；不得把
`.codex_idea` 缺失视为 `NOT_APPLICABLE`。诊断实验、smoke 和正式实验的结论必须分开写，
不得把诊断口径结果报告成正式实验结果；不得把诊断口径结果报告成论文复现结果。
这些实验都必须符合人工智能学术论文实验规范。

科研和实验任务必须执行四个 reliable checks：
- Idea Check: 复述用户 idea 和核心假设，不得替换假设。
- Code Mapping Check: 每段代码改动必须对应 idea 要求，并标注 assumption。
- Experiment Check: 每个实验只验证一个用户提出的 hypothesis / claim，并核对
  `idea_plan.md` 的参数要求与实际命令/artifact facts 一致。
- Benchmark Attribution Check: Pipeline 调整任务必须把 `score delta` 映射到声明的
  module 或 module set；Pipeline 未跑通时只能写 blocked / inconclusive，不得写成
  module-effect cognition。
- Conclusion Check: 结论只能按 confirmed / not confirmed / inconclusive / needs further experiment 对应实验输出。

## 3. 本地执行与验证硬约束

- 本地 Python 相关执行必须由 `uv-package-manager` 规则管理。不要直接调用 `python`、`python3`、`pip`、`pytest`、`ruff`、`mypy` 等系统命令，也不可直接将环境通过`pip`安装，必须要通过uv来管理。
- 如果 `uv` 不可用，停止并报告，不得 fallback 到系统 Python。
- 普通任务验收使用 `unit-test`；只有用户明确要求 benchmark / 定量评估时，才允许把评估写入 `tests/bench/**` 并使用 `harness-bench`。
- AGENTS、skill、workflow、repo hygiene 或 shared contract 改动必须运行：

```bash
uv run python .codex/skills/system-contract/scripts/check_system_contract.py --workspace .
```

## 4. 开发闭环

1. **Plan**: 更新 `.codex_record/<CODEX_THREAD_ID>/task_plan.md`，确认 Linear hook 已登记；基于 `software-architecture` 写清架构化计划、领域划分、业务实现路径、验收模型，再使用 `unit-test` 冻结任务级验收 gate。plan至少要有一个section用自然语言基于software architecture的形式告诉我你的实现路径
2. **Act**: 先通过 `error-roadmap` 建立 roadmap path、结构化异常上下文和完整日志定位方式；通过 `change-gate` 保持最小 coherent diff；通过 `modular-code` 保持明确 edit boundary。
3. **Record**: 将关键操作、错误、验证结果增量追加到 `progress.md`，发现和决策写入 `findings.md`。
4. **Validate**: 运行 task-scoped `uv run ...` 验收命令；workflow/skill 改动追加 `system-contract` gate。运行失败时先按 `error-roadmap` 读取结构化异常、roadmap path 和完整 `tee` 日志，再定位原始 traceback。验证时应采用分层下钻的 Evaluation 策略：先从端到端 Pipeline 或外部 Benchmark 观察整体是否达标；如果整体失败，再沿着 Pipeline 的模块边界逐层拆解，从高层流程到子模块、组件、函数分别构造最小测试用例。通过每一层测试的通过/失败反馈，逐步缩小问题范围，判断失败来自模块自身实现、模块间接口，模块的确在该下游benchmark上表现不佳还是评测环境中的集成问题
5. **Review**: 任务结束、运行失败或测试失败时由 `code-review-with-logs` end-task hook 生成标准 report。如果 review 为 `FAIL` 或 `BLOCKED`，先修复证据或实现问题。
6. **Report**: 用简体中文报告计划执行、验收标准满足情况、验证命令和 review 证据。

## 5. Feishu 与收口

- 完成任务后必须发送 `code-review-with-logs` 的完整 review report。
- 使用固定群组 `chat_id`: `oc_28abbb3d6e900a7084967e947da391fe`。
- 使用：

```bash
HOME=/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/DataFlyWheel/.lark \
  uv run python .codex/skills/code-review-with-logs/scripts/report_review_result.py \
  .codex/reviews/<review_id>/review_report.json \
  --summary-md .codex/reviews/<review_id>/review_summary.md \
  --send-feishu \
  --chat-id oc_28abbb3d6e900a7084967e947da391fe
```

完整 report 必须保留本地 review artifacts 和 `.codex_record/<CODEX_THREAD_ID>/progress.md` append；Feishu 消息不能替代本地记录。

## 6. Git Workflow

- 完成功能开发计划的任何部分后，必须提交到当前 Git 分支。
- `git add` 前检查 `.gitignore` 和 `git status --short`，避免大文件、cache、实验产物入库。
- 不要回滚用户已有改动；只提交本任务相关文件。
- 提交消息必须使用 Conventional Commits，例如：

```text
feat: Add Warehouse Covenant Skill
fix: fix task acceptance command generation
test: add system contract checks
```

## 7. 长期上下文

当本地上下文不足，或用户引用 proposal、实验设计、infra 决策、历史结论时，优先使用
`lark-wiki` / `lark-doc` 回查飞书知识库 `Context-Aware Agent Swarm Midtraining` 及其子文档；使用这些
skill 时不要加 `HOME`。关键发现必须追加到当前 session 的 `findings.md` / `progress.md`。
