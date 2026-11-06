# Toy example / 玩具示例

**Everything here is invented**: the passages, the years and the reader judgements exist only to
show the workflow. They are not attestation data and must not be cited.
**这里的一切都是编的**：句子、年份和读者判定只用来演示流程，不是任何真实的考证数据，不可引用。

```bash
python3 examples/toy/run_example.py
```

Runs offline in a few seconds. The "models" are keyword stand-ins (`mock_judge.py`,
`mock_audit.py`) and three readers are simulated (`simulate_annotators.py`). Outputs go to `out/`.
离线运行，几秒钟完成。“模型”是关键词替身，三位读者是模拟的。输出在 `out/`。

## What it shows / 演示了什么

| Unit / 单元 | What happens / 发生了什么 | Mechanism / 机制 |
|---|---|---|
| mouse | the earliest target-sense passage sits in the first year of the corpus | window edge → reported as an upper bound / 窗口边缘 → 按上界报告 |
| cloud | the judge takes "computer room" as the computing sense; the next real use is 17 years later | isolated early anchor → triage → audit rejects it / 孤立早期锚点 → 分流 → 审计否决 |
| 云 | the judge matches 云计算 inside 白云计算机厂 (a factory name) | segmentation trap + single-character rule → audit rejects it / 切分穿透＋单字规则 → 审计否决 |
| tablet | the audit wrongly rejects a valid passage | audit precision is measured, not assumed / 审计精确率要测，不能假定 |
| all | three readers label the anchors blind; reader B disagrees twice | agreement measured among humans first / 先测人与人的一致度 |

The final step checks every number in `report.md` against the output files.
最后一步把 `report.md` 里的每个数字都对回输出文件。
