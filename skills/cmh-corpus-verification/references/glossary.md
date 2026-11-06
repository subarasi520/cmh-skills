# Glossary / 术语表

| English | 中文 | Meaning / 含义 |
|---|---|---|
| CMH (Corpus–Model–Human) | 语料—模型—人 | the verification design described here / 本 skill 介绍的核验设计 |
| unit | 单元 | one row of the results table (a concept, a form, a document…) / 结论表的一行 |
| instance | 实例 | one retrieved passage judged by a reader or a model / 一条被判读的检索结果 |
| target sense / category | 目标义／类别 | the property judged per instance / 每条实例要判的属性 |
| definition, codebook | 定义、编码手册 | the written criterion readers and models apply / 读者和模型共同依据的书面标准 |
| corpus nomination | 语料提名 | candidates come from scanning the corpus or a closed list, not from memory / 候选来自语料扫描或封闭名单，而不是记忆 |
| closed list | 封闭名单 | an enumerable external list used in full / 可穷举、完整使用的外部名单 |
| judge layer | 判读层 | the model that labels every instance / 逐条判读的模型 |
| audit layer | 审计层 | a differently configured model that re-checks selected claims / 配置不同、复查部分结论的模型 |
| anchor | 锚点 | the instance a dating claim rests on / 定年结论所依据的那条实例 |
| false anchor | 假锚 | an anchor that does not carry the target sense / 没有用目标义的锚点 |
| abstention | 弃权 | no claim because the evidence does not support one / 证据不足时不下结论 |
| triage | 分流 | stated rules that send risky claims to review / 按写明的规则把可疑结论送去复核 |
| review queue | 待核队列 | claims flagged by triage / 被分流规则标出的结论 |
| spot check | 抽查 | a seeded random sample of unflagged claims / 未标记结论中带种子的随机样本 |
| overturn, false overturn | 推翻、误推翻 | the audit rejects a claim; … a valid one / 审计否决结论；否决了本来成立的结论 |
| precision (of an audit) | 精确率 | share of overturns that were correct / 推翻里推翻对了的比例 |
| catch rate | 捕获率 | share of false claims the audit overturned / 假结论中被审计推翻的比例 |
| residual error | 剩余错误率 | share of false claims left after a condition / 某条件跑完后剩下的结论里假的比例 |
| evidence tier | 证据层级 | the strength of the evidence a claim rests on / 结论所依据证据的强弱等级 |
| upper bound | 上界 | a value the truth can only be earlier than (or below) / 真实值只可能更早（更小） |
| censoring (left) | 左删失 | a value at the start of the observation window / 落在观察窗起点上的值 |
| observation window | 观察窗 | the period a source covers / 一个来源覆盖的时间范围 |
| results table (single source of truth) | 结论表（单一事实源） | the one table every reported number comes from / 所有报告数字的唯一来源 |
| ledger | 台账 | append-only record of every model call / 只追加的模型调用记录 |
| protocol lock | 协议锁 | hashes of the frozen protocol files / 冻结协议文件的哈希 |
| blind sheet | 盲判卷 | items for annotators with sources hidden / 隐去来源的标注卷 |
| answer key | 答案键 | the map from sheet items back to sources / 卷面条目对应来源的表 |
| yardstick (human baseline) | 标尺（人类基线） | human agreement every layer is read against / 衡量每一层所对照的人的一致度 |
| adjudication | 裁决 | the researcher's ruling on a boundary case / 研究者对边界情况的裁定 |
| segmentation passthrough | 切分穿透 | a string match that crosses a word boundary / 字符串匹配跨过了词的边界 |
| specific agreement (p_pos, p_neg) | 特异一致率（正类／负类） | agreement on positive or on negative decisions / 正类判定或负类判定上的一致 |
| miss rate | 漏报率 | true positives among items judged negative / 判为否的条目中其实为是的比例 |
| instruments | 仪表（可观测接口） | read-only views recomputed when the table changes / 结论表变化时自动重算的只读视图 |
| exploratory analysis | 探索性分析 | an analysis added after the protocol was frozen / 冻结协议之后加的分析 |
