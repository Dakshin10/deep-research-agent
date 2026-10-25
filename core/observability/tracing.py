from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from langfuse import Langfuse, observe
    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False


class TraceEvent(BaseModel):
    name: str
    trace_type: str  # "agent", "tool", "gate"
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    status: str = "success"
    error: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class LangfuseTracer:
    """
    Central observability manager using Langfuse SDK.
    Captures traces, spans, latency, and tokens around agents and tool calls.
    Falls back gracefully when Langfuse service is unreachable or keys are mock.
    """

    def __init__(self):
        self.public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        self.host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
        self.client = None
        self._trace_history: List[TraceEvent] = []

        if _LANGFUSE_AVAILABLE and self.public_key and self.secret_key and not self.public_key.startswith("pk-lf-mock"):
            try:
                self.client = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                )
            except Exception:
                self.client = None

    def record_trace(
        self,
        name: str,
        trace_type: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        duration: float,
        status: str = "success",
        error: Optional[str] = None,
    ) -> TraceEvent:
        event = TraceEvent(
            name=name,
            trace_type=trace_type,
            inputs={k: str(v)[:500] for k, v in inputs.items()},
            outputs={k: str(v)[:500] for k, v in outputs.items()},
            duration_seconds=duration,
            status=status,
            error=error,
        )
        self._trace_history.append(event)

        # Send to Langfuse if client is live
        if self.client:
            try:
                self.client.trace(
                    name=name,
                    metadata={"type": trace_type, "status": status, "duration": duration},
                    input=inputs,
                    output=outputs,
                )
            except Exception:
                pass

        return event

    def get_traces(self) -> List[TraceEvent]:
        return list(self._trace_history)

    def clear(self) -> None:
        self._trace_history.clear()


_GLOBAL_TRACER: Optional[LangfuseTracer] = None


def get_tracer() -> LangfuseTracer:
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is None:
        _GLOBAL_TRACER = LangfuseTracer()
    return _GLOBAL_TRACER


