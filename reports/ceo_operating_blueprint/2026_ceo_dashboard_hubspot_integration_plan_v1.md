# 2026 CEO Dashboard

## HubSpot Integration Plan v1

Date: 2026-03-22  
Status: Draft for implementation  
Scope: CEO Dashboard commercial layer (HubSpot side)

## 1. 目标与边界

本方案用于把 HubSpot 接入 CEO Dashboard，优先补齐商业侧指标（pipeline、forecast、won、owner、region）。

关键边界：

- `Revenue Actual YTD` 继续使用已锁定的 Lark 来源（Finance current SoT）。
- HubSpot 不替代 Recognized Revenue 口径，只提供商业生产与预测口径。

## 2. 当前可访问的 HubSpot 对象（拟接入清单）

说明：仓库当前未发现已落地 HubSpot API 代码或历史导出，因此以下为 `MVP 目标访问对象`，上线前需用一次权限探测脚本做最终确认。

| 对象 | HubSpot API 名称 | 用途 | MVP 优先级 |
|---|---|---|---|
| Deals | `crm/v3/objects/deals` | Pipeline、Forecast、Won Revenue、阶段分析 | P0 |
| Companies | `crm/v3/objects/companies` | Region 映射、行业/分层、账户归属 | P0 |
| Contacts | `crm/v3/objects/contacts` | 次要关联（可选） | P2 |
| Owners | `crm/v3/owners/` | Region/Deal Owner 映射 | P0 |
| Pipelines & Stages | `crm/v3/pipelines/deals` | 统一阶段过滤（qualified stage） | P0 |
| Line Items | `crm/v3/objects/line_items` | 产品拆分/新产品归因 | P1 |
| Associations | `crm/v4/associations/*` | Deal-Company/Contact 关联 | P0 |
| Engagements/Activities | calls/emails/meetings objects | 销售活动效率（非 CEO MVP 核心） | P2 |

## 3. CEO Dashboard 所需字段清单（HubSpot侧）

## 3.1 Deal 级字段（P0）

- `dealId`
- `dealname`
- `amount`
- `dealstage`
- `pipeline`
- `closedate`
- `createdate`
- `hs_lastmodifieddate`
- `hubspot_owner_id`
- `forecast_category`（若启用）
- `probability`（若启用）
- `dealtype`（new business / existing business）
- `is_closed_won`（由阶段派生）
- `company_id`（通过 association）

## 3.2 Company 级字段（P0）

- `companyId`
- `name`
- `domain`
- `country`
- `region_code`（如有自定义字段，优先用）
- `segment`（Enterprise/SMB 等）
- `owner_id`（可选）

## 3.3 Owner / Pipeline 字段（P0）

- `owner_id`
- `owner_name`
- `owner_email`
- `pipeline_id`
- `pipeline_label`
- `stage_id`
- `stage_label`
- `stage_order`
- `is_closed`
- `is_won`

## 3.4 P1 扩展字段

- `line_item_id`
- `product_sku` / `product_family`
- `line_item_amount`
- `discount` / `effective_price`
- `renewal_flag` / `expansion_flag`（若有自定义字段）

## 4. HubSpot 字段到 Dashboard 指标映射表

| Dashboard 指标 | 计算口径 | HubSpot 字段来源 | 说明 |
|---|---|---|---|
| New Logos Pipeline Coverage | `Qualified pipeline amount / near-term target` | deals.amount + deals.dealstage + pipelines.stages | qualified stage 由 RevOps 锁定 |
| Region Pipeline Coverage | `Region qualified pipeline / region target` | deals + companies.region_code | region 优先 company 主数据 |
| Region Won Revenue YTD | `YTD closed-won amount` | deals.amount + deals.closedate + won stage | 商业口径，不等于 recognized revenue |
| Region Forecast | `sum(weighted or commit forecast)` | deals.amount + forecast_category/probability + closedate | 权重规则需锁定 |
| Region Owner | `single DRI` | owners + company/deal owner mapping | 强制一地一主责 |
| Next 90-Day Forecast | `next 90d expected amount` | deals.amount + closedate + stage filter | 以 close date 窗口筛选 |
| New Products 贡献（P1） | `product-linked amount` | line_items + deals associations | 需产品归因规则 |
| Price Leakage（P1/P2） | `discount impact vs baseline` | line_items/discount custom fields | 若字段不足先导出过渡 |

## 5. 同步方式：API 还是导出过渡

结论：采用 `API 为主 + 导出兜底` 的双轨方案。

## 5.1 API 主链路（推荐）

- 方式：HubSpot Private App Token 调用 REST API
- 优点：自动化、可增量、可审计、延迟低
- 适用：Deals / Companies / Owners / Pipelines / Associations（P0）

## 5.2 导出过渡链路（补位）

- 方式：手工或半自动 CSV 导出（HubSpot 报表/列表）
- 优点：上线快、对权限要求低
- 缺点：口径漂移风险高、审计和重跑弱
- 适用：Line items、price/discount、renewal/expansion 标记未就绪时（P1 过渡）

## 5.3 推荐落地

- P0：全部走 API（Deals/Companies/Owners/Pipelines）
- P1：产品与价格相关字段若 API 权限未批复，先导出过渡 2-4 周
- P2：全部切回 API，关闭手工导出

## 6. MVP 先接哪些字段，哪些后接

## 6.1 MVP 先接（P0，2周内）

- 对象：Deals、Companies、Owners、Pipelines、Associations
- 指标：
  - New Logos Pipeline Coverage
  - Region Pipeline Coverage
  - Region Won Revenue YTD（商业口径）
  - Region Forecast
  - Region Owner
  - Next 90-Day Forecast

## 6.2 后接（P1，2-6周）

- 对象：Line Items（+必要自定义字段）
- 指标：
  - New Products 贡献
  - Expansion 归因增强
  - Price Leakage 初版

## 6.3 最后接（P2，6周+）

- 对象：Engagements/Activities、更多自定义对象
- 指标：
  - 活动效率与转化链路
  - 细粒度销售动作归因

## 7. 技术实施建议（简版）

1. 新增 `scripts/sync_ceo_dashboard_from_hubspot.py`
2. 输出标准化文件：`reports/ceo_dashboard/hubspot_source_latest.json`
3. 增加历史快照：`reports/ceo_dashboard/hubspot_history_*.csv`
4. 新增 workflow：`ceo-dashboard-hubspot-sync.yml`
5. 与现有 Lark 结果在语义层合并，形成 CEO Dashboard 单一输入

## 8. 风险与控制

- 风险：阶段定义不统一 -> 控制：锁定 stage whitelist（RevOps owner）
- 风险：region 归属冲突 -> 控制：Company 主数据优先，禁止报表端手改
- 风险：商业口径与财务口径混用 -> 控制：Dashboard 明确标注 `Commercial` vs `Recognized`
- 风险：字段缺失 -> 控制：P1 使用导出过渡并设置 sunset 日期

## 9. 建议的本周动作

1. HubSpot 管理员完成 Private App 建立与 scope 授权
2. 用 API 探测脚本确认 P0 对象可读
3. RevOps 锁定 qualified stages
4. BizOps 锁定 company->region 映射规则
5. 启动 P0 接口开发并跑两轮周更验收
