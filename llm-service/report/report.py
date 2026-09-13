#!/usr/bin/env python3
"""llm-service 防护日报：拉汇总 → 生成 Markdown → 发到 hublog。

**为什么不让 llm-service 自己推**（两条都是硬约束）：

1. 它的 NetworkPolicy 出站只放行 DNS + 443，而 hublog 是集群内 http，出站就被挡；
2. 它自我定位是「不做业务逻辑」，写博客算业务。

**为什么报告里必须显示 `since`**：llm-service 的计数器在进程内存里，Pod 重启归零。
不显示起点的话，「重启后只统计了 2 小时」会被误读成「今天很干净」——那是这个报告
最容易造成的误解，所以把它写在正文最前面。

只依赖标准库，所以可以直接塞进 llm-service 的镜像里跑（见 Dockerfile）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_LLM_BASE_URL = "http://llm-service.llm.svc.cluster.local/v1"
DEFAULT_HUBLOG_BASE_URL = "http://hublog-api.hublog.svc.cluster.local"
REPORT_TAGS = ("llm-service", "日报", "安全")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_json(url: str, token: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body.strip() else {}


def render(report: dict, day: str) -> tuple[str, str]:
    """返回 (标题, Markdown 正文)。"""
    callers = report.get("callers") or {}
    since = report.get("since") or "未知"

    requests = sum(int(item.get("requests") or 0) for item in callers.values())
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in callers.values())
    completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in callers.values())
    leaks = sum(int(item.get("canary_leaks") or 0) for item in callers.values())
    rejected = sum(int(item.get("rejected") or 0) for item in callers.values())

    rule_totals: dict[str, int] = {}
    rule_last_caller: dict[str, str] = {}
    for caller, item in sorted(callers.items()):
        for rule, count in (item.get("detection_hits") or {}).items():
            if count:
                rule_totals[rule] = rule_totals.get(rule, 0) + int(count)
                rule_last_caller.setdefault(rule, caller)
    detections = sum(rule_totals.values())

    lines: list[str] = [
        f"# LLM 接入日报 · {day}",
        "",
        f"统计窗口：**自 `{since}`**（llm-service 本次启动）起。",
        "",
        "> 计数器在 llm-service 进程内存里，Pod 重启会归零。上面这个时间戳就是本次统计的真实起点——"
        "如果它离现在很近，说明数据只有很短一段，不代表当天很干净。",
        "",
        "## 总览",
        "",
        f"- 请求 **{requests:,}** 次 · prompt **{prompt_tokens:,}** tokens · completion **{completion_tokens:,}** tokens",
        f"- 检测命中 **{detections}** 次 · canary 泄漏 **{leaks}** 次 · 拦截 **{rejected}** 次",
        "",
    ]

    if callers:
        lines += [
            "## 按调用方",
            "",
            "| 调用方 | 请求 | prompt | completion | 检测命中 | canary |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for caller, item in sorted(callers.items(), key=lambda pair: -int(pair[1].get("requests") or 0)):
            hits = sum(int(v) for v in (item.get("detection_hits") or {}).values())
            lines.append(
                f"| `{caller}` | {int(item.get('requests') or 0):,} "
                f"| {int(item.get('prompt_tokens') or 0):,} | {int(item.get('completion_tokens') or 0):,} "
                f"| {hits} | {int(item.get('canary_leaks') or 0)} |"
            )
        lines.append("")

    lines += ["## 检测命中明细", ""]
    if rule_totals:
        lines += ["| 规则 | 次数 | 最近一次调用方 |", "|---|---:|---|"]
        for rule, count in sorted(rule_totals.items(), key=lambda pair: -pair[1]):
            lines.append(f"| `{rule}` | {count} | `{rule_last_caller.get(rule, '?')}` |")
    else:
        lines.append("本次窗口内没有命中。")
    lines.append("")

    lines += [
        "## 说明",
        "",
        "- 检测命中只代表**文本里出现了这些特征**，不代表一定是攻击；当前为「只记日志」模式，没有拦截。",
        "- spotlight 与 canary 只对 `guarded` 档生效（用户会写 prompt 的那一档）。",
        "- 日报由 llm-service 之外的独立任务生成，`/v1/guard/report` 只对白名单调用方开放。",
        "",
    ]
    return f"LLM 接入日报 · {day}", "\n".join(lines)


def main() -> int:
    base_url = _env("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).rstrip("/")
    llm_token = _env("LLM_SERVICE_TOKEN")
    hublog_url = _env("HUBLOG_BASE_URL", DEFAULT_HUBLOG_BASE_URL).rstrip("/")
    hublog_token = _env("HUBLOG_REPORT_TOKEN")
    timeout = float(_env("REPORT_TIMEOUT", "60"))
    dry_run = _env("REPORT_DRY_RUN").lower() in {"1", "true", "yes", "on"}

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not llm_token:
        print("ERROR: LLM_SERVICE_TOKEN 未注入（本任务需要 llm-report 调用方身份）", file=sys.stderr)
        return 2

    try:
        report = _get_json(f"{base_url}/guard/report", llm_token, timeout)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        print(f"ERROR: 拉取汇总失败 HTTP {error.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"ERROR: 连不上 llm-service（{base_url}）: {error}", file=sys.stderr)
        return 1

    title, content = render(report, day)

    if dry_run:
        print(content)
        return 0

    if not hublog_token:
        print("ERROR: HUBLOG_REPORT_TOKEN 未注入", file=sys.stderr)
        return 2

    payload = {
        "post_type": "article" if len(content) > 500 else "short",
        "visibility": "public",
        "title": title[:300],
        "content": content,
        "tags": list(REPORT_TAGS),
    }
    try:
        created = _post_json(
            f"{hublog_url}/api/v1/posts",
            payload,
            headers={
                "Authorization": f"Bearer {hublog_token}",
                # 同一天重复跑（比如手动补发）不会发两条
                "Idempotency-Key": f"llm-guard-report:{day}",
            },
            timeout=timeout,
        )
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        print(f"ERROR: 发布失败 HTTP {error.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"ERROR: 连不上 hublog（{hublog_url}）: {error}", file=sys.stderr)
        return 1

    print(f"published: {created.get('id', '?')} ({len(content)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
