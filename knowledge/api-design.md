# API Design Best Practices

<knowledge-base name="api-design" version="1.0">
<triggers>API, REST, endpoint, HTTP, versioning, request, response, GraphQL, query, mutation, subscription, schema</triggers>
<overview>REST and GraphQL API design principles, versioning strategies, error handling, and documentation standards.</overview>

<decision-matrix title="REST vs GraphQL">
  <factor name="Data requirements" rest="Fixed, known responses" graphql="Client-defined, flexible"/>
  <factor name="Clients" rest="Homogeneous (similar needs)" graphql="Heterogeneous (different needs)"/>
  <factor name="Caching" rest="HTTP caching built-in" graphql="Requires custom caching"/>
  <factor name="File uploads" rest="Native support" graphql="Requires extensions"/>
  <factor name="Over-fetching" rest="Common problem" graphql="Solved by design"/>
  <factor name="Real-time" rest="Requires WebSockets" graphql="Subscriptions built-in"/>
  <recommendation when="Simple CRUD, public APIs, caching critical">REST</recommendation>
  <recommendation when="Complex data relationships, multiple clients, avoiding over/under-fetching">GraphQL</recommendation>
</decision-matrix>

<core-principles>
  <api-first>
    <step>Design API contract before writing code</step>
    <step>Review with stakeholders</step>
    <step>Use OpenAPI/Swagger for specification</step>
    <step>Generate code from spec, not spec from code</step>
  </api-first>
  <rest-constraints>
    <constraint name="Client-Server">Separation of concerns</constraint>
    <constraint name="Stateless">Each request contains all needed info</constraint>
    <constraint name="Cacheable">Responses indicate cacheability</constraint>
    <constraint name="Uniform Interface">Consistent resource addressing</constraint>
    <constraint name="Layered System">Intermediaries transparent to client</constraint>
  </rest-constraints>
</core-principles>

<rest-api>

