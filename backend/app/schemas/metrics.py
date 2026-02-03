from pydantic import BaseModel


class MetricsEndpointSummary(BaseModel):
    endpoint: str
    total: int
    ok: int
    fail: int
    ok_rate: float
    avg_latency_ms: float


class MetricsSummaryResponse(BaseModel):
    total: int
    ok: int
    fail: int
    ok_rate: float
    avg_latency_ms: float
    by_endpoint: list[MetricsEndpointSummary]
