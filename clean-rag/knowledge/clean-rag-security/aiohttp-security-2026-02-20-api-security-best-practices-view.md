<!-- Source: https://oneuptime.com/blog/post/2026-02-20-api-security-best-practices/view | Tier: B | Topic: aiohttp-security | Fetched: 2026-06-26 -->

Skip to main content

[ OneUptime ](/)

Open menu

Products

Enterprise

Enterprise

## Built for how you work

Scale your reliability operations with enterprise-grade tools.

[ Enterprise Overview Scale with confidence ](/enterprise/overview) [ Request Demo See it in action ](/enterprise/demo)

[ Contact Sales  ](/legal/contact)

Enterprise

[ Enterprise Overview Solutions for large organizations ](/enterprise/overview) [ Request Demo Schedule a personalized demo ](/enterprise/demo)

Teams

[ DevOps ](/solutions/devops) [ SRE ](/solutions/sre) [ Platform ](/solutions/platform) [ Developers ](/solutions/developers)

Industries

[ FinTech ](/industries/fintech) [ SaaS ](/industries/saas) [ Healthcare ](/industries/healthcare) [ E-Commerce ](/industries/ecommerce) [ Media ](/industries/media) [ Government ](/industries/government)

[Documentation](/docs) [Pricing](/pricing) [Blog](/blog)

[ Get Started Free  ](/accounts/register)

[Pricing](/pricing)

Resources

Resources

## Learn & Connect

Everything you need to get started and succeed.

[ Documentation Guides & tutorials ](/docs) [ API Reference REST API & SDKs ](/reference)

