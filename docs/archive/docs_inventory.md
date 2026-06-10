# Docs Inventory

Scope: read-only inventory from the documentation flattening/restructuring
pass. It records `README.md` documentation links and Markdown assets that were
reviewed under `docs/`, `docs/archive/`, `docs/roadmap/`, and
`docs/validation/`. This is a restructuring audit artifact, not a long-term
user documentation entry point, and it does not define current behavior.

Allowed actions in this inventory: 保留, 合并, 改名, 归档, 删除候选, 暂缓判断.

## Document Inventory

| 文档 | 当前用途 | 目标读者 | 当前有效文档 | 重复情况 | 建议动作 |
| --- | --- | --- | --- | --- | --- |
| `README.md` | 项目主入口、当前能力、推荐工作流、输出 workspace 和安全边界。 | 用户、维护者、新贡献者。 | 是。当前 2.2.12 和 operator workflow 的主入口。 | 与 `docs/cookbook.md`, `docs/index.md`, `docs/output_layout.md`, `docs/release_verification.md` 有摘要级重复。 | 保留 |
| `docs/index.md` | 文档地图，按 current contracts、active designs、release docs、archive 分层。 | 所有读者，尤其是维护者和 AI agent。 | 是，但目录层级已经反映出顶层过宽。 | 与 `README.md` 的文档列表和推荐路线重复；与 `docs/maintenance.md` 的分层规则重复。 | 保留 |
| `docs/cookbook.md` | 高层 CLI 操作手册，覆盖 verify/status/package/release 常用命令。 | 操作者、验证人员。 | 是。当前 operator cookbook。 | 与 `README.md` 推荐工作流、`docs/release_verification.md` release 命令、`docs/output_layout.md` 路径规则重复。 | 保留 |
| `docs/design.md` | 当前架构、安全合约、已实现工作流面。 | 维护者、开发者。 | 是。 | 与 `docs/stable_contracts.md`, `docs/output_layout.md`, `docs/lpsn_first_acquisition.md` 有合约摘要重复。 | 保留 |
| `docs/stable_contracts.md` | 稳定/审阅/内部/post-v1.0 合约分类。 | 维护者、下游脚本作者、发布审阅者。 | 是。 | 与 `docs/design.md`, `docs/output_layout.md`, `docs/schemas.md`, `docs/statuses.md` 有索引式重复。 | 保留 |
| `docs/output_layout.md` | Canonical output path contract，包括默认 workspace、`--outdir`、stage outputs。 | 用户、维护者、测试作者。 | 是。当前路径规范的权威文档。 | 与 `README.md`, `docs/cookbook.md`, `docs/release_checklist.md`, `docs/release_verification.md`, `docs/release_process.md` 的 workspace/results 说明重复。 | 保留 |
| `docs/schemas.md` | TSV/table 字段字典。 | 维护者、下游消费者、测试作者。 | 是。 | 与 `docs/output_layout.md` 路径上下文互补，少量与 specific feature docs 重复。 | 保留 |
| `docs/statuses.md` | emitted status values 字典。 | 维护者、测试作者、下游消费者。 | 是。 | 与 `docs/schemas.md` 中 status 字段说明、feature docs 中局部状态说明重复。 | 保留 |
| `docs/species_checklist_audit.md` | 用户提供 species checklist audit 的实现合约。 | 用户、维护者。 | 是。 | 与 `docs/lpsn_first_acquisition.md`, `docs/schemas.md`, `docs/statuses.md` 有 checklist 语义重复。 | 保留 |
| `docs/completion_audit.md` | mixed-provenance completion/gap 输出和 split completion metric 的实现合约。 | 用户、维护者、发布审阅者。 | 是。 | 与 `docs/schemas.md` 互补；external workflow 操作说明已指向 `docs/external_workflow_cookbook.md`。 | 保留 |
| `docs/handoff_index_contract.md` | `package-results` 生成的 `handoff_index.md` 解释合约。 | 操作者、下游 reviewer、维护者。 | 是。 | 与 `README.md`, `docs/cookbook.md`, `docs/release_verification.md`, `docs/roadmap/v2.2.12-maintenance-plan.md` 中 package/handoff 说明重复。 | 保留 |
| `docs/maintenance.md` | 文档维护规则、分层规则、最小验证命令。 | 维护者、AI agent。 | 是。 | 与 `docs/index.md` 分层重复；release hygiene 与 `docs/release_checklist.md` 重复。 | 保留 |
| `docs/release_process.md` | release commit/tag/GitHub Release/PR/post-release 流程。 | 维护者、发布人员。 | 是。 | 与 `docs/release_checklist.md` 有 release gate 和 workspace cleanup 重复。 | 保留 |
| `docs/release_checklist.md` | 发布执行 checklist、本地验证、packaging smoke、文件提交边界。 | 发布人员、维护者。 | 是。 | 与 `docs/release_process.md`, `docs/release_verification.md`, `README.md` 的验证路径和 workspace 规则重复。 | 保留 |
| `docs/release_verification.md` | 当前 release-verification 行为、版本历史摘要、gap/report 解释。 | 发布人员、操作者。 | 是。当前 release verification 主文档。 | 与 `docs/v2_2_0_release_verification.md`, `docs/release_notes_v2_2_x.md`, `docs/cookbook.md`, `README.md` 重复。 | 保留 |
| `docs/release_notes_v2_2_x.md` | v2.2.x consolidated release notes。 | 用户、发布审阅者。 | 是，但更像 release-history 支撑文档。 | 与 `CHANGELOG.md`、`docs/release_verification.md` 的 v2.2.x history 重复。 | 保留 |
| `docs/lpsn_first_acquisition.md` | LPSN-first acquisition 详细设计、实现历史、证据边界。 | 维护者、高级用户。 | 是，但包含 implementation history。 | 与 `README.md`, `docs/species_checklist_audit.md`, `docs/output_layout.md`, `docs/schemas.md` 大量重叠。 | 合并 |
| `docs/external_type_genome_ingestion.md` | 手工 external type-genome registration 的权威设计、边界和数据契约入口。 | 维护者、高级用户。 | 是。 | 与 cookbook/completion/provider docs 保持链接分工，不承载长篇操作说明、completion 规则或 provider policy。 | 保留 |
| `docs/external_workflow_cookbook.md` | external FASTA registration 的短流程 cookbook，含 synthetic/real local scenario。 | 操作者、curator。 | 是。 | 与 examples README 有命令形状重复，但保持为当前操作者入口；设计、output、provider、completion 细节链接到权威文档。 | 保留 |
| `docs/archive/fusobacterium_external_pilot.md` | `F. mortiferum` external registered genome pilot 历史案例。 | curator、验证人员、历史追溯读者。 | 否，archive case。 | 当前流程由 `docs/external_workflow_cookbook.md` 承担；examples README 保留最小可运行入口。 | 已归档 |
| `docs/archive/fusobacterium_real_pilot_template.md` | real local `F. mortiferum` evidence package 历史模板。 | curator、历史追溯读者。 | 否，archive case/template。 | 当前流程由 `docs/external_workflow_cookbook.md` 承担；examples README 保留最小模板入口。 | 已归档 |
| `docs/archive/local_artifact_normalization_design.md` | curator-provided local FASTA artifacts 的 offline normalization 历史设计边界。 | 维护者、future implementer。 | 否，design-only history；当前边界已并入 `docs/provider_automation_policy.md`。 | 与 external ingestion/provider policy 的 non-scope 边界重复。 | 已归档 |
| `docs/provider_automation_policy.md` | 当前 provider/ATCC boundary policy，覆盖 no default provider download、credential/ToS/manual review/no automated ATCC downloader、future-design gates。 | 维护者、future implementer。 | 是，作为 provider 边界权威文档有效。 | 已吸收 feasibility/framework/gate/local-artifact 文档的必要摘要。 | 保留 |
| `docs/archive/provider_automation_feasibility.md` | provider/ATCC automation feasibility 历史设计与 safe route。 | 维护者、future implementer。 | 否，历史 feasibility；当前边界已并入 `docs/provider_automation_policy.md`。 | 与 provider policy/framework/gate review 重复。 | 已归档 |
| `docs/archive/atcc_downloader_gate_review.md` | ATCC downloader eligibility 历史 gate review。 | 维护者、合规审阅者。 | 否，negative gate decision 已摘要进 `docs/provider_automation_policy.md`。 | 与 provider policy 和 feasibility 文档重复。 | 已归档 |
| `docs/archive/v2_0_0_provider_automation_framework.md` | v2.0.0 provider automation framework 历史 design freeze。 | 维护者、future implementer。 | 否，future framework history；当前边界已并入 `docs/provider_automation_policy.md`。 | 与 provider policy/feasibility/gate review 重复。 | 已归档 |
| `docs/v1_0_0_readiness_review.md` | v1.0.0 readiness review 与 stable boundary。 | 维护者、发布审阅者。 | 部分有效；更多是历史 release readiness。 | 与 `docs/stable_contracts.md`, `docs/release_checklist.md`, `docs/index.md` 重复。 | 归档 |
| `docs/v0_8_0_implementation_plan.md` | v0.8.0 hardening/validation implementation plan。 | 维护者。 | 否，阶段计划。 | 当前行为已由 completion/external/docs 合约覆盖。 | 归档 |
| `docs/archive/v0_9_0_provider_adapter_spike_plan.md` | v0.9.0 provider adapter spike plan。 | 维护者、future implementer。 | 否，历史 spike plan；当前边界已并入 `docs/provider_automation_policy.md`。 | 与 provider automation policy/framework/feasibility 重复。 | 已归档 |
| `docs/v2_2_0_release_verification.md` | v2.2.0 release verification runbook 和 TSV recording contract。 | 发布审阅者、历史追溯。 | 否，当前已由 `docs/release_verification.md` 接管。 | 与 current release verification 重复，且使用旧 `results/v2_2_0_release_verification` 路径。 | 归档 |
| `docs/v2_2_2_enterobacter_baseline.md` | v2.2.2 Enterobacter baseline。 | 发布审阅者、历史追溯。 | 否，阶段性 baseline。 | 与 release notes / release verification 的 history 重复。 | 归档 |
| `docs/v2_2_3_expanded_discovery_baseline.md` | v2.2.3 expanded discovery baseline。 | 发布审阅者、历史追溯。 | 否，阶段性 baseline。 | 与 `docs/release_verification.md`, `docs/release_notes_v2_2_x.md` 重复。 | 归档 |
| `docs/v2_2_4_ncbi_taxonomy_baseline.md` | v2.2.4 NCBI Taxonomy enrichment baseline。 | 发布审阅者、历史追溯。 | 否，阶段性 baseline。 | 与 release notes/current verification history 重复。 | 归档 |
| `docs/v2_2_x_acceptance_checklist.md` | v2.2.2-v2.2.4 integration acceptance checklist。 | 发布审阅者。 | 否，旧阶段 checklist。 | 与 current `docs/release_checklist.md` 和 release notes 重复。 | 归档 |
| `docs/archive/pr_description_v2_2_x.md` | v2.2.x PR description draft。 | 发布审阅者。 | 否，stale PR 草稿，已归档。 | 与 release notes / release verification / acceptance checklist 重复。 | 归档 |
| `docs/archive/README.md` | archive inventory、retention rules、deleted evidence summaries。 | 维护者、历史追溯读者。 | 是，作为 archive 索引有效。 | 与 `docs/index.md` archive section 重复。 | 保留 |
| `docs/archive/ncbi_candidate_discovery_phase22.md` | Phase 22 NCBI candidate discovery historical design。 | 维护者、历史追溯读者。 | 否，历史计划。 | 当前 discovery 行为已分散在 LPSN/acquisition/schema/status docs。 | 保留 |
| `docs/archive/run_evidence/fusobacterium_v0_5_0/README.md` | compact v0.5.0 Fusobacterium evidence index。 | 维护者、历史追溯读者。 | 否，archive evidence。 | 与 archive README 和 nested evidence docs 重复。 | 保留 |
| `docs/archive/run_evidence/fusobacterium_v0_5_0/delivery/README.md` | Fusobacterium 16/17 delivery archived evidence。 | 历史追溯读者。 | 否，archive evidence。 | 与 final audit/current status 有事实重复。 | 保留 |
| `docs/archive/run_evidence/fusobacterium_v0_5_0/final_audit/current_status.md` | Fusobacterium final audit status evidence。 | 历史追溯读者。 | 否，archive evidence。 | 与 delivery README 重复。 | 保留 |
| `docs/archive/run_evidence/fusobacterium_v0_5_0/mortiferum_final_review/mortiferum_final_decision.md` | `F. mortiferum` final non-selection rationale。 | 历史追溯读者、curator。 | 否，archive evidence。 | 与 Fusobacterium delivery/current status 互补。 | 保留 |
| `docs/archive/run_evidence/phase15_smoke/README.md` | Phase 15 smoke run compact evidence index。 | 历史追溯读者。 | 否，archive evidence。 | 与 archive README 重复。 | 保留 |
| `docs/archive/run_evidence/phase15_smoke/actinocorallia/report/summary.md` | Archived generated summary for Actinocorallia smoke run。 | 历史追溯读者。 | 否，archive generated evidence。 | 与 Phase 15 smoke README 重复。 | 保留 |
| `docs/roadmap/v2.2.10-ux-followups.md` | v2.2.10 UX/reporting follow-up checklist from v2.2.9 validation。 | 维护者、历史追溯读者。 | 否，阶段性 roadmap。 | 与 release notes / release verification 的 v2.2.10 history 重复。 | 归档 |
| `docs/roadmap/v2.2.12-maintenance-plan.md` | v2.2.12 maintenance staged plan and dedup notes。 | 维护者。 | 部分有效；当前 release 后更像 history。 | 与 release checklist、release verification、release notes 的 current 2.2.12 内容重复。 | 归档 |
| `docs/validation/v2.2.9-real-world-validation.md` | v2.2.9 real-world validation evidence。 | 发布审阅者、历史追溯读者。 | 否，validation evidence。 | 与 v2.2.10 roadmap and release notes 重复。 | 归档 |

