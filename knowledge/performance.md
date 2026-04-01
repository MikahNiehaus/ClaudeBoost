# Performance Optimization Knowledge Base

<knowledge-base name="performance" version="1.0">
<triggers>performance, profiling, benchmark, optimization, bottleneck, latency, throughput, slow, memory leak, load test</triggers>
<overview>Measure, identify, optimize, verify. Finding and fixing performance problems across languages and platforms.</overview>

<core-principles>
  <principle>Measure before optimizing - never guess at performance problems</principle>
  <principle>Profile in production-like conditions with realistic data and load</principle>
  <principle>Focus on hot paths - 80% of time is in 20% of code</principle>
  <principle>Optimize the right metric: latency vs throughput vs resource usage</principle>
  <principle>Verify improvements - measure after every change</principle>
  <principle>Consider trade-offs: speed vs memory vs complexity vs maintainability</principle>
</core-principles>

<latency-metrics>
  <metric name="p50 (median)" meaning="Half of requests faster" target="User-facing: &lt; 100ms"/>
  <metric name="p90" meaning="90% of requests faster" target="User-facing: &lt; 200ms"/>
  <metric name="p99" meaning="99% of requests faster" target="User-facing: &lt; 500ms"/>
  <metric name="p99.9" meaning="99.9% of requests faster" target="Critical paths: &lt; 1s"/>
  <metric name="Average" meaning="Mean response time" warning="Misleading - don't optimize for this"/>
</latency-metrics>

<resource-thresholds>
  <resource name="CPU" warning="&gt; 70% sustained" critical="&gt; 90%"/>
  <resource name="Memory" warning="&gt; 80%" critical="&gt; 95%"/>
  <resource name="Disk I/O" warning="&gt; 80% utilization" critical="&gt; 95%"/>
  <resource name="Network" warning="&gt; 70% bandwidth" critical="&gt; 90%"/>
  <resource name="DB Connections" warning="&gt; 80% pool" critical="&gt; 95%"/>
</resource-thresholds>

<profiling-tools>
  <language name="Python">
    <tool type="CPU">cProfile, py-spy, line_profiler</tool>
    <tool type="Memory">memory_profiler, tracemalloc, objgraph</tool>
    <tool type="Async">yappi (supports asyncio/threading)</tool>
  </language>
  <language name="JavaScript/Node.js">
    <tool type="CPU">--inspect + Chrome DevTools, clinic.js, 0x</tool>
    <tool type="Memory">heap snapshots, memwatch-next, heapdump</tool>
    <tool type="Production">--prof for V8 profiling</tool>
  </language>
  <language name="Java">
    <tool type="CPU">async-profiler, JFR (Java Flight Recorder), VisualVM</tool>
    <tool type="Memory">jmap, MAT (Memory Analyzer Tool)</tool>
    <tool type="GC">-Xlog:gc*, GCViewer</tool>
  </language>
  <language name="Go">
    <tool type="CPU">pprof, go test -bench -cpuprofile</tool>
    <tool type="Memory">pprof heap profiles, runtime.ReadMemStats()</tool>
    <tool type="Tracing">go tool trace</tool>
  </language>
</profiling-tools>

<bottleneck-types>
  <type name="CPU-Bound">
    <symptoms>High CPU (&gt;80%), latency scales with complexity, more cores help</symptoms>
    <causes>Inefficient algorithms, string concatenation, regex in hot paths, JSON parsing in loops</causes>
    <solutions>Improve algorithm complexity, cache computed results, parallelize</solutions>
  </type>
  <type name="Memory-Bound">
    <symptoms>High memory usage, GC pauses, OOM errors under load</symptoms>
    <causes>Memory leaks, large object graphs, excessive allocations, unbounded caches</causes>
    <solutions>Object pooling, streaming, bounded caches with eviction, fix leaks</solutions>
  </type>
  <type name="I/O-Bound">
    <symptoms>High disk/network utilization, CPU relatively idle</symptoms>
    <causes>Synchronous I/O, many small operations, missing connection pooling</causes>
    <solutions>Async I/O, batching requests, connection pooling, caching, compression</solutions>
  </type>
  <type name="Database-Bound">
    <symptoms>Slow queries, high database CPU/I/O, lock contention</symptoms>
    <causes>Missing indexes, N+1 queries, full table scans, lock contention</causes>
    <solutions>Add indexes, eager loading/JOINs, query caching, read replicas, batching</solutions>
  </type>
</bottleneck-types>

