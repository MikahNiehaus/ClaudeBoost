# Observability Knowledge Base

<knowledge-base name="observability" version="1.0">
<triggers>logging, metrics, tracing, monitoring, observability, alerts, telemetry, dashboard, APM</triggers>
<overview>Observability is understanding internal system state by examining outputs. Three pillars: Logs (events), Metrics (measurements), Traces (request flows). Answer: What happened? How often? Where?</overview>

<three-pillars>
  <pillar name="Logs">
    <what>Discrete events with context</what>
    <when>Debugging, audit trails, error details</when>
    <examples>Error messages, request logs, audit events</examples>
  </pillar>
  <pillar name="Metrics">
    <what>Numerical measurements over time</what>
    <when>Alerting, dashboards, capacity planning</when>
    <examples>Request count, latency percentiles, CPU usage</examples>
  </pillar>
  <pillar name="Traces">
    <what>Request flow through distributed systems</what>
    <when>Understanding dependencies, latency breakdown</when>
    <examples>API call → Service A → Database → Cache → Response</examples>
  </pillar>
</three-pillars>

<structured-logging>
  <bad-example>ERROR: Failed to process order for user john</bad-example>
  <good-example><![CDATA[{
  "level": "error",
  "message": "Failed to process order",
  "user_id": "user_123",
  "order_id": "order_456",
  "error_type": "PaymentDeclined",
  "trace_id": "abc123"
}]]></good-example>
  <log-levels>
    <level name="TRACE" usage="Very detailed debugging" example="Variable values in loops"/>
    <level name="DEBUG" usage="Development debugging" example="Function entry/exit"/>
    <level name="INFO" usage="Normal operations" example="Request completed"/>
    <level name="WARN" usage="Potential problems" example="Retry attempted"/>
    <level name="ERROR" usage="Operation failed" example="Exception caught"/>
    <level name="FATAL" usage="Cannot continue" example="Startup failure"/>
  </log-levels>
  <best-practices>
    <do>Include context (user_id, order_id, error_code)</do>
    <do>Use correlation IDs (trace_id)</do>
    <do>Log at boundaries (external API calls)</do>
    <dont>Log without context ("Something went wrong")</dont>
    <dont>Log sensitive data (passwords, API keys)</dont>
    <dont>Log in loops (will flood)</dont>
  </best-practices>
</structured-logging>

