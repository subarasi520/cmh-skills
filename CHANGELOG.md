# Changelog / 更新日志

## v1.0.0 (2026-11-06)

First public version. 首个公开版本。

- Skill `cmh-corpus-verification` in the Agent Skills format (`SKILL.md`), with a Chinese version
  of the skill and of every reference. 采用 Agent Skills 格式，skill 本体和全部参考文件都有中文版。
- References: workflow, scenarios, evidence, human annotation, statistics, failure patterns, glossary.
  参考文件：工作流程、适用场景、证据、人工标注、统计方法、常见失误、术语表。
- Templates: protocol, judge / audit / coding prompts, configurations, triage rules, table checks,
  number registry, annotator guide. 模板：协议、提示词、配置、分流规则、结论表核对、数字登记表、标注说明。
- Scripts (Python 3.11+, standard library only): `cmh_protocol`, `cmh_judge`, `cmh_aggregate`,
  `cmh_triage`, `cmh_sheet`, `cmh_agreement`, `cmh_evaluate`, `cmh_check`, `cmh_numbers`.
  脚本只用 Python 标准库。
- Synthetic end-to-end example and tests. 合成数据的端到端示例与测试。
