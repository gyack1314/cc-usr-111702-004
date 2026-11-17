# 企业召回公告资料约定

## 文档类型与身份

每类资料都以 (类型, 标识, 版次) 为身份,各自保留来源收据与生效版次:

- `notice`/`revision`:企业公告正文;字段 `effective`、`product`、`attachments`(附件清单标识)、`registration`(产品注册信息标识,可选)。
- `attachments`/`revision`:附件清单;`entries` 逐项钉住附件 `id` 与 `revision`,`kind` 为 `ranges`(批号附件)或 `distribution`(流通清单)。更换附件即清单升版并改钉新版次。
- `annex`/`revision`:批号附件;`ranges` 为批号级单元 `(batch, region, status)`。
- `registration`/`revision`:产品注册信息(`product`、`approval_no`、`holder`、`status`)。
- `distribution`/`revision`:流通清单,可能晚到;晚到期间记为待补缺口。
- `correction`/`revision`:更正;`target` 明确指向 `annex`@版次(以 `ranges` 覆盖列出的单元)或 `notice`@版次(以 `set` 覆盖列出的字段)。更正只影响其明确覆盖的范围,目标版次未生效时不外溢到其他版次。
- `media`:媒体报道;只允许 `group_quantities` 组级数量,出现 `ranges` 批号级范围即拒收。组级数量仅作线索展示,绝不展开为批号。

`status` 取值 `confirmed` / `pending_confirmation` / `cleared`;`pending_confirmation` 不是正式确认。

## 版本、来源与观察时间

- 每份原文先入 `receipts`(含来源地址与 `observed_at`),实体版本入 `entities` 并记录首次接收时间 `recorded_at`;两者同事务写入。
- 相同 (类型, 标识, 版次) 的不同原文由账本事务拒绝并整体回滚。
- 重复抓取与站点短暂回退重发的旧版原文均为幂等空操作,不抹掉已接收的新版次。
- `overview(as_of=...)` 按指定观察时间回放:只取 `recorded_at` 不晚于该时刻的版本,每个标识的生效版次为其中最高版次;无时间戳的旧资料始终可见。

## 范围解释

- 已确认召回范围 = 生效附件清单钉住的批号附件中 `confirmed` 单元,加上作用于该版次的更正明确覆盖的单元;每个单元带来源摘要、来源站与接收时间。
- 清单钉住的版次未接收时记待补缺口;已接收更新版次但清单未改钉时只记备注,不提前生效。
- 企业站与监管站对同一 `(batch, region)` 同时给出 `confirmed` 与 `cleared` 时,双方陈述都保留在 `conflicts` 中;公告品名与注册信息不一致同样保留。
- 附件未接收、流通清单未接收、注册信息未接收均记为待补缺口;存在缺口、待确认或冲突时 `publishable` 为假。

normal.json 为简版公告加待确认批号;conflict.json 在首份原文之后给出同一实体版本的不同内容;timeline.json 带观察时间,覆盖附件升版、流通清单晚到、限定范围的更正、监管站冲突、媒体组级数量与站点回退。未闭合的来源不能被解释成最终处置结果。
