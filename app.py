#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SarcasmMaster · Web API
=======================

用 Flask 把已有的 LangChain Agent 包装成 HTTP API，并托管一个静态前端页面。

设计原则：**只做包装，不重写逻辑。**
    - Agent / Prompt / Tools / RAG 全部直接复用 main.py 里已经构建好的 `agent` 对象。
    - 本文件不重新实现任何模型调用、检索或提示词逻辑。

接口一览
--------
    GET  /                    前端页面
    GET  /api/health          健康检查（模型、向量库状态）
    POST /api/sarcasm         同步生成，一次性返回 JSON
    POST /api/sarcasm/stream  流式生成，Server-Sent Events（前端使用这个）

运行
----
    python app.py
    浏览器打开 http://127.0.0.1:5000

    可用环境变量覆盖：HOST / PORT / FLASK_DEBUG
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterator, List, Tuple

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

# --- 复用原有项目：main.py 里的 agent 就是唯一的 Agent 实例 -------------
# main.py 现在把 CLI 部分放在 `if __name__ == "__main__":` 里，
# 所以这里 import 不会触发 input()，只会构建一次 Agent。
from main import agent  # noqa: E402
import rag  # noqa: E402  同一个模块实例（tools 已经导入过），用于健康检查
from langchain.messages import AIMessage, ToolMessage  # noqa: E402


# ======================================================================
# 配置
# ======================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")

MAX_INPUT_CHARS = 2000
PREVIEW_CHARS = 200

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
app.json.ensure_ascii = False          # 让 JSON 里直接显示中文
CORS(app)                              # 允许别人从其它页面调用这个 API


# 工具名 -> 给用户看的中文说明
TOOL_LABELS = {
    "retrieve_sarcasm_patterns": "检索语料库中的阴阳怪气范例",
    "transform_to_sarcasm": "遣词造句，生成阴阳怪气版本",
    "gather_sarcasm_feedback": "评估这句阴阳怪气的杀伤力",
}


# ======================================================================
# 小工具
# ======================================================================