[ Star on GitHub  ](https://github.com/oneuptime/oneuptime)

Learn

[ Blog News & insights ](/blog) [ Status System status ](https://status.oneuptime.com) [ Changelog What's new ](https://github.com/OneUptime/oneuptime/releases) [ Videos Watch & learn ](https://www.youtube.com/@OneUptimehq)

Support

[ Help Center ](/support) [ Contact Us ](/cdn-cgi/l/email-protection#75060005051a0701351a1b100005011c18105b161a18)

Company

[ About Us ](/about) [ Merch Store ](https://shop.oneuptime.com)

[Legal](/legal) [Privacy](/legal/privacy) [Terms](/legal/terms)

100% Open Source

[Sign in](/accounts) [Sign up](/accounts/register)

Close menu

[ Status Page ](/product/status-page) [ Incidents ](/product/incident-management) [ Monitoring ](/product/monitoring) [ On-Call ](/product/on-call) [ Maintenance ](/product/scheduled-maintenance) [ Logs ](/product/logs-management) [ Metrics ](/product/metrics) [ Traces ](/product/traces) [ Exceptions ](/product/exceptions) [ Services ](/product/services) [ Kubernetes ](/product/kubernetes) [ Docker ](/product/docker) [ Podman ](/product/podman) [ Hosts ](/product/host) [ Proxmox ](/product/proxmox) [ AI / LLM Observability ](/product/ai-observability) [ Ceph ](/product/ceph) [ Docker Swarm ](/product/docker-swarm) [ IoT Devices ](/product/iot) [ Serverless ](/product/serverless) [ Cloud ](/product/cloud) [ Profiles ](/product/profiles) [ RUM ](/product/rum) [ Workflows ](/product/workflows) [ Dashboards ](/product/dashboards) [ AI Agent ](/product/ai-agent)

Enterprise

[ DevOps ](/solutions/devops) [ SRE ](/solutions/sre) [ Platform ](/solutions/platform)

[Pricing](/pricing) [Docs](/docs) [Request Demo](/enterprise/demo) [Support](/support)

[Sign up](/accounts/register)

Existing customer? [Sign in](/accounts)

Products

## Explore the OneUptime platform

One platform for monitoring, observability & incident response.

`⌘K`

[ AI Agent Auto-fix issues with AI-powered PRs — analyze incidents and open pull requests automatically. ](/product/ai-agent)

### Essentials

[ Monitoring Uptime & synthetic checks ](/product/monitoring) [ Status Page Communicate incidents to users ](/product/status-page) [ Incidents Detect, manage & resolve ](/product/incident-management) [ On-Call & Alerts Smart routing & escalations ](/product/on-call) [ Scheduled Maintenance Plan & communicate downtime ](/product/scheduled-maintenance)

### Observability

[ Logs Fastest log ingest & search ](/product/logs-management) [ Metrics Application & infra metrics ](/product/metrics) [ Traces Distributed request tracing ](/product/traces) [ Exceptions Error tracking & debugging ](/product/exceptions) [ Profiles CPU & memory profiling ](/product/profiles) [ RUM Real user monitoring ](/product/rum)

### Infrastructure

[ Services Catalog every service you run ](/product/services) [ Kubernetes Cluster & pod observability ](/product/kubernetes) [ Docker Host & container observability ](/product/docker) [ Podman Host & container observability ](/product/podman) [ Hosts Auto-discovered server metrics ](/product/host) [ Proxmox VE clusters, VMs & backups ](/product/proxmox) [ AI / LLM Observability Tokens, cost, traces & prompts ](/product/ai-observability) [ Ceph Storage cluster health ](/product/ceph) [ Docker Swarm Nodes, services, tasks & stacks ](/product/docker-swarm) [ IoT Devices Fleets, sensors & gateways ](/product/iot) [ Serverless Functions & cold starts ](/product/serverless) [ Cloud AWS, GCP & Azure ](/product/cloud)

### Automation & Analytics

[ Workflows No-code automation builder ](/product/workflows) [ Runbooks Auto-trigger response steps ](/product/runbooks) [ Dashboards Custom data visualizations ](/product/dashboards)

No products found

[ 100% Open Source Self-host or use our cloud ](https://github.com/oneuptime/oneuptime)

`↑` `↓` `↵` `esc`

#  API Security Best Practices for Production Applications 

Essential API security best practices including authentication, input validation, rate limiting, and OWASP API Security Top 10. 

By @nawazdhandala

• Feb 20, 2026 • Reading time

[ API Security  ](/blog/tag/api-security) [ Authentication  ](/blog/tag/authentication) [ Authorization  ](/blog/tag/authorization) [ OWASP  ](/blog/tag/owasp) [ Best Practice  ](/blog/tag/best-practice)

##  On this page 

[ ](https://twitter.com/intent/tweet?text=%20API%20Security%20Best%20Practices%20for%20Production%20Applications&url=https%3A%2F%2Foneuptime.com%2Fblog%2Fpost%2F2026-02-20-api-security-best-practices%2Fview "Share on X") [ ](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Foneuptime.com%2Fblog%2Fpost%2F2026-02-20-api-security-best-practices%2Fview "Share on LinkedIn") [ ](https://news.ycombinator.com/submitlink?u=https%3A%2F%2Foneuptime.com%2Fblog%2Fpost%2F2026-02-20-api-security-best-practices%2Fview&t=%20API%20Security%20Best%20Practices%20for%20Production%20Applications "Discuss on Hacker News")

* * *

## Introduction

APIs are the backbone of modern applications, but they are also a prime target for attackers. A single insecure endpoint can expose sensitive data, enable account takeovers, or bring down your entire system. This guide covers essential API security best practices grounded in the OWASP API Security Top 10.

## OWASP API Security Top 10 Overview
    
    
    graph TD
        A[OWASP API Security Top 10] --> B1[API1: Broken Object Level Auth]
        A --> B2[API2: Broken Authentication]
        A --> B3[API3: Broken Object Property Level Authorization]
        A --> B4[API4: Unrestricted Resource Consumption]
        A --> B5[API5: Broken Function Level Authorization]
        A --> B6[API6: Unrestricted Access to Sensitive Business Flows]
        A --> B7[API7: Server Side Request Forgery]
        A --> B8[API8: Security Misconfiguration]
        A --> B9[API9: Improper Inventory Management]
        A --> B10[API10: Unsafe Consumption of APIs]

## Authentication and Authorization

### JWT Validation Middleware
    
    
    # Secure JWT validation middleware for FastAPI
    
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    import jwt
    import httpx
    from functools import lru_cache
    
    app = FastAPI()
    security = HTTPBearer()
    
    # Cache JWKS keys to avoid fetching on every request
    @lru_cache(maxsize=1)
    def get_jwks():
        """Fetch and cache the JWKS from the identity provider."""
        response = httpx.get("https://auth.example.com/.well-known/jwks.json")
        return response.json()
    
    async def validate_token(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> dict:
        """Validate the JWT token and return decoded claims."""
        token = credentials.credentials
    
        try:
            # Decode the token header to find the signing key ID
            header = jwt.get_unverified_header(token)
            jwks = get_jwks()
    
            # Find the matching key in the JWKS
            signing_key = None
            for key in jwks["keys"]:
                if key["kid"] == header["kid"]:
                    signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                    break
    
            if not signing_key:
                raise HTTPException(status_code=401, detail="Invalid signing key")
    
            # Validate signature, expiration, issuer, and audience
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],  # Only allow expected algorithms
                audience="my-api",
                issuer="https://auth.example.com",
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                },
            )
            return claims
    
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

### Object-Level Authorization
    
    
    # Prevent Broken Object Level Authorization (BOLA)
    from fastapi import APIRouter, Depends, HTTPException
    
    router = APIRouter()
    
    @router.get("/api/v1/orders/{order_id}")
    async def get_order(order_id: str, claims: dict = Depends(validate_token)):
        """Fetch an order - always verify ownership."""
        # Extract the authenticated user's ID from token claims
        user_id = claims["sub"]
    
        # Always filter by user_id to prevent unauthorized access
        order = await db.orders.find_one({
            "_id": order_id,
            "user_id": user_id,  # Critical: ensures the user owns this order
        })
    
        if not order:
            # Return 404 instead of 403 to prevent information leakage
            raise HTTPException(status_code=404, detail="Order not found")
    
        return order

## Input Validation

### Request Validation with Pydantic
    
    
    # Strict input validation using Pydantic models
    from pydantic import BaseModel, Field, EmailStr, field_validator
    from typing import Optional
    import re
    
    class CreateUserRequest(BaseModel):
        """Validated user creation request with strict constraints."""
    
        # Limit string lengths to prevent abuse
        username: str = Field(
            min_length=3,
            max_length=30,
            pattern=r"^[a-zA-Z0-9_]+$",  # Only alphanumeric and underscores
        )
        email: EmailStr  # Validates email format
        password: str = Field(min_length=12, max_length=128)
        display_name: Optional[str] = Field(default=None, max_length=100)
    
        @field_validator("password")
        @classmethod
        def validate_password_strength(cls, v: str) -> str:
            """Enforce password complexity requirements."""
            if not re.search(r"[A-Z]", v):
                raise ValueError("Password must contain at least one uppercase letter")
            if not re.search(r"[a-z]", v):
                raise ValueError("Password must contain at least one lowercase letter")
            if not re.search(r"\d", v):
                raise ValueError("Password must contain at least one digit")
            if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
                raise ValueError("Password must contain at least one special character")
            return v
    
    @router.post("/api/v1/users")
    async def create_user(request: CreateUserRequest):
        """Create user with validated input - Pydantic rejects invalid data."""
        # At this point, all input has been validated
        return await user_service.create(request)

## Rate Limiting

### Token Bucket Rate Limiter
    
    
    # Token bucket rate limiter using Redis
    import redis.asyncio as redis
    import time
    from fastapi import Request, HTTPException
    
    class RateLimiter:
        """Token bucket rate limiter backed by Redis."""
    
        def __init__(self, redis_client: redis.Redis):
            self.redis = redis_client
    
        async def check_rate_limit(
            self,
            key: str,
            max_tokens: int = 100,      # Maximum burst capacity
            refill_rate: float = 10.0,   # Tokens added per second
        ) -> bool:
            """Check if request is within rate limits using token bucket."""
            now = time.time()
    
            # Lua script for atomic token bucket operations
            lua_script = """
            local key = KEYS[1]
            local max_tokens = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])
    
            -- Get current bucket state
            local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
            local tokens = tonumber(bucket[1]) or max_tokens
            local last_refill = tonumber(bucket[2]) or now
    
            -- Calculate tokens to add since last refill
            local elapsed = now - last_refill
            tokens = math.min(max_tokens, tokens + (elapsed * refill_rate))
    
            -- Try to consume one token
            if tokens >= 1 then
                tokens = tokens - 1
                redis.call('HSET', key, 'tokens', tokens, 'last_refill', now)
                redis.call('EXPIRE', key, 3600)
                return 1
            else
                return 0
            end
            """
    
            result = await self.redis.eval(lua_script, 1, key, max_tokens, refill_rate, now)
            return result == 1
    
    # Dependency for FastAPI routes
    async def rate_limit_dependency(request: Request):
        """FastAPI dependency that enforces rate limiting per IP."""
        client_ip = request.client.host
        limiter = RateLimiter(request.app.state.redis)
    
        if not await limiter.check_rate_limit(f"rate_limit:{client_ip}"):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": "10"},
            )

## Security Headers
    
    
    # Security headers middleware
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    
    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        """Add security headers to all API responses."""
    
        async def dispatch(self, request: Request, call_next) -> Response:
            response = await call_next(request)
    
            # Prevent MIME type sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"
    
            # Prevent clickjacking
            response.headers["X-Frame-Options"] = "DENY"
    
            # Control referrer information
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
            # Content Security Policy for API responses
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    
            # Strict Transport Security (HTTPS only)
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
            # Remove server header to avoid information leakage
            response.headers.pop("server", None)
    
            return response
    
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

## API Security Architecture
    
    
    graph TD
        Client[Client] -->|HTTPS| WAF[WAF / API Gateway]
        WAF -->|Rate Limiting| Auth[Authentication]
        Auth -->|JWT Validation| Authz[Authorization]
        Authz -->|RBAC / ABAC| Validation[Input Validation]
        Validation -->|Validated Input| Logic[Business Logic]
        Logic -->|Parameterized Queries| DB[(Database)]
        Logic -->|Audit Events| Audit[Audit Log]
        Logic -->|Metrics| Monitor[Monitoring]

## Request Logging and Audit Trail
    
    
    # Structured audit logging for security events
    from fastapi import Depends, HTTPException, Request
    import structlog
    from datetime import datetime, timezone
    
    # Configure structured logger
    logger = structlog.get_logger("audit")
    
    async def log_security_event(
        event_type: str,
        user_id: str,
        resource: str,
        action: str,
        result: str,
        request: Request,
        details: dict = None,
    ):
        """Log a structured security audit event."""
        await logger.ainfo(
            "security_event",
            event_type=event_type,
            user_id=user_id,
            resource=resource,
            action=action,
            result=result,
            client_ip=request.client.host,
            user_agent=request.headers.get("user-agent", "unknown"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_id=getattr(request.state, "request_id", None),
            details=details or {},
        )
    
    # Usage in route handlers
    @router.delete("/api/v1/users/{user_id}")
    async def delete_user(user_id: str, request: Request, claims: dict = Depends(validate_token)):
        """Delete a user with full audit logging."""
        # Check admin permissions
        if "admin" not in claims.get("roles", []):
            await log_security_event("authorization", claims["sub"], f"user:{user_id}", "delete", "denied", request)
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    
        await user_service.delete(user_id)
        await log_security_event("authorization", claims["sub"], f"user:{user_id}", "delete", "success", request)
        return {"status": "deleted"}

## CORS Configuration
    
    
    # Strict CORS configuration for production
    from fastapi.middleware.cors import CORSMiddleware
    
    # Only allow specific, trusted origins
    ALLOWED_ORIGINS = [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,     # Never use ["*"] in production
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=3600,  # Cache preflight responses for 1 hour
    )

## Conclusion

API security is not a single feature but a layered approach. Combine authentication, authorization, input validation, rate limiting, security headers, and audit logging. Follow the OWASP API Security Top 10 as your baseline and continuously monitor for anomalies.

To monitor your API endpoints, track error rates, and get alerted on security anomalies, check out [OneUptime](https://oneuptime.com) for comprehensive API monitoring and incident management.

Share this article

[ ](https://twitter.com/intent/tweet?text=%20API%20Security%20Best%20Practices%20for%20Production%20Applications&url=https%3A%2F%2Foneuptime.com%2Fblog%2Fpost%2F2026-02-20-api-security-best-practices%2Fview "Share on X") [ ](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Foneuptime.com%2Fblog%2Fpost%2F2026-02-20-api-security-best-practices%2Fview "Share on LinkedIn") [ ](https://news.ycombinator.com/submitlink?u=https%3A%2F%2Foneuptime.com%2Fblog%2Fpost%2F2026-02-20-api-security-best-practices%2Fview&t=%20API%20Security%20Best%20Practices%20for%20Production%20Applications "Discuss on Hacker News")

### Nawaz Dhandala

Author

@nawazdhandala • Feb 20, 2026 • 

Nawaz is building OneUptime with a passion for engineering reliable systems and improving observability.

[ GitHub ](https://github.com/nawazdhandala)

Technically validated · May 27, 2026 View report 

### Help improve this post

Every OneUptime blog post is open source. Found a typo, an inaccuracy, or have a clearer way to explain something? Anyone can contribute — your edits make this post better for everyone who reads it next.

[ Edit this post on GitHub ](https://github.com/oneuptime/blog/tree/master/posts/2026-02-20-api-security-best-practices) [ Contributing guidelines ](https://github.com/oneuptime/blog)

[ Open source ](https://github.com/oneuptime/oneuptime)

##  OneUptime is the Open-Source   
Observability Platform 

Your complete reliability stack unified: infrastructure monitoring, incident management, status pages, and APM. Open-source and self-hostable. 

[ Get started for free  ](/accounts/register) [ Request a demo ](/enterprise/demo)

[ Status Page Real-time status updates ](/product/status-page) [ Incidents Detect and resolve fast ](/product/incident-management) [ Monitoring Monitor any resource ](/product/monitoring) [ On-Call Smart alert routing ](/product/on-call) [ Maintenance Plan & communicate downtime ](/product/scheduled-maintenance) [ Logs Fastest log ingest and search ](/product/logs-management) [ Metrics Performance insights ](/product/metrics) [ Traces End-to-end distributed tracing ](/product/traces) [ Exceptions Catch and fix bugs early ](/product/exceptions) [ Workflows Automate any process ](/product/workflows) [ Dashboards Visualize all your data ](/product/dashboards) [ Kubernetes Monitor K8s clusters ](/product/kubernetes) [ Profiles CPU & memory profiling ](/product/profiles)

[ AI Agent Automatically detect, diagnose, and resolve incidents with AI-powered root cause analysis and code fixes. ](/product/ai-agent)

We use cookies to enhance your browsing experience and provide personalized content. By clicking "Accept," you consent to the use of cookies.

Our product uses both first-party and third-party cookies for session storage and for various other purposes.

Please note that disabling certain cookies may affect the functionality and performance of our product.

For more information about how we handle your data and cookies, please read our Privacy Policy.

By continuing to use our site without changing your cookie settings, you agree to our use of cookies as described above. See our [terms](/legal/terms) and our [privacy policy](/legal/privacy)

Accept all Reject all

## Footer

Open Source Observability

### Build reliable systems with confidence

Join thousands of developers using OneUptime to monitor, debug, and optimize their infrastructure, stack, and apps.

[ Read Blog ](/blog) [ Star on GitHub ](https://github.com/oneuptime/oneuptime)

[ ](/)

The complete open-source observability platform. Monitor, debug, and improve your entire stack in one place. 

[ GitHub ](https://github.com/oneuptime/oneuptime) [ X ](https://x.com/oneuptimehq) [ YouTube ](https://www.youtube.com/@OneUptimeHQ) [ Reddit ](https://www.reddit.com/r/oneuptimehq/) [ LinkedIn ](https://www.linkedin.com/company/oneuptime)

Trusted by thousands of teams worldwide - from Fortune 500 enterprises to fast-growing startups. 

### Products

  * [Status Page](/product/status-page)
  * [Incidents](/product/incident-management)
  * [Monitoring](/product/monitoring)
  * [On-Call](/product/on-call)
  * [Logs](/product/logs-management)
  * [Metrics](/product/metrics)
  * [Traces](/product/traces)
  * [Exceptions](/product/exceptions)
  * [Profiles](/product/profiles)
  * [Real User Monitoring](/product/rum)
  * [Kubernetes](/product/kubernetes)
  * [Docker](/product/docker)
  * [Podman](/product/podman)
  * [Hosts](/product/host)
  * [Proxmox](/product/proxmox)
  * [AI / LLM Observability](/product/ai-observability)
  * [Ceph](/product/ceph)
  * [Docker Swarm](/product/docker-swarm)
  * [IoT Devices](/product/iot)
  * [Serverless](/product/serverless)
  * [Cloud](/product/cloud)
  * [Workflows](/product/workflows)
  * [Dashboards](/product/dashboards)
  * [AI Agent](/product/ai-agent)



### Solutions

  * [Enterprise](/enterprise/overview)
  * [Request Demo](/enterprise/demo)
  * [Pricing](/pricing)
  * [Data Residency](/legal/data-residency)



### Teams

  * [DevOps](/solutions/devops)
  * [SRE](/solutions/sre)
  * [Platform](/solutions/platform)
  * [Developers](/solutions/developers)



### Tools

  * [MCP Server](/tool/mcp-server)
  * [CLI](/tool/cli)



### Resources

  * [Documentation](/docs)
  * [API Reference](/reference)
  * [Blog](/blog)
  * [Help & Support](/support)
  * [GitHub](https://github.com/oneuptime/oneuptime)
  * [Changelog](https://github.com/oneuptime/oneuptime/releases)
  * [Open Source Friends](/oss-friends)



### Industries

  * [FinTech](/industries/fintech)
  * [SaaS](/industries/saas)
  * [Healthcare](/industries/healthcare)
  * [E-Commerce](/industries/ecommerce)
  * [Media](/industries/media)
  * [Government](/industries/government)



### Company

  * [About Us](/about)
  * [Careers](https://github.com/OneUptime/interview)
  * [Merch Store](https://shop.oneuptime.com)
  * [Contact](/legal/contact)



### Legal

  * [Trust Center](/trust)
  * [Terms of Service](/legal/terms)
  * [Privacy Policy](/legal/privacy)
  * [SLA](/legal/sla)
  * [Legal Center](/legal)



### Compare

  * [vs PagerDuty](/compare/pagerduty)
  * [vs Statuspage](/compare/statuspage.io)
  * [vs Incident.io](/compare/incident.io)
  * [vs Pingdom](/compare/pingdom)
  * [vs Datadog](/compare/datadog)
  * [vs New Relic](/compare/newrelic)
  * [vs Better Stack](/compare/better-uptime)
  * [vs Uptime Robot](/compare/uptime-robot)
  * [vs Checkly](/compare/checkly)
  * [vs SigNoz](/compare/signoz)



(C) 2026 HackerBay, Inc. All rights reserved.

[ Open Source ](https://github.com/oneuptime/oneuptime) | Made with care for developers worldwide

[SOC 2](/legal/soc-2) [HIPAA](/legal/hipaa) [GDPR](/legal/gdpr) [ISO 27001](/legal/iso-27001)

## Validation report

Technically reviewed for accuracy • May 27, 2026

Loading validation report… 

Automated technical review  Close