def trace_agent(agent_name: str) -> Callable:
    """Decorator to trace agent execution with Langfuse telemetry."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            start = time.time()
            inputs = {"args": [str(a)[:200] for a in args[1:]], "kwargs": {k: str(v)[:200] for k, v in kwargs.items()}}
            try:
                res = await func(*args, **kwargs)
                duration = time.time() - start
                out_summary = {"result": str(res)[:300]} if res is not None else {}
                tracer.record_trace(
                    name=agent_name,
                    trace_type="agent",
                    inputs=inputs,
                    outputs=out_summary,
                    duration=duration,
                    status="success",
                )
                return res
            except BaseException as e:
                if type(e).__name__ == "GraphInterrupt":
                    raise
                duration = time.time() - start
                tracer.record_trace(
                    name=agent_name,
                    trace_type="agent",
                    inputs=inputs,
                    outputs={},
                    duration=duration,
                    status="error",
                    error=str(e),
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            start = time.time()
            inputs = {"args": [str(a)[:200] for a in args[1:]], "kwargs": {k: str(v)[:200] for k, v in kwargs.items()}}
            try:
                res = func(*args, **kwargs)
                duration = time.time() - start
                out_summary = {"result": str(res)[:300]} if res is not None else {}
                tracer.record_trace(
                    name=agent_name,
                    trace_type="agent",
                    inputs=inputs,
                    outputs=out_summary,
                    duration=duration,
                    status="success",
                )
                return res
            except Exception as e:
                duration = time.time() - start
                tracer.record_trace(
                    name=agent_name,
                    trace_type="agent",
                    inputs=inputs,
                    outputs={},
                    duration=duration,
                    status="error",
                    error=str(e),
                )
                raise

        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_tool(tool_name: str) -> Callable:
    """Decorator to trace tool execution with Langfuse telemetry."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            start = time.time()
            inputs = {"args": [str(a)[:200] for a in args[1:]], "kwargs": {k: str(v)[:200] for k, v in kwargs.items()}}
            try:
                res = await func(*args, **kwargs)
                duration = time.time() - start
                tracer.record_trace(
                    name=tool_name,
                    trace_type="tool",
                    inputs=inputs,
                    outputs={"result_type": type(res).__name__, "length": len(res) if hasattr(res, "__len__") else 1},
                    duration=duration,
                    status="success",
                )
                return res
            except Exception as e:
                duration = time.time() - start
                tracer.record_trace(
                    name=tool_name,
                    trace_type="tool",
                    inputs=inputs,
                    outputs={},
                    duration=duration,
                    status="error",
                    error=str(e),
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            start = time.time()
            inputs = {"args": [str(a)[:200] for a in args[1:]], "kwargs": {k: str(v)[:200] for k, v in kwargs.items()}}
            try:
                res = func(*args, **kwargs)
                duration = time.time() - start
                tracer.record_trace(
                    name=tool_name,
                    trace_type="tool",
                    inputs=inputs,
                    outputs={"result_type": type(res).__name__, "length": len(res) if hasattr(res, "__len__") else 1},
                    duration=duration,
                    status="success",
                )
                return res
            except Exception as e:
                duration = time.time() - start
                tracer.record_trace(
                    name=tool_name,
                    trace_type="tool",
                    inputs=inputs,
                    outputs={},
                    duration=duration,
                    status="error",
                    error=str(e),
                )
                raise

        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def asyncio_iscoroutinefunction(func: Any) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(func)


def record_shard_span(
    shard_id: str,
    task_id: str,
    query: str,
    duration: float,
    notes_count: int,
    error: Optional[str] = None,
) -> TraceEvent:
    """Records a Langfuse span specifically for a parallel research shard with latency and notes count."""
    tracer = get_tracer()
    return tracer.record_trace(
        name=f"shard_{shard_id}",
        trace_type="shard",
        inputs={"shard_id": shard_id, "task_id": task_id, "query": query},
        outputs={"notes_count": notes_count},
        duration=duration,
        status="error" if error else "success",
        error=error,
    )


def record_provider_span(
    provider: str,
    query: str,
    duration: float,
    hits_count: int,
    error: Optional[str] = None,
) -> TraceEvent:
    """Records a Langfuse span specifically for a search provider query with latency and error metrics."""
    tracer = get_tracer()
    return tracer.record_trace(
        name=f"provider_{provider}",
        trace_type="provider",
        inputs={"provider": provider, "query": query},
        outputs={"hits_count": hits_count},
        duration=duration,
        status="error" if error else "success",
        error=error,
    )


def record_crawl_span(
    source: str,
    run_id: str,
    pages_crawled: int,
    duration: float,
    error: Optional[str] = None,
) -> TraceEvent:
    """Records a Langfuse span for a crawler run tracking pages and rate."""
    tracer = get_tracer()
    pages_per_sec = round(pages_crawled / max(0.01, duration), 2)
    return tracer.record_trace(
        name=f"crawl_{source}",
        trace_type="crawl",
        inputs={"source": source, "run_id": run_id},
        outputs={"pages_crawled": pages_crawled, "pages_per_sec": pages_per_sec},
        duration=duration,
        status="error" if error else "success",
        error=error,
    )


def record_extraction_batch_span(
    source: str,
    batch_size: int,
    ideas_extracted: int,
    duration: float,
    estimated_cost_usd: Optional[float] = None,
    error: Optional[str] = None,
) -> TraceEvent:
    """
    Records a Langfuse span for an idea extraction batch, tracking throughput
    and estimated model cost per 1,000 pages (defaulting to ~$0.15 / 1k pages).
    """
    tracer = get_tracer()
    cost = estimated_cost_usd if estimated_cost_usd is not None else round((batch_size / 1000.0) * 0.15, 4)
    cost_per_1k = round((cost / max(1, batch_size)) * 1000.0, 4)
    return tracer.record_trace(
        name=f"extract_{source}",
        trace_type="extraction",
        inputs={"source": source, "batch_size": batch_size},
        outputs={
            "ideas_extracted": ideas_extracted,
            "cost_usd": cost,
            "cost_per_1000_pages_usd": cost_per_1k,
        },
        duration=duration,
        status="error" if error else "success",
        error=error,
    )

