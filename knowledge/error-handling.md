# Error Handling Knowledge Base

<knowledge-base name="error-handling" version="1.0">
<triggers>error, exception, handling, recovery, retry, fault tolerance, failure, catch, throw</triggers>
<overview>Error design patterns, recovery strategies, and best practices across languages.</overview>

<design-principles>
  <principle name="Fail Fast">
    <rule>Detect and report errors as early as possible</rule>
    <good>Validate input immediately at function entry</good>
    <bad>Fail deep in processing when items is None</bad>
  </principle>
  <principle name="Be Specific">
    <rule>Use specific error types, not generic ones</rule>
    <good>OrderNotFoundError, InsufficientInventoryError, PaymentDeclinedError</good>
    <bad>Exception("Something went wrong"), RuntimeError("Error")</bad>
  </principle>
  <principle name="Include Context">
    <rule>Errors should contain debugging information</rule>
    <good>Include order_id, user_id, items, original_error</good>
    <bad>raise Exception("Order failed")</bad>
  </principle>
  <principle name="Don't Swallow Errors">
    <rule>Never hide errors silently</rule>
    <bad>except Exception: pass</bad>
    <good>Log with context and re-raise</good>
  </principle>
</design-principles>

<error-hierarchy><![CDATA[
ApplicationError (base)
├── ValidationError
│   ├── InvalidInputError
│   ├── MissingFieldError
│   └── InvalidFormatError
├── BusinessError
│   ├── InsufficientFundsError
│   ├── ItemNotAvailableError
│   └── PermissionDeniedError
├── IntegrationError
│   ├── DatabaseError
│   ├── ExternalServiceError
│   └── TimeoutError
└── SystemError
    ├── ConfigurationError
    └── ResourceExhaustedError
]]></error-hierarchy>

<exception-vs-result>
  <use-exceptions-when>
    <condition>Truly exceptional conditions (shouldn't happen in normal flow)</condition>
    <condition>Errors that can't be handled locally</condition>
    <condition>Crossing module boundaries</condition>
    <condition>I/O errors, system failures</condition>
  </use-exceptions-when>
  <use-result-types-when>
    <condition>Expected failure cases (validation, not found)</condition>
    <condition>Errors that caller should handle</condition>
    <condition>Functional programming style</condition>
    <condition>When you want to force error handling</condition>
  </use-result-types-when>
</exception-vs-result>

<recovery-patterns>
  <pattern name="Retry with Backoff">
    <description>Exponential backoff with jitter for transient failures</description>
    <formula>delay = min(base_delay * (2 ** attempt), max_delay) + jitter</formula>
    <applies-to>ConnectionError, TimeoutError</applies-to>
  </pattern>
  <pattern name="Circuit Breaker">
    <states>
      <state name="CLOSED">Normal operation</state>
      <state name="OPEN">Failing, reject calls</state>
      <state name="HALF_OPEN">Testing if recovered</state>
    </states>
    <config>failure_threshold=5, recovery_timeout=30</config>
  </pattern>
  <pattern name="Fallback">
    <description>Try primary source, fall back to cache if unavailable</description>
    <example>Database unavailable → use cache → both fail → ServiceUnavailableError</example>
  </pattern>
  <pattern name="Graceful Degradation">
    <description>Return full details if available, partial if some services fail</description>
    <example>Core data required, reviews/recommendations optional (degrade to empty)</example>
  </pattern>
</recovery-patterns>

<http-error-handling>
  <rfc9457-format><![CDATA[
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Failed",
  "status": 400,
  "detail": "The request body contains invalid data",
  "instance": "/orders/12345",
  "errors": [{"field": "email", "message": "Must be a valid email address"}]
}
]]></rfc9457-format>
  <status-codes>
    <code value="400" when="Client error - bad request, validation failure"/>
    <code value="401" when="Authentication required"/>
    <code value="403" when="Authenticated but not authorized"/>
    <code value="404" when="Resource not found"/>
    <code value="409" when="Conflict (e.g., duplicate resource)"/>
    <code value="422" when="Unprocessable entity (semantic error)"/>
    <code value="429" when="Rate limit exceeded"/>
    <code value="500" when="Server error - unexpected failure"/>
    <code value="502" when="Bad gateway - upstream service failed"/>
    <code value="503" when="Service unavailable - temporary overload"/>
    <code value="504" when="Gateway timeout - upstream timeout"/>
  </status-codes>
</http-error-handling>

<logging-best-practices>
  <log>
    <item>order_id, user_id, total (context)</item>
    <item>error_type, error_message, error_code (error details)</item>
    <item>trace_id, span_id (tracing)</item>
    <item>exc_info=True (include stack trace)</item>
  </log>
  <do-not-log>
    <item>Passwords, tokens, API keys</item>
    <item>Full credit card numbers</item>
    <item>Personal identifiable information (PII)</item>
    <item>Sensitive business data</item>
  </do-not-log>
</logging-best-practices>

<anti-patterns>
  <anti-pattern name="Pokemon Exception Handling">
    <bad>except: pass (catches everything including KeyboardInterrupt)</bad>
    <good>except (ValueError, TypeError) as e: handle_error(e)</good>
  </anti-pattern>
  <anti-pattern name="Exception as Control Flow">
    <bad>Using exceptions for expected cases like user not found</bad>
    <good>Return None or use Result type for expected failures</good>
  </anti-pattern>
  <anti-pattern name="Rethrowing Without Context">
    <bad>raise RuntimeError("Processing failed") - loses original</bad>
    <good>raise RuntimeError("Processing failed") from e</good>
  </anti-pattern>
  <anti-pattern name="Logging and Rethrowing">
    <bad>Log then raise (will be logged again up the stack)</bad>
    <good>Log once at the handling point, or just rethrow</good>
  </anti-pattern>
</anti-patterns>

<language-patterns>
  <language name="Python">
    <pattern>Context managers for cleanup (__enter__/__exit__)</pattern>
    <pattern>Exception chaining: raise NewError() from e</pattern>
  </language>
  <language name="JavaScript/TypeScript">
    <pattern>Custom error classes extending Error</pattern>
    <pattern>Error.captureStackTrace for clean traces</pattern>
    <pattern>NetworkError with { cause: error }</pattern>
  </language>
  <language name="Go">
    <pattern>Custom error types with Error() method</pattern>
    <pattern>Error wrapping: fmt.Errorf("failed: %w", err)</pattern>
    <pattern>errors.Is() for checking wrapped errors</pattern>
  </language>
</language-patterns>

<checklist>
  <design-phase>
    <item>Defined error hierarchy for the application</item>
    <item>Identified recoverable vs non-recoverable errors</item>
    <item>Designed error response format for APIs</item>
    <item>Planned retry/fallback strategies</item>
  </design-phase>
  <implementation>
    <item>Specific exception types used</item>
    <item>Errors include relevant context</item>
    <item>No swallowed exceptions</item>
    <item>Proper cleanup in finally/defer/using</item>
    <item>Async errors properly handled</item>
  </implementation>
  <observability>
    <item>Errors logged with context</item>
    <item>Sensitive data excluded from logs</item>
    <item>Error metrics tracked</item>
    <item>Alerts configured for critical errors</item>
  </observability>
  <testing>
    <item>Error paths tested</item>
    <item>Recovery mechanisms tested</item>
    <item>Timeout behavior tested</item>
    <item>Concurrent error handling tested</item>
  </testing>
</checklist>

</knowledge-base>
