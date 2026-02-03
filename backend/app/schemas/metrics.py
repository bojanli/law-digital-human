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


class PaperKpiLatency(BaseModel):
    sample_size: int
    p50_ms: float
    p90_ms: float
    avg_ms: float


class PaperKpiResponse(BaseModel):
    days: int | None = None
    chat_total: int
    chat_with_evidence: int
    citation_hit_rate: float
    chat_no_evidence: int
    no_evidence_reject_rate: float
    chat_latency: PaperKpiLatency
    case_step_latency: PaperKpiLatency
