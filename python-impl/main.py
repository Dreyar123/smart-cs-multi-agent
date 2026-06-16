"""
FastAPI入口 — 提供REST API + SSE流式响应
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.supervisor import create_supervisor_graph
from memory.working_memory import WorkingMemory
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from mcp.mcp_server import MCPToolServer, create_default_tools
from tracing.otel_config import init_tracer, AgentMetrics

import asyncio
from opentelemetry import trace

load_dotenv()

import sys
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# # 在代码最上方（定义完 import 之后）立即执行以下三行，用真正的 Provider 替换掉 Proxy
# provider = TracerProvider()
# processor = BatchSpanProcessor(ConsoleSpanExporter())  # 也可以改用 SimpleSpanProcessor
# provider.add_span_processor(processor)
# trace.set_tracer_provider(provider)
#
# # 获取属于你当前模块的追踪器
# tracer = trace.get_tracer(__name__)


working_memory = WorkingMemory()
short_term_memory = ShortTermMemory(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
long_term_memory = LongTermMemory(index_path=os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index"))
mcp_server = create_default_tools(MCPToolServer())
metrics = AgentMetrics()
graph = None

def callFunc(user_input: str):
    from langchain_core.messages import HumanMessage

    asyncio.run(short_term_memory.add_message("1", "user", user_input))

    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "user_id": "0",
        "session_id": "1",
        "intent": "",
        "sub_results": {},
        "compliance_passed": True,
        "final_response": "",
        "current_agent": "",
        "retry_count": 0,
    }

    current_round_state = {
        "messages": [HumanMessage(content=user_input)]
    }

    config = {"configurable": {"thread_id": "1"}}

    try:
        result = asyncio.run(graph.ainvoke(current_round_state, config=config))
    except Exception as e:
        raise HTTPException(status_code=50, detail=f"处理失败: {str(e)}")
    final_response = result.get("final_response", "系统处理异常，请稍后重试")

    asyncio.run(short_term_memory.add_message("1", "assistant", final_response))

    return final_response

if __name__ == "__main__":
    graph = create_supervisor_graph(
        working_memory=working_memory,
        short_term_memory=short_term_memory,
        long_term_memory=long_term_memory,
    )

    long_term_memory.add_document(
        content="我们的理财产品A年化收益率为3.5%-5.2%，投资期限为6个月至3年，最低投资金额10000元。注意：理财非存款，产品有风险，投资须谨慎。",
        source="product_faq.md",
    )
    long_term_memory.add_document(
        content="退款政策：用户在购买后7天内可申请无理由退款，超过7天需提供合理原因。退款将在3-5个工作日内原路退回。",
        source="refund_policy.md",
    )
    long_term_memory.add_document(
        content="开户流程：1.准备身份证原件 2.填写开户申请表 3.进行视频认证 4.设置交易密码 5.完成风险评估问卷。整个流程约需15-30分钟。",
        source="account_guide.md",
    )


    while True:
        # 接收用户输入
        user_input = input("用户: ")

        # 设置退出条件
        if user_input.strip().lower() in ['exit', 'quit']:
            print("🤖 再见！")
            break

        # 如果输入为空则跳过
        if not user_input.strip():
            continue


        print(callFunc(user_input))
    # # ==================== 【第二步：安全冲刷】 ====================
    # # 此时 get_tracer_provider() 获取到的是上面第 8 行创建的真正的 TracerProvider 了
    # print("正在强制冲刷性能日志到控制台...")
    # # trace.get_tracer_provider().force_flush()
    # # print("冲刷完成，程序安全退出。")
    # print("end")