<caching-strategies>
  <levels>
    <level name="L1">Application memory (fastest, limited size)</level>
    <level name="L2">Local cache (Redis/Memcached on same machine)</level>
    <level name="L3">Distributed cache (shared Redis cluster)</level>
    <level name="L4">CDN (for static/semi-static content)</level>
  </levels>
  <patterns>
    <pattern name="Cache-Aside (Lazy Loading)">Check cache → miss → load from source → store → return</pattern>
    <pattern name="Write-Through">Write to cache AND source together, read from cache</pattern>
    <pattern name="Write-Behind">Write to cache immediately, async write to source</pattern>
  </patterns>
  <invalidation>
    <strategy name="Time-based (TTL)">Simple but may serve stale data</strategy>
    <strategy name="Event-based">Complex but always fresh</strategy>
    <strategy name="Version-based">Add version to cache key</strategy>
  </invalidation>
  <sizing>
    <guideline>Hit Rate Target: &gt; 90% for most caches</guideline>
    <guideline>Eviction Policy: LRU for general use, LFU for skewed access</guideline>
  </sizing>
</caching-strategies>

<load-testing>
  <test-types>
    <type name="Smoke" purpose="Verify system works" duration="Minutes"/>
    <type name="Load" purpose="Normal expected traffic" duration="30-60 min"/>
    <type name="Stress" purpose="Find breaking point" duration="Until failure"/>
    <type name="Soak" purpose="Find memory leaks" duration="Hours/days"/>
    <type name="Spike" purpose="Handle sudden traffic" duration="Burst patterns"/>
  </test-types>
  <tools>
    <tool type="HTTP">k6, Apache JMeter, wrk, Locust, Artillery</tool>
    <tool type="Database">pgbench (PostgreSQL), mysqlslap (MySQL), sysbench</tool>
  </tools>
  <design-guidelines>
    <guideline>Define scenarios (user journeys, not just endpoints)</guideline>
    <guideline>Set realistic think times between requests</guideline>
    <guideline>Use production-like data volumes</guideline>
    <guideline>Ramp up gradually (don't spike immediately)</guideline>
    <guideline>Monitor all components (app, DB, cache, network)</guideline>
    <guideline>Run long enough to see patterns (30+ minutes)</guideline>
  </design-guidelines>
</load-testing>

<database-optimization>
  <index-strategy>
    <create-for>WHERE clause columns, JOIN columns, ORDER BY columns, high selectivity columns</create-for>
    <avoid-for>Small tables, frequently updated columns, low cardinality (boolean, status)</avoid-for>
  </index-strategy>
  <connection-pooling>
    <formula>connections = (core_count * 2) + spindle_count</formula>
    <example>8 cores, SSD: (8 * 2) + 1 = 17 connections</example>
    <note>Start conservative, increase based on monitoring</note>
  </connection-pooling>
  <query-checklist>
    <item>EXPLAIN/EXPLAIN ANALYZE the query</item>
    <item>Check for full table scans</item>
    <item>Verify indexes are being used</item>
    <item>Look for implicit type conversions</item>
    <item>Check for N+1 patterns</item>
    <item>Consider query caching</item>
  </query-checklist>
</database-optimization>

<concurrency-optimization>
  <thread-pool-sizing>
    <rule type="CPU-bound">threads = number_of_cores</rule>
    <rule type="I/O-bound">threads = cores * (1 + wait_time/compute_time)</rule>
    <example>8 cores, 100ms wait, 10ms compute: 8 * (1 + 100/10) = 88 threads</example>
  </thread-pool-sizing>
  <lock-optimization>
    <strategy>Reduce lock scope (hold briefly)</strategy>
    <strategy>Use read-write locks for read-heavy workloads</strategy>
    <strategy>Lock striping (multiple locks for different data segments)</strategy>
    <strategy>Lock-free data structures where possible</strategy>
    <strategy>Avoid nested locks (deadlock risk)</strategy>
  </lock-optimization>
</concurrency-optimization>

<anti-patterns>
  <anti-pattern name="Premature Optimization">Optimizing without profiling data, micro-optimizing rarely-executed code</anti-pattern>
  <anti-pattern name="Over-Caching">Caching everything "just in case", unbounded cache growth</anti-pattern>
  <anti-pattern name="Incorrect Parallelization">Parallelizing CPU-bound work beyond core count, thread per request</anti-pattern>
  <anti-pattern name="Ignoring Tail Latency">Only measuring averages, not monitoring p99/p99.9</anti-pattern>
</anti-patterns>

<optimization-checklist>
  <before>
    <item>Defined performance requirements (SLOs)</item>
    <item>Established baseline metrics</item>
    <item>Identified bottleneck with profiling data</item>
    <item>Quantified expected improvement</item>
  </before>
  <during>
    <item>Changed one thing at a time</item>
    <item>Measured after each change</item>
    <item>Verified no regressions in other areas</item>
    <item>Documented what was changed and why</item>
  </during>
  <after>
    <item>Confirmed improvement meets requirements</item>
    <item>Added performance tests to prevent regression</item>
    <item>Updated documentation</item>
    <item>Shared learnings with team</item>
  </after>
</optimization-checklist>

</knowledge-base>