## Current Top-Level Docs Candidates To Keep

These are the strongest candidates to remain in `docs/` top level after a
future flattening/dedup pass:

- `docs/index.md`
- `docs/cookbook.md`
- `docs/design.md`
- `docs/stable_contracts.md`
- `docs/output_layout.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/species_checklist_audit.md`
- `docs/completion_audit.md`
- `docs/handoff_index_contract.md`
- `docs/maintenance.md`
- `docs/release_process.md`
- `docs/release_checklist.md`
- `docs/release_verification.md`
- `docs/release_notes_v2_2_x.md`

Conditional top-level candidates:

- `docs/lpsn_first_acquisition.md`: keep only if it is shortened into the
  canonical detailed acquisition guide; otherwise split current contract from
  implementation history.
- `docs/external_type_genome_ingestion.md`: canonical external registration
  design, boundary, and data-contract entry.
- `docs/external_workflow_cookbook.md`: short operator workflow for manual
  external FASTA registration.
- `docs/provider_automation_policy.md`: keep as the canonical provider/ATCC
  boundary policy after consolidating feasibility, gate review, framework,
  spike, and local-artifact-normalization history into archive.

## Suggested Archive Candidates

Historical or stage-specific files that should probably move out of docs top
level or stay under historical folders:

- `docs/archive/fusobacterium_external_pilot.md` has already replaced the old
  top-level Fusobacterium pilot path.
