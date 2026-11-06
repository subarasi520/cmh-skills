# Contributing / 参与贡献

Thank you for helping. A few rules keep the project usable and safe for everyone.
感谢参与。下面几条规则让这个项目对所有人都可用、安全。

1. **Synthetic data only.** Examples and tests use invented text. No real corpus excerpts, no
   personal data, no copyrighted material. 示例和测试只用编造的文本：不放真实语料片段、个人信息或受版权保护的材料。
2. **No secrets.** No keys, tokens, private URLs or local paths in commits.
   不提交密钥、令牌、私有网址或本机路径。
3. **Standard library only** for the scripts, Python 3.11+. 脚本只用标准库，Python 3.11 及以上。
4. **Tests.** Run `python -m unittest discover -s tests` before a pull request. Any change to a
   statistic needs a test with a value that can be checked by hand.
   提交前运行测试；统计方法的任何改动，都要附一个能手算核对的测试。
5. **Both languages.** Documentation exists in English and Chinese (`*.zh-CN.md`). Change both, or
   say in the pull request which one needs a translation.
   文档有中英两版（`*.zh-CN.md`）。两版一起改，或者在 pull request 里说明哪一版还需要翻译。
6. **Plain claims.** Describe what a change does and what it does not do. The documentation should
   never promise more than the code checks.
   如实描述改动做了什么、没做什么。文档承诺的，不能超过代码实际检查的。
