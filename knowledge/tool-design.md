# Tool Design for AI Agents

<knowledge-base name="tool-design" version="1.0">
<triggers>tool, MCP, tool definition, API, function, parameter, tool use, tool call</triggers>
<overview>Well-designed tools dramatically improve agent performance. Poorly designed tools waste tokens and cause errors.</overview>

<core-principles>
  <principle name="Clear Naming">
    <do name="search_orders_by_customer_id" description="Search for orders placed by a specific customer. Returns order summaries with IDs, dates, and totals."/>
    <dont name="search" description="Search for things"/>
    <rule>Use explicit, unambiguous names</rule>
  </principle>

  <principle name="Self-Documenting Parameters">
    <do><![CDATA[{
  "customer_id": {
    "type": "string",
    "description": "Customer UUID (e.g., 'cust_abc123'). Must be 12 characters.",
    "pattern": "^cust_[a-z0-9]{8}$"
  },
  "status_filter": {
    "type": "string",
    "enum": ["pending", "shipped", "delivered", "cancelled"]
  }
}]]></do>
    <dont><![CDATA[{ "id": { "type": "string" } }]]></dont>
    <rule>Include type hints, examples, constraints</rule>
  </principle>

  <principle name="Actionable Error Messages">
    <do><![CDATA[{
  "error": true,
  "message": "Invalid date format. Expected YYYY-MM-DD, got '12/25/2024'",
  "suggestion": "Use '2024-12-25' instead"
}]]></do>
    <dont><![CDATA[{ "error": true, "code": "E_INVALID_PARAM" }]]></dont>
    <rule>Return specific, correctable errors</rule>
  </principle>

  <principle name="Token-Efficient Responses">
    <do>Return order_id, customer_name, total, status, total_count, has_more</do>
    <dont>Return 50+ fields including internal UUIDs, timestamps in ms, carrier IDs</dont>
    <rule>Return only high-signal information</rule>
  </principle>
</core-principles>

<response-design>
  <pagination>
    <param name="limit" default="20" max="100">Max results</param>
    <param name="offset" default="0">Skip N results</param>
    <param name="cursor">For cursor-based pagination</param>
    <response-fields>results, total_count, has_more, next_cursor</response-fields>
  </pagination>

  <format-control>
    <option name="concise">Names and IDs only (default)</option>
    <option name="detailed">Full metadata</option>
  </format-control>

  <identifier-preferences>
    <prefer for="display">name, title</prefer>
    <avoid for="display">uuid, internal_id</avoid>
    <prefer for="type">file_type: "image"</prefer>
    <avoid for="type">mime_type: "image/jpeg"</avoid>
    <prefer for="dates">created: "2024-12-12"</prefer>
    <avoid for="dates">created_ms: 1702358400000</avoid>
  </identifier-preferences>
</response-design>

<tool-scope>
  <anti-pattern name="One Tool Per Endpoint">
    <bad>create_user, get_user, update_user_email, update_user_name, update_user_settings, delete_user, list_users, search_users... (20+ tools)</bad>
    <good>manage_user (create, update, delete), search_users (list, filter, paginate)</good>
  </anti-pattern>

  <when-to-split>Different authentication, very different use cases, complex params per operation</when-to-split>
  <when-to-combine>Same entity different operations, logically sequential, same error patterns</when-to-combine>

  <namespacing>
    <good>github_repos_search, github_repos_create, github_issues_list</good>
    <bad>searchRepos, createRepo, listIssues, create_issue</bad>
  </namespacing>
</tool-scope>

<error-handling>
  <error-categories>
    <category code="400" name="Invalid Input" action="Fix parameters, retry"/>
    <category code="404" name="Not Found" action="Try different search"/>
    <category code="429" name="Rate Limited" action="Wait, retry"/>
    <category code="401/403" name="Auth Failed" action="Report BLOCKED"/>
    <category code="500+" name="Server Error" action="Retry with backoff"/>
  </error-categories>

  <steering-example><![CDATA[{
  "error": true,
  "message": "Search returned 10,000+ results",
  "suggestion": "Add filters to narrow results. Try date_range or status filters.",
  "tip": "Smaller, targeted searches are more efficient"
}]]></steering-example>
</error-handling>

<token-budget>
  <definition-costs>
    <component name="Tool name + description" tokens="50-100"/>
    <component name="Each parameter" tokens="20-50"/>
    <component name="Enum values" tokens="5-10 each"/>
    <component name="Examples in description" tokens="30-50 each"/>
  </definition-costs>

  <optimization>
    <strategy>Prune unused parameters</strategy>
    <strategy>Collapse similar tools</strategy>
    <strategy>Default sensible values</strategy>
    <strategy>Lazy loading: only include advanced tools when needed</strategy>
  </optimization>

  <multi-server-costs>
    <setup servers="1" tools="5" tokens="~5K"/>
    <setup servers="3" tools="15" tokens="~25K"/>
    <setup servers="5" tools="30+" tokens="~55K"/>
    <mitigation>Only connect servers needed for current task</mitigation>
  </multi-server-costs>
</token-budget>

<evaluation>
  <test-scenario><![CDATA[
Task: Find all failed orders from last week
Expected: search_orders(status="failed", date_range="last_7_days")
If >20 results: paginate with cursor
Success: Finds all (precision), no unnecessary calls (efficiency), handles pagination
]]></test-scenario>

  <usage-patterns>
    <pattern symptom="Many retries with param changes" problem="Unclear parameter spec" fix="Add examples"/>
    <pattern symptom="Redundant tool calls" problem="Missing pagination" fix="Add pagination"/>
    <pattern symptom="Wrong tool selection" problem="Ambiguous names" fix="Improve descriptions"/>
    <pattern symptom="Large response handling" problem="Missing truncation" fix="Add limits"/>
  </usage-patterns>

  <refinement-cycle>
    <step>Run evaluation scenarios</step>
    <step>Analyze failure patterns</step>
    <step>Identify tool rough edges</step>
    <step>Refine descriptions/parameters</step>
    <step>Re-evaluate</step>
    <step>Repeat until metrics improve</step>
  </refinement-cycle>
</evaluation>

<source>Writing Tools for Agents - anthropic.com/engineering</source>

</knowledge-base>
