# 企业召回公告与流通批次的版本化抓取

企业公告、附件清单、产品注册信息、批号附件、流通清单、更正与媒体报道按 (类型, 标识, 版次) 保存,各自带来源收据与首次接收时间;附件中的待确认范围不会自动变成已生效召回范围,更正只影响其明确覆盖的范围,媒体组级数量不展开为批号。

现有项目从冻结来源响应读取资料,由 transport 保证请求与原文字节身份,domain 解释本领域字段,ledger 保存版本、接收时间和原始收据,view 按观察时间回放已确认内容与缺口。样例为合成资料,不访问真实监管站或企业系统。

Python 3.11 以上;在项目根目录执行:

    python -m unittest discover -s tests -v
    python -m compileall -q capture_service tests
    python -m capture_service.cli inspect data/normal.json
    python -m capture_service.cli inspect data/timeline.json --as-of 2026-11-20T09:30:00Z

`--as-of` 按指定观察时间回放当时已接收的版本:重复抓取和站点短暂回退不改变已确认范围,企业站与监管站的冲突陈述、晚到的流通清单缺口都会保留。

Dockerfile 提供 Linux 环境;docker build -t recall-bulletin . 构建,docker run --rm recall-bulletin 运行样例。