def content_text(content: Any) -> str:
    """取出消息里的纯文本。

    LangChain 1.x 里 `AIMessage.content` 可能是 str，也可能是
    `[{'type': 'text', 'text': '...'}, ...]` 这种 content blocks 列表，
    这里统一抽成字符串。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return str(content)


def clip(text: Any, limit: int = PREVIEW_CHARS) -> str:
    """压缩空白并截断，用于给前端展示工具参数 / 返回值预览。"""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit] + "…"


def args_preview(tool_name: str, args: Dict[str, Any]) -> str:
    """挑出工具参数里最有信息量的那个字段做预览。"""
    for key in ("question", "original", "sentences", "context"):
        if args.get(key):
            return clip(args[key])
    return clip(json.dumps(args, ensure_ascii=False)) if args else ""


def agent_events(text: str) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """跑一次 Agent，产出 (事件名, 数据) 二元组。

    事件名与前端 static/app.js 里的 handleEvent() 一一对应：
        status / tool / tool_result / final / error

    这里沿用了 main.py 完全一样的调用方式：
        agent.stream_events({"messages": {...}}, version="v3")  然后遍历 .values
    """
    t0 = time.time()
    yield "status", {"message": "正在理解你的句子…"}

    final_text = ""
    seen: set = set()

    try:
        stream = agent.stream_events(
            {"messages": {"role": "user", "content": text}},
            version="v3",
        )

        # 每个 snapshot 是 AgentState（含完整 messages 列表），
        # 我们只关心「最新多出来的那一条消息」。
        for snapshot in stream.values:
            messages = (snapshot or {}).get("messages") or []
            if not messages:
                continue

            latest = messages[-1]
            msg_id = getattr(latest, "id", None) or id(latest)
            if msg_id in seen:
                continue
            seen.add(msg_id)

            tool_calls = getattr(latest, "tool_calls", None) or []

            if tool_calls:
                # Agent 决定调用工具
                for call in tool_calls:
                    name = call.get("name", "tool")
                    args = call.get("args") or {}
                    yield "tool", {
                        "name": name,
                        "label": TOOL_LABELS.get(name, name),
                        "args": args,
                        "preview": args_preview(name, args),
                    }
            elif isinstance(latest, ToolMessage):
                # 工具执行完毕，把结果回传
                yield "tool_result", {
                    "name": getattr(latest, "name", None) or "tool",
                    "preview": clip(content_text(latest.content)),
                }
            elif isinstance(latest, AIMessage):
                # 没有工具调用 => 这是最终答案
                answer = content_text(latest.content).strip()
                if answer:
                    final_text = answer

        # 兜底：万一上面的循环没抓到文本，直接看最终 state
        if not final_text:
            output = stream.output or {}
            out_msgs = output.get("messages") or []
            if out_msgs:
                final_text = content_text(
                    getattr(out_msgs[-1], "content", "")
                ).strip()

        if final_text:
            yield "final", {
                "text": final_text,
                "elapsed": round(time.time() - t0, 1),
            }
        else:
            yield "error", {"message": "模型没有返回任何内容，请重试。"}

    except Exception as exc:  # noqa: BLE001  —— 任何异常都转成前端可读的错误
        app.logger.exception("Agent 执行失败")
        yield "error", {"message": f"{type(exc).__name__}: {exc}"}


# ======================================================================
# 路由
# ======================================================================

@app.get("/")
def index():
    """返回前端页面。"""
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/health")
def health():
    """健康检查：模型名 + 向量库条数。"""
    try:
        count = rag.vector_store._collection.count()
        ready = count > 0
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("向量库检查失败: %s", exc)
        count, ready = 0, False

    return jsonify({
        "status": "ok",
        "llm_model": os.getenv("LLM_MODEL") or os.getenv("llm_model"),
        "embedding_model": os.getenv("EMBEDDING_MODEL") or os.getenv("embedding_model"),
        "vector_store_ready": ready,
        "vector_store_count": count,
    })


def read_text_input() -> str:
    """从 JSON body 里取用户输入，顺便做长度校验。"""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or data.get("sentence") or "").strip()

    if not text:
        raise ValueError("缺少字段 text。")
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(f"输入太长了（最多 {MAX_INPUT_CHARS} 字）。")
    return text


@app.post("/api/sarcasm")
def sarcasm():
    """同步接口：等 Agent 跑完，一次性返回结果。

    请求体: {"text": "今天天气真好"}
    响应体: {"sarcastic": "...", "elapsed": 57.7, "trace": [...]}
    """
    try:
        text = read_text_input()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    trace: List[Dict[str, Any]] = []
    answer = ""
    error = None

    for name, payload in agent_events(text):
        if name == "final":
            answer = payload["text"]
        elif name == "error":
            error = payload["message"]
        elif name in ("tool", "tool_result", "status"):
            trace.append({"event": name, **payload})

    if error and not answer:
        return jsonify({"error": error, "trace": trace}), 500

    return jsonify({"sarcastic": answer, "trace": trace})


@app.post("/api/sarcasm/stream")
def sarcasm_stream():
    """流式接口：Server-Sent Events。

    请求体: {"text": "今天天气真好"}
    返回一堆 SSE 事件：status / tool / tool_result / final / error / done
    """
    try:
        text = read_text_input()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    def generate() -> Iterator[str]:
        for name, payload in agent_events(text):
            body = json.dumps(payload, ensure_ascii=False)
            yield f"event: {name}\ndata: {body}\n\n"
        yield "event: done\ndata: {}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # 反向代理下也保持不缓冲
        },
    )


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "请求体过大。"}), 413


# ======================================================================
# 启动
# ======================================================================

if __name__ == "__main__":
    print()
    print("  SarcasmMaster API")
    print("  -----------------")
    print(f"  LLM 模型    : {os.getenv('LLM_MODEL') or os.getenv('llm_model')}")
    print(f"  前端页面    : http://127.0.0.1:{PORT}/")
    print(f"  API (同步)  : POST http://127.0.0.1:{PORT}/api/sarcasm")
    print(f"  API (流式)  : POST http://127.0.0.1:{PORT}/api/sarcasm/stream")
    print()
    print("  提示：第一次生成大约要 30~60 秒（qwen3:8b 本地推理比较慢），")
    print("        前端会实时显示 Agent 的工具调用过程。按 Ctrl+C 停止。")
    print()

    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True, use_reloader=False)
