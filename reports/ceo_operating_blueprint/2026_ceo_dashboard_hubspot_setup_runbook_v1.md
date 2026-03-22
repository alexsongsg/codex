# 2026 CEO Dashboard

## HubSpot Setup Runbook v1

Date: 2026-03-22  
For: Enable `CEO Dashboard HubSpot Sync` workflow

## 1. 目标

打通 HubSpot 到 CEO Dashboard 的商业层数据链路，产出：

- `reports/ceo_dashboard/hubspot_source_latest.json`
- `reports/ceo_dashboard/hubspot_metrics_history.csv`

## 2. 一次性准备：HubSpot Private App

1. 登录 HubSpot 管理后台（管理员账号）。
2. 进入 `Settings -> Integrations -> Private Apps`。
3. 点击 `Create a private app`，命名例如 `CEO Dashboard Sync`。
4. 在 scopes 里至少勾选：
- `crm.objects.deals.read`
- `crm.objects.companies.read`
- `crm.objects.owners.read`
- `crm.schemas.deals.read`
- `crm.objects.contacts.read`（建议，便于后续扩展）
5. 创建后复制 Access Token。

这个 token 就是：

- `HUBSPOT_PRIVATE_APP_TOKEN`

## 3. 配置 GitHub Secrets

仓库 -> `Settings -> Secrets and variables -> Actions -> New repository secret`

必填：

- `HUBSPOT_PRIVATE_APP_TOKEN`

建议填写：

- `HUBSPOT_QUALIFIED_STAGE_IDS`
  - 逗号分隔，例如：`appointmentscheduled,qualifiedtobuy,presentationscheduled`
  - 若不填，脚本会自动用“未关闭阶段”做临时口径
- `HUBSPOT_REGION_TARGETS_JSON`
  - 可填一个仓库内 JSON 路径，例如：`data/input/hubspot/region_targets.json`
  - 用于计算 `Region Pipeline Coverage`
- `CEO_DASHBOARD_CURRENCY`（如 `USD`）

## 4. Qualified Stage IDs 怎么拿

方式 A（推荐，最快）：

- HubSpot 里打开 `Deals` pipeline 设置，记录你定义为 qualified 的 stage internal IDs。

方式 B（自动）：

- 先跑一次 workflow（`dry_run=true`），看 `hubspot-sync-output.json` 里 pipeline/stage 结构，再回填 `HUBSPOT_QUALIFIED_STAGE_IDS`。

## 5. 首次联调

1. 打开 GitHub Actions -> `CEO Dashboard HubSpot Sync`
2. 点 `Run workflow`
3. 参数：
- `dry_run=true`
- `as_of_date` 留空
4. 成功后检查输出中：
- `accessed_objects` 是否有非零记录（deals/companies/owners/pipelines）
- `company_totals` 是否有合理值

## 6. 正式运行

1. 再跑一次 `dry_run=false`
2. 确认产物文件被生成
3. 定时任务将按工作日自动刷新

## 7. 常见问题

- `Missing required secrets: HUBSPOT_PRIVATE_APP_TOKEN`
  - 未配置 token 或拼写错误
- `HubSpot API error ...`
  - token 无效或 scope 不足
- 指标为 0
  - 常见是 stage 口径未配置；先填 `HUBSPOT_QUALIFIED_STAGE_IDS`
- Region 全是 `UNKNOWN`
  - company 没有 `region_code`，需补公司主数据或国家到区域映射
