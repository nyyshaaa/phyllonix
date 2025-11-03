

from prometheus_fastapi_instrumentator import Instrumentator,metrics

instrumentator = Instrumentator(
    should_ignore_untemplated=True,      # /foo/123 → /foo/{id}
    excluded_handlers=["/metrics"],      # exclude metrics endpoint from instrumentation
    should_instrument_requests_inprogress=True,                   # ← opt‑in for “requests in progress” gauge
    should_group_status_codes=False,
    # latency_buckets=[0.005,0.01,0.025,0.05,0.1,0.2,0.5,1,2,5]
)
