# AGENTS.md

## 0. 入口规则

**Required Skills**: `planning-with-files`, `linear-cli`, `change-gate`, `uv-package-manager`,
`modular-code`, `unit-test`, `harness-bench`, `experiment-handbook`, `refinement`,
`system-contract`, `code-review-with-logs`

所有非闲聊、非纯问候、非 `[quick check]` 的任务都必须先走 `linear-cli` start-task hook，
并使用文件化记录。`AGENTS.md` 只保留仓库级硬约束；可复用细节必须沉淀到对应 skill。
在所有任务开始前请必须先阅读`refinement`这个skill的Failure Modes，并在整个任务执行过程中牢记

核心例外：
- 当用户要求以 `[quick check]` 开始时，只做快速总结，不调用 Linear、规划、review 等流程化记录。
- 用户交互必须使用简体中文；代码、注释和 `.codex/` 文档可使用英文。
- 新发现的工具行为、API 兼容性、用户纠正过的工作流概念，必须更新到对应 skill。

## Agentic Engineering Loop

仓库基础设施改动默认遵循小步、可验证、可复核的工作闭环：

1. Understand：先确认用户可见目标、影响面、现有约束和最窄可用验证命令。
2. Scope：选择满足目标的最小 coherent change，通过`modular-code`确保每个模块单职责、单输入/输出、明确可编辑边界；不要混入无关清理、格式化、依赖升级或历史入口恢复。
3. Plan：跨模块、公共接口、数据/安全、构建/发布、实验运行契约或大文件重构前，先写短计划并确认不放宽本文件约束。
4. Implement：沿用本仓库既有模式，保持 diff 可审阅；公共 API、manifest/schema、runner CLI、service contract 默认保持兼容。
5. Validate：先跑 focused/static check；基础设施改动默认跑 `system-contract`，再按影响面追加更重验证。
6. Review：收口前检查 `code-review-with-logs` 和实际 diff，确认没有无关 churn、generated/cache、本地实验产物、secret-like 字符串或私有端点。
7. Report：说明改了什么、验证结果、未跑验证及原因、剩余风险或需要人工复核的位置。


## 1. Skill 路由

| 场景 | 必用 skill | 责任 |
|---|---|---|
| 多步任务、任务记录、上下文恢复 | `planning-with-files` | 维护文件化计划、发现、进度；本仓库写入 `.codex_record/<CODEX_THREAD_ID>/`。 |
| 任务登记、Linear 复用/reopen/sub-issue/closeout | `linear-cli` | 唯一拥有 Linear 细节规则；AGENTS 不重复展开。 |
| 代码、测试、配置、依赖、构建、文档行为或 agent-rule 改动 | `change-gate` | 工程闭环、scope control、repo hygiene、自检和报告纪律。 |
| 本地 Python 执行、依赖、工具命令 | `uv-package-manager` | 所有本地 Python 相关执行必须使用 `uv` / `uvx` / `uv tool run`。 |
| Python 模块边界、职责拆分、edit boundary | `modular-code` | 单职责、单输入/输出、明确可编辑边界。 |
| 任务级验收、fail-before/pass-after、lint/type gate | `unit-test` | 普通验收测试不得放入 `tests/bench`。 |
| 定量评估、benchmark 方法学、`tests/bench/**` | `harness-bench` | 只有明确 benchmark / 效果评估任务才使用。 |
| 实验运行方法、命令、artifact、环境前提、复现实验流程 | `experiment-handbook` | 所有可复用实验运行方法必须记录在该 skill。 |
| AGENTS 或 skill 不好用、规则失效、agent 行为失败 | `refinement` | 记录 failure mode，改进 owning skill/rule，并由另一个 agent 或独立验证确认 failure mode 不再复现。 |
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
- 执行阶段优先并行agent，优先通过多个worker来分解任务，但必须有清晰 ownership。需要共享上下文的 subagent 工作由 main agent 维护 Linear issue topology。

### `.codex_record`

确定当前线程 ID：优先使用 `CODEX_THREAD_ID`，缺省为 `main`。创建并只写入：

| File | Purpose |
|---|---|
| `.codex_record/<CODEX_THREAD_ID>/task_plan.md` | Goals, phases, status |
| `.codex_record/<CODEX_THREAD_ID>/progress.md` | Operation log, errors; source of truth |
| `.codex_record/<CODEX_THREAD_ID>/findings.md` | Discoveries and architecture decisions |

可读取其他线程记录以共享上下文，但只能写入当前线程目录。`progress.md` 只能增量追加，不得删除旧记录。

### `.codex_idea`

科研相关任务必须创建并只写入：

| File | Purpose |
|---|---|
| `.codex_idea/<CODEX_THREAD_ID>/idea_plan.md` | 用户科研 idea、核心假设、idea-to-code 映射、实验设计 |
| `.codex_idea/<CODEX_THREAD_ID>/idea_progress.md` | 执行日志和四个保真检查点状态 |
| `.codex_idea/<CODEX_THREAD_ID>/idea_findings.md` | 实验结果和结论 |

科研任务必须执行四个 reliable checks：
- Idea Check: 复述用户 idea 和核心假设，不得替换假设。
- Code Mapping Check: 每段代码改动必须对应 idea 要求，并标注 assumption。
- Experiment Check: 每个实验只验证一个用户提出的 hypothesis / claim。
- Conclusion Check: 结论只能按 confirmed / not confirmed / inconclusive / needs further experiment 对应实验输出。

## 3. 本地执行与验证硬约束

- 本地 Python 相关执行必须由 `uv-package-manager` 规则管理。不要直接调用 `python`、`python3`、`pip`、`pytest`、`ruff`、`mypy` 等系统命令。
- 如果 `uv` 不可用，停止并报告，不得 fallback 到系统 Python。
- 普通任务验收使用 `unit-test`；只有用户明确要求 benchmark / 定量评估时，才允许把评估写入 `tests/bench/**` 并使用 `harness-bench`。
- AGENTS、skill、workflow、repo hygiene 或 shared contract 改动必须运行：

```bash
uv run python .codex/skills/system-contract/scripts/check_system_contract.py --workspace .
```

## 4. 开发闭环

1. **Plan**: 更新 `.codex_record/<CODEX_THREAD_ID>/task_plan.md`，确认 Linear hook 已登记，使用 `unit-test` 冻结任务级验收 gate。
2. **Act**: 通过 `change-gate` 保持最小 coherent diff；通过 `modular-code` 保持明确 edit boundary。
3. **Record**: 将关键操作、错误、验证结果增量追加到 `progress.md`，发现和决策写入 `findings.md`。
4. **Validate**: 运行 task-scoped `uv run ...` 验收命令；workflow/skill 改动追加 `system-contract` gate。
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
`lark-wiki` / `lark-doc` 回查飞书知识库 `Long Horizon Midtraining` 及其子文档；使用这些
skill 时不要加 `HOME`。关键发现必须追加到当前 session 的 `findings.md` / `progress.md`。
