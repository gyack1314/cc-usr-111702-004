# 企业召回公告与流通批次的版本化抓取

企业正文和批号附件按版本保存；附件中的待确认范围不会自动变成已生效召回范围。

现有项目从冻结来源响应读取资料，由 transport 保证请求与原文字节身份，domain 解释本领域字段，ledger 保存版本和原始收据，view 展示已确认内容与缺口。样例为合成资料，不访问真实监管站或企业系统。

Python 3.11 以上；在项目根目录执行：

    python -m unittest discover -s tests -v
    python -m compileall -q capture_service tests
    python -m capture_service.cli inspect data/normal.json

Dockerfile 提供 Linux 环境；docker build -t recall-bulletin . 构建，docker run --rm recall-bulletin 运行样例。