<code-level-logging-guide>
  <overview>Practical guide for agents writing code. Defines WHEN to log, WHAT to include, and at which LEVEL.</overview>

  <when-to-log>
    <category name="Always Log">
      <item level="INFO">API endpoint entry and response (method, path, status, duration)</item>
      <item level="ERROR">Caught errors and exceptions (with full context)</item>
      <item level="DEBUG/INFO">External service calls (before call at DEBUG, after at INFO with outcome)</item>
      <item level="INFO/WARN">Authentication and authorization decisions (success at INFO, failure at WARN)</item>
      <item level="INFO">Data mutations (create, update, delete with entity IDs)</item>
      <item level="INFO">Configuration changes (what changed, old vs new values — never log secrets)</item>
      <item level="INFO">Application startup and shutdown (version, config loaded, dependencies connected)</item>
      <item level="WARN">Retries and circuit breaker activations (attempt count, backoff, threshold)</item>
      <item level="INFO">Non-obvious business logic decisions (why a path was taken, with relevant IDs)</item>
    </category>
    <category name="Conditionally Log">
      <item level="DEBUG">Cache hits and misses (key, hit/miss, TTL remaining)</item>
      <item level="INFO">Scheduled job execution (job name, start, end, items processed)</item>
      <item level="DEBUG/INFO">Queue message processing (message type at DEBUG, batch summary at INFO)</item>
      <item level="DEBUG">Slow queries exceeding threshold (query, duration, threshold)</item>
      <item level="DEBUG">Feature flag evaluations (flag name, resolved value, user segment)</item>
    </category>
    <category name="Do NOT Log">
      <item>Tight loops or high-frequency iterations (will flood logs)</item>
      <item>Pure functions with no side effects</item>
      <item>Simple getters and setters</item>
      <item>Utility and helper functions (string formatting, math, etc.)</item>
      <item>Simple data classes, DTOs, or type definitions</item>
      <item>Sensitive data: passwords, tokens, API keys, PII, credit card numbers</item>
    </category>
  </when-to-log>

  <what-to-include>
    <required>
      <field name="operation">What action is being performed (e.g., "createOrder", "authenticateUser")</field>
      <field name="entity_ids">Relevant identifiers (user_id, order_id, request_id)</field>
      <field name="outcome">Success, failure, or specific result</field>
      <field name="level">Appropriate log level matching severity</field>
    </required>
    <recommended>
      <field name="duration_ms">How long the operation took</field>
      <field name="correlation_id">Trace or request ID for distributed tracing</field>
    </recommended>
    <prohibited>
      <field>Passwords or password hashes</field>
      <field>Authentication tokens, API keys, secrets</field>
      <field>PII (email, phone, SSN, address) unless explicitly required and masked</field>
      <field>Credit card numbers or financial account details</field>
      <field>Raw request/response bodies containing user data</field>
    </prohibited>
  </what-to-include>

  <log-level-decision-tree><![CDATA[
    Is the operation a failure?
    ├── YES → Can the system recover automatically?
    │   ├── YES → WARN (recoverable failure: retry, fallback, degraded mode)
    │   └── NO  → Can the application continue running?
    │       ├── YES → ERROR (operation failed, but app survives)
    │       └── NO  → FATAL (app must shut down)
    └── NO → Is this normal operational flow?
        ├── YES → INFO (business events, request completion, state changes)
        └── NO  → Is this useful only during development/debugging?
            ├── YES → DEBUG (internal state, intermediate values, flow tracing)
            └── NO  → TRACE (variable-level detail, method entry/exit in libraries)
  ]]></log-level-decision-tree>

  <anti-patterns>
    <anti-pattern name="Log-and-Forget">
      <description>Catching an exception, logging it, then swallowing it without re-throwing or handling</description>
      <bad><![CDATA[catch (error) { logger.error(error); }  // Error is silently swallowed]]></bad>
      <good><![CDATA[catch (error) { logger.error("Failed to process order", { order_id, error }); throw error; }]]></good>
    </anti-pattern>
    <anti-pattern name="No Context">
      <description>Logging a message without any identifying information</description>
      <bad><![CDATA[logger.error("Failed");  // What failed? For whom? Why?]]></bad>
      <good><![CDATA[logger.error("Failed to charge payment", { user_id, order_id, amount, error_code });]]></good>
    </anti-pattern>
    <anti-pattern name="Logging Secrets">
      <description>Including sensitive data in log output</description>
      <bad><![CDATA[logger.info("User login", { email, password, token });]]></bad>
      <good><![CDATA[logger.info("User login", { user_id, login_method: "password" });]]></good>
    </anti-pattern>
    <anti-pattern name="Log Flooding">
      <description>Logging inside tight loops or high-frequency code paths</description>
      <bad><![CDATA[for (item in items) { logger.debug("Processing item", { item }); }]]></bad>
      <good><![CDATA[logger.info("Processing batch", { count: items.length }); // Log summary, not each item]]></good>
    </anti-pattern>
  </anti-patterns>
</code-level-logging-guide>

<log-tools>
  <tool name="ELK Stack" best-for="Self-hosted, full control"/>
  <tool name="Datadog" best-for="Unified platform, integrated"/>
  <tool name="Splunk" best-for="Enterprise, compliance"/>
  <tool name="CloudWatch" best-for="AWS native"/>
  <tool name="Loki" best-for="Kubernetes, cost-effective"/>
</log-tools>

<metric-types>
  <type name="Counter" behavior="Only increases (or resets)" example="http_requests_total{method,path,status}"/>
  <type name="Gauge" behavior="Current value (up/down)" example="active_connections, memory_usage_bytes"/>
  <type name="Histogram" behavior="Distribution of values" example="http_request_duration_seconds_bucket{le}"/>
  <type name="Summary" behavior="Pre-calculated percentiles" example="http_request_duration_seconds{quantile}"/>
</metric-types>

<metric-methods>
  <method name="RED" focus="Request">
    <metric name="Rate">Requests per second</metric>
    <metric name="Errors">Failed requests per second</metric>
    <metric name="Duration">Request latency distribution</metric>
  </method>
  <method name="USE" focus="Resource">
    <metric name="Utilization">% resource in use</metric>
    <metric name="Saturation">Work queued/waiting</metric>
    <metric name="Errors">Error count</metric>
  </method>
</metric-methods>

<essential-metrics>
  <category name="Request">http_requests_total, http_request_duration_seconds, http_request_size_bytes</category>
  <category name="Business">orders_processed_total, revenue_dollars_total, user_signups_total</category>
  <category name="System">process_cpu_seconds_total, process_memory_bytes, process_open_fds</category>
</essential-metrics>

<metric-tools>
  <tool name="Prometheus" type="Pull-based TSDB" best-for="Kubernetes, microservices"/>
  <tool name="Datadog" type="Push-based SaaS" best-for="Full stack monitoring"/>
  <tool name="CloudWatch" type="AWS native" best-for="AWS services"/>
  <tool name="InfluxDB" type="Push-based TSDB" best-for="IoT, high-cardinality"/>
  <tool name="Grafana" type="Visualization" best-for="Dashboards"/>
</metric-tools>

<distributed-tracing>
  <concepts>
    <concept name="Trace">Full journey of request through system</concept>
    <concept name="Span">Single operation within a trace</concept>
    <concept name="Context Propagation">Passing trace IDs across services</concept>
  </concepts>
  <span-anatomy><![CDATA[{
  "trace_id": "abc123",
  "span_id": "span456",
  "parent_span_id": "span123",
  "operation_name": "database.query",
  "duration_ms": 45,
  "attributes": {"db.system": "postgresql"}
}]]></span-anatomy>
</distributed-tracing>

<tracing-tools>
  <tool name="Jaeger" type="Open source" best-for="Self-hosted, Kubernetes"/>
  <tool name="Zipkin" type="Open source" best-for="Simpler setup"/>
  <tool name="Datadog APM" type="SaaS" best-for="Full platform integration"/>
  <tool name="AWS X-Ray" type="AWS native" best-for="AWS services"/>
  <tool name="Honeycomb" type="SaaS" best-for="High-cardinality analysis"/>
</tracing-tools>

<alerting>
  <principles>
    <principle>Alert on symptoms, not causes (API latency not DB CPU)</principle>
    <principle>Include runbook links in annotations</principle>
  </principles>
  <severity-levels>
    <level name="Critical" response="Wake someone up" examples="Service down, data loss"/>
    <level name="Warning" response="Investigate soon" examples="Degraded performance"/>
    <level name="Info" response="Business hours" examples="Unusual pattern"/>
  </severity-levels>
  <avoid-fatigue>
    <strategy>Set realistic thresholds</strategy>
    <strategy>Group related alerts</strategy>
    <strategy>Require sustained condition</strategy>
    <strategy>Have clear ownership</strategy>
    <strategy>Regularly review and tune</strategy>
  </avoid-fatigue>
</alerting>

<dashboard-design>
  <types>
    <type name="Executive" content="Business KPIs, health summary, trends"/>
    <type name="Service Health" content="RED metrics, utilization, dependencies"/>
    <type name="Debugging" content="Detailed metrics, logs, traces"/>
  </types>
  <best-practices>
    <layout>Most important at top-left, group related, consistent time ranges</layout>
    <visualization>Appropriate charts, show thresholds, avoid 3D, consistent colors</visualization>
    <interactivity>Drill-down links, trace/log links, time adjustment, filtering</interactivity>
  </best-practices>
</dashboard-design>

<slos-slis>
  <definitions>
    <term name="SLI">Service Level Indicator - measurement of behavior</term>
    <term name="SLO">Service Level Objective - target for SLI</term>
    <term name="SLA">Service Level Agreement - contract with consequences</term>
  </definitions>
  <common-slis>
    <sli name="Availability" calc="Successful/Total requests" good-slo="99.9%"/>
    <sli name="Latency" calc="% requests &lt; threshold" good-slo="95% &lt; 200ms"/>
    <sli name="Error Rate" calc="Errors/Total requests" good-slo="&lt; 0.1%"/>
    <sli name="Throughput" calc="Requests per second" good-slo="> 1000 RPS"/>
  </common-slis>
  <error-budget>If SLO = 99.9%: Budget = 0.1% = 43.2 minutes/month downtime</error-budget>
</slos-slis>

<implementation-checklist>
  <category name="Logging">
    <item>Structured JSON logging configured</item>
    <item>Appropriate log levels defined</item>
    <item>Correlation IDs propagated</item>
    <item>Sensitive data excluded</item>
    <item>Log aggregation configured</item>
  </category>
  <category name="Metrics">
    <item>Key business metrics defined</item>
    <item>RED metrics for services</item>
    <item>USE metrics for resources</item>
    <item>Grafana dashboards created</item>
  </category>
  <category name="Tracing">
    <item>OpenTelemetry instrumented</item>
    <item>Context propagation working</item>
    <item>Sampling strategy defined</item>
  </category>
  <category name="Alerting">
    <item>Critical alerts defined</item>
    <item>Runbooks linked</item>
    <item>On-call rotation set</item>
  </category>
</implementation-checklist>

</knowledge-base>