- `docs/archive/fusobacterium_real_pilot_template.md` has already replaced the
  old top-level Fusobacterium template path.
- `docs/provider_automation_feasibility.md`
- `docs/atcc_downloader_gate_review.md`
- `docs/local_artifact_normalization_design.md`
- `docs/v0_8_0_implementation_plan.md`
- `docs/v0_9_0_provider_adapter_spike_plan.md`
- `docs/v2_0_0_provider_automation_framework.md`
- `docs/v1_0_0_readiness_review.md`
- `docs/v2_2_0_release_verification.md`
- `docs/v2_2_2_enterobacter_baseline.md`
- `docs/v2_2_3_expanded_discovery_baseline.md`
- `docs/v2_2_4_ncbi_taxonomy_baseline.md`
- `docs/v2_2_x_acceptance_checklist.md`
- `docs/roadmap/v2.2.10-ux-followups.md`
- `docs/roadmap/v2.2.12-maintenance-plan.md`
- `docs/validation/v2.2.9-real-world-validation.md`

Deletion candidate:

- None for the current release-doc pass. `docs/archive/pr_description_v2_2_x.md`
  is retained as historical PR-draft context.

Already archived and recommended to remain archived:

- `docs/archive/README.md`
- `docs/archive/ncbi_candidate_discovery_phase22.md`
- `docs/archive/run_evidence/fusobacterium_v0_5_0/`
- `docs/archive/run_evidence/phase15_smoke/`

