from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "novelforge.db"
DEFAULT_API = "http://127.0.0.1:8000"

REQUIRED_MIN_COUNTS = {
    "prompt_templates": 1,
    "agent_roles": 1,
    "reader_agent_profiles": 1,
    "model_providers": 1,
}


def fetch_json(url: str, timeout: int = 8) -> tuple[bool, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return False, str(exc)


def scalar(cur: sqlite3.Cursor, sql: str) -> Any:
    return cur.execute(sql).fetchone()[0]


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    row = cur.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
    return row is not None


def data_counts(cur: sqlite3.Cursor) -> dict[str, int | str]:
    tables = [
        "prompt_templates",
        "prompt_versions",
        "agent_roles",
        "agent_model_bindings",
        "agent_prompt_bindings",
        "reader_agent_profiles",
        "model_providers",
        "model_role_assignments",
        "projects",
        "chapters",
    ]
    counts: dict[str, int | str] = {}
    for table in tables:
        counts[table] = int(scalar(cur, f"select count(*) from {table}")) if table_exists(cur, table) else "MISSING"
    return counts


def task_snapshot(cur: sqlite3.Cursor) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    if table_exists(cur, "agent_tasks"):
        snapshot["agent_tasks_by_status"] = [
            dict(row)
            for row in cur.execute(
                """
                select task_type, domain, status, count(*) as count, max(updated_at) as latest
                from agent_tasks
                group by task_type, domain, status
                order by latest desc
                """
            ).fetchall()
        ]
        snapshot["active_or_failed_tasks"] = [
            dict(row)
            for row in cur.execute(
                """
                select id, task_type, domain, status, error, retry_count,
                       lease_owner, lease_expires_at, last_heartbeat_at, updated_at
                from agent_tasks
                where status in ('running', 'pending', 'queued', 'failed')
                order by id desc
                limit 20
                """
            ).fetchall()
        ]
    if table_exists(cur, "deepstudy_runs"):
        snapshot["deepstudy_runs"] = [
            dict(row)
            for row in cur.execute(
                """
                select id, project_id, status, current_stage, processed_chapters,
                       total_chapters, error, updated_at
                from deepstudy_runs
                order by id desc
                limit 10
                """
            ).fetchall()
        ]
    return snapshot


def api_snapshot(api_base: str) -> dict[str, Any]:
    urls = {
        "health": f"{api_base}/health",
        "worker_status": f"{api_base}/api/worker/status",
        "worker_multi_status": f"{api_base}/api/worker/multi-status",
        "prompts": f"{api_base}/api/prompts",
        "agent_roles": f"{api_base}/api/agent-roles",
        "reader_agents": f"{api_base}/api/reviews/readers",
    }
    out: dict[str, Any] = {}
    for key, url in urls.items():
        ok, payload = fetch_json(url)
        if not ok:
            out[key] = {"ok": False, "error": payload}
            continue
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, list):
            out[key] = {"ok": True, "count": len(data)}
        elif isinstance(data, dict):
            compact = {k: data.get(k) for k in ["state", "loop_state", "current_task_id", "last_error", "stale_running_tasks"] if k in data}
            out[key] = {"ok": True, **compact}
        else:
            out[key] = {"ok": True, "value": data}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="检查后端、worker、拆书、写作、模板和 Agent 基线。")
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    result: dict[str, Any] = {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "api_base": args.api,
        "ok": True,
        "issues": [],
    }

    if not DB_PATH.exists():
        result["ok"] = False
        result["issues"].append("数据库文件不存在")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        counts = data_counts(cur)
        result["counts"] = counts
        for table, minimum in REQUIRED_MIN_COUNTS.items():
            value = counts.get(table)
            if not isinstance(value, int) or value < minimum:
                result["ok"] = False
                result["issues"].append(f"{table} 数量异常：{value}")
        result["tasks"] = task_snapshot(cur)
    finally:
        conn.close()

    result["api"] = api_snapshot(args.api)
    worker = result["api"].get("worker_status", {})
    if worker.get("ok") and worker.get("loop_state") != "alive":
        result["ok"] = False
        result["issues"].append(f"worker 未存活：{worker.get('loop_state')}")
    elif not worker.get("ok"):
        result["ok"] = False
        result["issues"].append("worker 状态接口不可用")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
