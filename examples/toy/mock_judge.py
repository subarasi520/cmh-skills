"""Keyword stand-in for a judge model (toy example only; deliberately imperfect).

It reads the prompt on stdin and answers TARGET / OTHER / UNSURE from surface
cues, the way a weak model might. It makes the kinds of mistakes the CMH
workflow is built to catch: it fires on 'computer' in a room description and
on '计算' inside '白云计算机厂'.
"""
import re
import sys

CUES = ["computer", "screen", "click", "cursor", "upload", "server", "touch",
        "偶像", "明星", "签名", "计算", "硬盘", "杀毒", "软件", "存储", "服务器"]

prompt = sys.stdin.read()
match = re.search(r"^Passage: (.*)$", prompt, flags=re.M)
passage = match.group(1) if match else ""
if passage.endswith(("?", "？")):
    print("UNSURE")
elif any(cue in passage.lower() for cue in CUES):
    print("TARGET")
else:
    print("OTHER")