## Merge Or Dedup Groups

| Group | Files | Issue | Suggested direction |
| --- | --- | --- | --- |
| Documentation map and maintenance layers | `README.md`, `docs/index.md`, `docs/maintenance.md` | All describe where docs live and what is current. | Keep README as user entry, `docs/index.md` as map, `docs/maintenance.md` as maintainer rules; remove route/version prose from secondary surfaces later. |
| Output workspace and path policy | `README.md`, `docs/output_layout.md`, `docs/cookbook.md`, `docs/release_checklist.md`, `docs/release_process.md`, `docs/release_verification.md` | Repeats `TYPETREEFLOW_WORKSPACE`, `<workspace>/runs`, `<workspace>/deliveries`, `results/`, `typetreeflow_out/`, and `--outdir` precedence. | Make `docs/output_layout.md` canonical; keep short summaries elsewhere with links only. |
| Release process/checklist/verification | `docs/release_process.md`, `docs/release_checklist.md`, `docs/release_verification.md`, `docs/release_notes_v2_2_x.md`, `docs/v2_2_x_acceptance_checklist.md`, `docs/v2_2_0_release_verification.md` | Current process, execution checklist, verification behavior, historical matrix, and acceptance checklist overlap. | Keep current three-doc split: process, checklist, verification. Archive old v2.2.0/v2.2.x acceptance docs. |
| LPSN/checklist/acquisition contract | `docs/lpsn_first_acquisition.md`, `docs/species_checklist_audit.md`, `docs/output_layout.md`, `docs/schemas.md`, `docs/statuses.md`, `README.md` | Detailed LPSN guide repeats output/schema/status contracts. | Keep feature docs narrow: behavior overview in LPSN guide, schema/status/path details in canonical contract docs. |
| External genome workflow | `docs/external_type_genome_ingestion.md`, `docs/external_workflow_cookbook.md`, `docs/archive/fusobacterium_external_pilot.md`, `docs/archive/fusobacterium_real_pilot_template.md`, `docs/completion_audit.md` | General design, cookbook, completion metrics, and Fusobacterium case templates historically overlapped. | Current split: design/data contract in `external_type_genome_ingestion`, short operator path in `external_workflow_cookbook`, completion/gap counting in `completion_audit`, and Fusobacterium material as archive/examples only. |
| Provider/ATCC boundary | `docs/provider_automation_policy.md`, `docs/archive/provider_automation_feasibility.md`, `docs/archive/atcc_downloader_gate_review.md`, `docs/archive/local_artifact_normalization_design.md`, `docs/archive/v0_9_0_provider_adapter_spike_plan.md`, `docs/archive/v2_0_0_provider_automation_framework.md` | Multiple historical docs repeated no-default-provider-download, credential, gate, local-artifact, and review-only planning boundaries. | Current policy has been consolidated into one canonical provider boundary doc; archived files are history only. |
| v2.2.x historical evidence | `docs/release_notes_v2_2_x.md`, `docs/release_verification.md`, `docs/validation/v2.2.9-real-world-validation.md`, `docs/roadmap/v2.2.10-ux-followups.md`, `docs/roadmap/v2.2.12-maintenance-plan.md`, `docs/v2_2_2_*`, `docs/v2_2_3_*`, `docs/v2_2_4_*` | Release history is split across current docs, validation notes, roadmap notes, and baseline files. | Keep release notes and current verification summary; archive validation/roadmap/baseline details. |
| Archive evidence index | `docs/archive/README.md`, nested `docs/archive/run_evidence/` READMEs, `docs/index.md` archive sections | Archive entries are listed in both current map and archive README. | Keep `docs/index.md` as pointer only; keep detailed retention rationale in `docs/archive/README.md`. |

