"""Keyword stand-in for an audit model (toy example only; deliberately imperfect).

Stricter than the judge: it accepts only passages with a strong cue and
rejects known traps, so it catches some judge errors and wrongly rejects
some valid evidence.
"""
import re
import sys

STRONG = ["cursor", "upload", "servers", "touch", "button",
          "偶像", "明星", "硬盘", "杀毒", "云端", "服务器"]
TRAPS = ["白云计算机"]

prompt = sys.stdin.read()
match = re.search(r"^Passage: (.*)$", prompt, flags=re.M)
passage = match.group(1) if match else ""
if any(trap in passage for trap in TRAPS):
    print("REJECT")
elif any(cue in passage.lower() for cue in STRONG):
    print("ACCEPT")
else:
    print("REJECT")
