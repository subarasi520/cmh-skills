# Security / 安全

## What the code does / 代码做什么

- Reads and writes only the files given on the command line (and files referenced by configuration
  files you pass in). 只读写命令行里指定的文件（以及你传入的配置文件所引用的文件）。
- **Network**: only `cmh_judge.py`, only with the `openai_compatible` backend, only to the
  `base_url` in your configuration. No telemetry, no update checks.
  **网络**：只有 `cmh_judge.py` 在使用 `openai_compatible` 后端时，才会访问配置里的 `base_url`。没有遥测，不检查更新。
- **Processes**: `cmh_judge.py` with the `command` backend runs the program in `argv` (as a list,
  never through a shell). `cmh_protocol.py` and `cmh_sheet.py` may run read-only `git` commands
  (`rev-parse`, `status`, `check-ignore`).
  **进程**：`cmh_judge.py` 的 `command` 后端运行 `argv` 里的程序（以列表形式，从不经过 shell）。`cmh_protocol.py` 和 `cmh_sheet.py` 可能运行只读的 `git` 命令。
- No `eval`, `exec` or `pickle`. Prompt templates use `string.Template` substitution only.
  不使用 `eval`、`exec`、`pickle`；提示词模板只做 `string.Template` 替换。
- API keys are read from environment variables named in the configuration and are never written
  to the ledger or any output. 密钥只从配置里指定的环境变量读取，从不写入台账或任何输出。
- Annotation sheets escape cells that spreadsheets could execute as formulas.
  标注卷会转义可能被表格软件当作公式执行的单元格。

## Your part / 你需要注意的

- Treat configuration files from others as code: a `command` backend executes a program.
  把别人提供的配置文件当作代码对待：`command` 后端会执行程序。
- Keep keys in environment variables, not in files. Use `https` for remote endpoints.
  密钥放在环境变量里，不要写进文件；远程接口用 `https`。
- Do not commit corpora, answer keys, ledgers that contain corpus text, or keys.
  不要提交语料、答案键、含语料原文的台账或密钥。

## Reporting a vulnerability / 报告安全问题

Please use GitHub's private vulnerability reporting: the **Security** tab of this repository →
**Report a vulnerability**. Do not open a public issue for a security problem. Only the latest
version on the default branch is maintained.

请使用 GitHub 的私密漏洞报告：本仓库的 **Security** 页 → **Report a vulnerability**。安全问题请不要开公开 issue。只维护默认分支上的最新版本。