## Broken Links, Path Risks, And Old Output Path Risks

### Broken links

- No broken local Markdown links were found by the read-only link check over
  `README.md` and `docs/**/*.md`.

### Path and wording risks

- `README.md` and current operational docs now consistently state that omitted
  `--outdir` writes to a workspace default and that explicit `--outdir` wins.
  This is good, but the same rule appears in several places and can drift.
- `results/` is currently described as reserved for curated, small, trackable
  verification evidence. Historical docs and archived evidence still cite many
  `results/...` paths. This is acceptable for archive/history, but risky in
  top-level stage docs.
- `typetreeflow_out/` is consistently described as old default or historical
  example in current docs. Keep that wording centralized to avoid accidentally
  reviving it as a recommended output path.
- `docs/v2_2_0_release_verification.md` uses `results/v2_2_0_release_verification`
  as an approved verification directory. That conflicts with the current
  workspace-first guidance if read as current. It should be clearly historical
  or archived.
- `docs/archive/v0_9_0_provider_adapter_spike_plan.md` contains
  `--outdir results/provider_spike`, which is a historical/stage example and
  conflicts with current guidance for real or large outputs.
- `docs/schemas.md` still references legacy Fusobacterium audit outputs under
  `results/fusobacterium_final_audit_v2/...`. This may be acceptable as a
  legacy note, but it should not be confused with current canonical output
  layout.