<resource-design>
  <url-pattern verb="GET" path="/resources">List all</url-pattern>
  <url-pattern verb="GET" path="/resources/{id}">Get one</url-pattern>
  <url-pattern verb="POST" path="/resources">Create</url-pattern>
  <url-pattern verb="PUT" path="/resources/{id}">Replace</url-pattern>
  <url-pattern verb="PATCH" path="/resources/{id}">Partial update</url-pattern>
  <url-pattern verb="DELETE" path="/resources/{id}">Delete</url-pattern>

  <naming-conventions>
    <rule>Plural nouns: /users, /orders, /products</rule>
    <rule>Lowercase: /user-profiles not /UserProfiles</rule>
    <rule>Hyphens for readability: /user-accounts not /user_accounts</rule>
    <rule>No file extensions: /users not /users.json</rule>
  </naming-conventions>

  <nested-resources max-depth="2-3">
    <example>GET /users/123/orders (User's orders)</example>
    <example>POST /users/123/orders (Create order for user)</example>
  </nested-resources>

  <query-params>
    <param type="Filter">?status=active</param>
    <param type="Sort">?sort=created_at&amp;order=desc</param>
    <param type="Paginate">?page=2&amp;limit=20</param>
    <param type="Sparse fields">?fields=id,name,email</param>
  </query-params>
</resource-design>

<http-methods>
  <method name="GET" purpose="Retrieve" idempotent="yes" safe="yes" body="no"/>
  <method name="POST" purpose="Create" idempotent="no" safe="no" body="yes"/>
  <method name="PUT" purpose="Replace" idempotent="yes" safe="no" body="yes"/>
  <method name="PATCH" purpose="Partial update" idempotent="no" safe="no" body="yes"/>
  <method name="DELETE" purpose="Remove" idempotent="yes" safe="no" body="optional"/>
</http-methods>

<status-codes>
  <category name="Success (2xx)">
    <code value="200" name="OK" use="Successful GET, PUT, PATCH"/>
    <code value="201" name="Created" use="Successful POST, resource created"/>
    <code value="204" name="No Content" use="Successful DELETE"/>
  </category>
  <category name="Client Error (4xx)">
    <code value="400" name="Bad Request" use="Invalid request body/parameters"/>
    <code value="401" name="Unauthorized" use="Missing/invalid authentication"/>
    <code value="403" name="Forbidden" use="Authenticated but not authorized"/>
    <code value="404" name="Not Found" use="Resource doesn't exist"/>
    <code value="409" name="Conflict" use="State conflict (duplicate, version)"/>
    <code value="422" name="Unprocessable Entity" use="Validation errors"/>
    <code value="429" name="Too Many Requests" use="Rate limit exceeded"/>
  </category>
  <category name="Server Error (5xx)">
    <code value="500" name="Internal Server Error" use="Unexpected server error"/>
    <code value="502" name="Bad Gateway" use="Upstream service error"/>
    <code value="503" name="Service Unavailable" use="Temporary overload/maintenance"/>
    <code value="504" name="Gateway Timeout" use="Upstream timeout"/>
  </category>
  <antipattern>200 with error in body - Use proper status codes!</antipattern>
</status-codes>

<error-handling>
  <format name="RFC 9457 Problem Details"><![CDATA[
{
  "type": "https://api.example.com/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "The email address format is invalid",
  "instance": "/users/123",
  "errors": [{"field": "email", "message": "Must be valid email"}]
}
]]></format>
  <best-practices>
    <practice>Use appropriate HTTP status codes</practice>
    <practice>Be consistent - same format across all endpoints</practice>
    <practice>Be specific - tell clients what went wrong</practice>
    <practice>Be secure - don't expose internal details</practice>
    <practice>Be actionable - help clients fix the problem</practice>
  </best-practices>
</error-handling>

<versioning>
  <strategy name="URL Path" example="/v1/users" recommended="true">
    <pros>Explicit, easy to route, cache-friendly</pros>
    <cons>URL changes between versions</cons>
  </strategy>
  <strategy name="Header" example="Accept: application/vnd.api.v2+json">
    <pros>Clean URLs</pros>
    <cons>Harder to test, less visible</cons>
  </strategy>
  <strategy name="Query Param" example="/users?version=2">
    <pros>Simple to implement</pros>
    <cons>Clutters query string</cons>
  </strategy>
  <deprecation-headers>
    <header>Sunset: Sat, 31 Dec 2025 23:59:59 GMT</header>
    <header>Deprecation: Sun, 01 Jan 2025 00:00:00 GMT</header>
    <header>Link: &lt;.../v3/users&gt;; rel="successor-version"</header>
  </deprecation-headers>
</versioning>

<pagination>
  <type name="Offset-Based" example="?offset=40&amp;limit=20" simple="true">
    <response-fields>total, limit, offset, next, prev</response-fields>
  </type>
  <type name="Cursor-Based" example="?cursor=eyJpZCI6MTIzfQ&amp;limit=20" scalable="true">
    <response-fields>next_cursor, has_more</response-fields>
    <pros>Works well with real-time data, no page drift</pros>
    <cons>No random access to pages</cons>
  </type>
</pagination>

<rate-limiting>
  <headers>
    <header name="X-RateLimit-Limit">Max requests per window</header>
    <header name="X-RateLimit-Remaining">Requests left</header>
    <header name="X-RateLimit-Reset">Unix timestamp of reset</header>
    <header name="Retry-After">Seconds until retry allowed</header>
  </headers>
</rate-limiting>

<security>
  <methods>
    <method name="API Key" use="Simple, server-to-server"/>
    <method name="OAuth 2.0" use="User authorization, third-party apps"/>
    <method name="JWT" use="Stateless authentication"/>
  </methods>
  <best-practices>
    <practice>Always use HTTPS (TLS 1.3 preferred)</practice>
    <practice>Authenticate in headers - never in URL query params</practice>
    <practice>Use short-lived tokens - refresh for long sessions</practice>
    <practice>Implement rate limiting - prevent abuse</practice>
    <practice>Validate all input - don't trust client data</practice>
    <practice>Log security events - auth failures, unusual patterns</practice>
  </best-practices>
</security>

<request-response>
  <standards>
    <standard name="Dates">ISO 8601: "2024-01-15T10:30:00Z"</standard>
    <standard name="Enums">lowercase strings: "active"</standard>
    <standard name="IDs">strings to avoid integer overflow</standard>
    <standard name="Nulls">explicit null for clearing values</standard>
  </standards>
</request-response>

</rest-api>

<graphql-api>

<core-concepts>
  <concept name="Schema">Contract defining types, queries, mutations, subscriptions</concept>
  <concept name="Queries">Read operations (like GET)</concept>
  <concept name="Mutations">Write operations (like POST/PUT/DELETE)</concept>
  <concept name="Subscriptions">Real-time updates via WebSocket</concept>
  <concept name="Resolvers">Functions that fetch data for each field</concept>
</core-concepts>

<schema-design>
  <type-patterns><![CDATA[
# Scalars: ID, String, Int, Float, Boolean
scalar DateTime
scalar Email

# Object types
type User {
  id: ID!                    # ! = non-nullable
  email: Email!
  orders: [Order!]!          # Non-null list of non-null orders
  profile: Profile           # Nullable relation
}

# Enum types
enum OrderStatus {
  PENDING
  PROCESSING
  SHIPPED
  DELIVERED
}

# Input types for mutations
input CreateUserInput {
  email: Email!
  name: String!
  password: String!
}

# Interface for shared fields
interface Node {
  id: ID!
}

# Union for polymorphic returns
union SearchResult = User | Order | Product
]]></type-patterns>
</schema-design>

<query-patterns>
  <pattern name="Single resource">user(id: ID!): User</pattern>
  <pattern name="List with pagination">users(first: Int, after: String): UserConnection!</pattern>
  <pattern name="Current user">me: User</pattern>
  <pattern name="Search">search(query: String!): [SearchResult!]!</pattern>

  <relay-pagination><![CDATA[
type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type UserEdge {
  node: User!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}
]]></relay-pagination>

  <n-plus-1-solution>Use DataLoader to batch requests into single query</n-plus-1-solution>
</query-patterns>

<mutation-patterns>
  <structure>
    <rule>Specific, action-oriented names: createUser, placeOrder, cancelOrder</rule>
    <rule>Always return payload type (not just entity)</rule>
    <rule>Include errors array in payload</rule>
    <rule>Include success boolean for quick check</rule>
  </structure>
  <payload-pattern><![CDATA[
type CreateUserPayload {
  user: User                 # The created entity
  errors: [UserError!]!      # Validation/business errors
  success: Boolean!          # Quick success check
}

type UserError {
  field: String              # Which field had error
  message: String!           # Human-readable message
  code: ErrorCode!           # Machine-readable code
}
]]></payload-pattern>
</mutation-patterns>

<subscription-patterns><![CDATA[
type Subscription {
  orderUpdated(orderId: ID!): Order!
  userNotifications: Notification!
  newOrders(status: OrderStatus): Order!
}
]]></subscription-patterns>

<error-handling>
  <category name="Top-level errors" use="Schema validation, auth, server errors">
    <location>Returned in "errors" array</location>
  </category>
  <category name="Field-level errors" use="Business/validation errors">
    <location>Returned in mutation payload</location>
  </category>
  <best-practices>
    <practice>Use payload errors for expected failures (validation, business rules)</practice>
    <practice>Use top-level errors for unexpected failures (auth, server errors)</practice>
    <practice>Include error codes for programmatic handling</practice>
    <practice>Never expose internal details (stack traces, SQL errors)</practice>
  </best-practices>
</error-handling>

<schema-evolution>
  <safe-changes>
    <change>Adding new fields (nullable or with defaults)</change>
    <change>Adding new types</change>
    <change>Adding new enum values</change>
    <change>Deprecating (not removing) fields</change>
  </safe-changes>
  <breaking-changes avoid="true">
    <change>Removing fields/types</change>
    <change>Changing field types (String to Int)</change>
    <change>Making nullable field non-nullable</change>
    <change>Removing enum values</change>
    <change>Renaming fields/types</change>
  </breaking-changes>
  <deprecation><![CDATA[
fullName: String @deprecated(reason: "Use 'name' instead. Will be removed 2025-06-01")
]]></deprecation>
  <evolution-timeline>
    <step order="1">Add new field alongside old</step>
    <step order="2">Mark old field @deprecated with date</step>
    <step order="3">Monitor usage of deprecated field</step>
    <step order="4">Remove after deprecation period (6+ months)</step>
  </evolution-timeline>
</schema-evolution>

<security>
  <query-limits>
    <limit type="Depth" value="10" tool="graphql-depth-limit"/>
    <limit type="Complexity" value="1000" tool="graphql-validation-complexity"/>
  </query-limits>
  <persisted-queries>Only allow pre-approved queries in production</persisted-queries>
  <authorization><![CDATA[
directive @auth(requires: Role!) on FIELD_DEFINITION

type Query {
  users: [User!]! @auth(requires: ADMIN)
  me: User @auth(requires: USER)
  publicProducts: [Product!]!  # No auth required
}
]]></authorization>
</security>

<performance>
  <caching><![CDATA[
type User @cacheControl(maxAge: 60) {
  id: ID!
  email: String! @cacheControl(maxAge: 0)  # No cache for PII
}
]]></caching>
  <batching>Always use DataLoader for relationships</batching>
  <query-planning>Parse query info to determine which fields are requested, fetch only what's needed</query-planning>
</performance>

</graphql-api>

<checklists>

<rest-checklist>
  <section name="Resource Design">
    <item>Nouns for resources (not verbs)</item>
    <item>Plural names for collections</item>
    <item>Consistent naming conventions</item>
    <item>Sensible nesting depth</item>
  </section>
  <section name="HTTP Semantics">
    <item>Correct methods for operations</item>
    <item>Appropriate status codes</item>
    <item>Idempotent operations where expected</item>
  </section>
  <section name="Error Handling">
    <item>Consistent error format (RFC 9457)</item>
    <item>Specific, actionable messages</item>
    <item>No internal details exposed</item>
  </section>
  <section name="Security">
    <item>HTTPS enforced</item>
    <item>Authentication in headers</item>
    <item>Rate limiting implemented</item>
    <item>Input validation</item>
  </section>
</rest-checklist>

<graphql-checklist>
  <section name="Schema Design">
    <item>Specific, domain-driven type names</item>
    <item>Implement Node interface for relay compatibility</item>
    <item>Use input types for mutation arguments</item>
    <item>Use enums for fixed value sets</item>
  </section>
  <section name="Queries">
    <item>Implement cursor-based pagination</item>
    <item>Use DataLoader for all relationships</item>
    <item>Add filtering and sorting options</item>
    <item>Limit query depth and complexity</item>
  </section>
  <section name="Mutations">
    <item>Use payload types with errors array</item>
    <item>Use specific action verbs (createX, updateX)</item>
    <item>Validate input at resolver level</item>
    <item>Return affected entity in payload</item>
  </section>
  <section name="Evolution">
    <item>Use @deprecated before removing</item>
    <item>Document deprecation timeline</item>
    <item>Monitor deprecated field usage</item>
    <item>Plan migration path for clients</item>
  </section>
</graphql-checklist>

</checklists>

<references>
  <ref name="Microsoft Azure REST API Guidelines" url="https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design"/>
  <ref name="Google Cloud API Design Guide" url="https://cloud.google.com/apis/design"/>
  <ref name="RFC 9457 - Problem Details" url="https://www.rfc-editor.org/rfc/rfc9457"/>
  <ref name="GraphQL Official Documentation" url="https://graphql.org/learn/"/>
  <ref name="Relay GraphQL Server Specification" url="https://relay.dev/docs/guides/graphql-server-specification/"/>
</references>

</knowledge-base>