- `docs/validation/v2.2.9-real-world-validation.md` and archive run evidence
  cite `results/v2_2_9_*` and `results/fusobacterium_*` directories. These are
  evidence paths, not current recommendations.
- README still has a release-verification example using
  `<workspace>/runs/release/v2_2_9_release_verification` inside the current
  recommended workflow section. The surrounding text frames it as v2.2.9
  history/reliability behavior, but it is close enough to current operator
  guidance that a future pass should either generalize the example or move the
  historical version anchor into `docs/release_verification.md`.
- `docs/roadmap/v2.2.12-maintenance-plan.md` records older v2.2.11 audit line
  references while the current README has moved to 2.2.12. This is useful
  history but should be archived to prevent readers treating old line numbers
  as current.

## Next Restructuring Recommendation

1. First define the final top-level set around current contracts and
   operations: `index`, `cookbook`, `design`, `stable_contracts`,
   `output_layout`, `schemas`, `statuses`, `species_checklist_audit`,
   `completion_audit`, `handoff_index_contract`, `maintenance`,
   `release_process`, `release_checklist`, `release_verification`, and
   `release_notes_v2_2_x`.
2. Move stage-specific release baselines, roadmap notes, validation notes, and
   Fusobacterium pilot templates into archive/history buckets, preserving
   links through `docs/archive/README.md`.
3. Provider/ATCC documents have been consolidated into
   `docs/provider_automation_policy.md`; feasibility, ATCC gate review,
   local-artifact normalization, spike, and framework notes are archived
   history.
4. Preserve the current external split: canonical design/data contract,
   short cookbook path, completion/gap contract, and Fusobacterium-specific
   archive/examples case material.
5. After moves are planned, update `README.md` and `docs/index.md` together and
   run the docs consistency tests plus a local Markdown link check.
