# Application Security Best Practices

<knowledge-base name="security" version="1.0">
<triggers>security, vulnerability, OWASP, injection, XSS, authentication, authorization, secrets, CVE</triggers>
<overview>Secure coding practices and vulnerability prevention. Fixing vulnerabilities early costs up to 100x less than in production.</overview>

<cia-triad foundation="ALL security decisions">
  <aspect name="Confidentiality">
    <questions>Who can see this data? Is it encrypted at rest? In transit?</questions>
    <controls>Encryption, access controls, data classification</controls>
  </aspect>
  <aspect name="Integrity">
    <questions>Can this be tampered with? Is it signed/validated? Are changes tracked?</questions>
    <controls>Hashing, digital signatures, audit logs, checksums</controls>
  </aspect>
  <aspect name="Availability">
    <questions>What if this fails? Is there redundancy? What's recovery time?</questions>
    <controls>Redundancy, backups, failover, load balancing</controls>
  </aspect>
</cia-triad>

<owasp-top-10 year="2025">
  <vulnerability id="A01" name="Broken Access Control">
    <risk>Users accessing data beyond their permissions</risk>
    <prevention>
      <item>Deny by default—access requires explicit permission</item>
      <item>Server-side enforcement (never trust client)</item>
      <item>Use RBAC consistently</item>
      <item>Log access control failures</item>
    </prevention>
  </vulnerability>

  <vulnerability id="A02" name="Security Misconfiguration">
    <risk>Insecure defaults, unnecessary features, verbose errors</risk>
    <prevention>
      <item>Remove unnecessary features, components</item>
      <item>Secure defaults for all environments</item>
      <item>Disable detailed error messages in production</item>
    </prevention>
  </vulnerability>

  <vulnerability id="A03" name="Injection">
    <risk>Untrusted data sent to interpreter (SQL, OS, LDAP)</risk>
    <prevention>
      <item>Use parameterized queries/prepared statements</item>
      <item>Use ORMs carefully (still validate input)</item>
      <item>Escape special characters for specific interpreter</item>
    </prevention>
    <code-example type="bad" lang="js">const query = `SELECT * FROM users WHERE email = '${email}'`;</code-example>
    <code-example type="good" lang="js">const query = 'SELECT * FROM users WHERE email = ?'; db.query(query, [email]);</code-example>
  </vulnerability>

  <vulnerability id="A04" name="Insecure Design">
    <risk>Missing or ineffective security controls in design</risk>
    <prevention>
      <item>Threat modeling during design phase</item>
      <item>Use secure design patterns</item>
      <item>Implement defense in depth</item>
      <item>Principle of least privilege</item>
    </prevention>
  </vulnerability>

  <vulnerability id="A05" name="Security Logging Failures">
    <risk>Breaches go undetected; attackers remain persistent</risk>
    <log>Authentication events, authorization failures, validation failures</log>
    <do-not-log>Passwords, session tokens, credit cards, PII</do-not-log>
  </vulnerability>

  <vulnerability id="A06" name="Vulnerable Components">
    <risk>Known vulnerabilities in dependencies</risk>
    <prevention>
      <item>Inventory all components and versions</item>
      <item>Remove unused dependencies</item>
      <item>Continuously monitor for CVEs</item>
      <item>Automate dependency scanning in CI/CD</item>
    </prevention>
    <tools>npm audit, pip-audit, Snyk, Dependabot</tools>
  </vulnerability>

  <vulnerability id="A07" name="Auth Failures">
    <risk>Credential stuffing, weak passwords, session hijacking</risk>
    <prevention>
      <item>Implement MFA where possible</item>
      <item>Hash passwords with Argon2, bcrypt, or scrypt</item>
      <item>Secure session management</item>
      <item>Rate limit authentication endpoints</item>
    </prevention>
  </vulnerability>

  <vulnerability id="A08" name="Data Integrity Failures">
    <risk>Code/infrastructure without integrity verification</risk>
    <prevention>
      <item>Verify digital signatures on updates</item>
      <item>Use SRI for CDN resources</item>
      <item>Secure CI/CD pipelines</item>
      <item>Sign commits and releases</item>
    </prevention>
  </vulnerability>

  <vulnerability id="A09" name="SSRF">
    <risk>Application fetches remote resource from user-supplied URL</risk>
    <prevention>
      <item>Validate and sanitize all user-supplied URLs</item>
      <item>Block requests to internal/private IPs</item>
      <item>Use allowlists for permitted destinations</item>
    </prevention>
  </vulnerability>

  <vulnerability id="A10" name="Exception Handling">
    <risk>Poor error handling leads to security issues</risk>
    <prevention>
      <item>Handle all exceptions explicitly</item>
      <item>Don't expose stack traces to users</item>
      <item>Fail securely (deny access on error)</item>
    </prevention>
  </vulnerability>
</owasp-top-10>

<input-validation>
  <strategy>
    <rule>Validate on server side - client validation is UX only</rule>
    <rule>Use allowlists - define what IS allowed, not what isn't</rule>
    <rule>Validate type, length, format, range</rule>
    <rule>Encode output - context-appropriate encoding</rule>
  </strategy>
  <output-encoding>
    <context name="HTML body">HTML entity encoding</context>
    <context name="HTML attribute">HTML attribute encoding</context>
    <context name="JavaScript">JavaScript encoding</context>
    <context name="URL">URL encoding</context>
  </output-encoding>
</input-validation>

<authentication>
  <passwords>
    <rule>Minimum 12 characters (length over complexity)</rule>
    <rule>Check against breach databases (Have I Been Pwned)</rule>
    <rule>Use Argon2id, bcrypt, or scrypt for hashing</rule>
  </passwords>
  <sessions>
    <rule>Generate cryptographically random session IDs</rule>
    <rule>Rotate session ID on authentication</rule>
    <rule>Set Secure, HttpOnly, SameSite cookie attributes</rule>
    <rule>Implement idle and absolute timeouts</rule>
  </sessions>
</authentication>

<secrets-management>
  <never-do>
    <item>Hardcode secrets in source code</item>
    <item>Commit secrets to version control</item>
    <item>Log secrets (even partially)</item>
    <item>Pass secrets in URLs</item>
  </never-do>
  <best-practices>
    <item>Use environment variables or secret managers</item>
    <item>Rotate secrets regularly</item>
    <item>Different secrets per environment</item>
    <item>Use short-lived credentials</item>
  </best-practices>
  <tools>HashiCorp Vault, AWS Secrets Manager, Azure Key Vault</tools>
</secrets-management>

<code-review-checklist>
  <critical block-pr="true">
    <item>No hardcoded secrets or credentials</item>
    <item>No SQL injection vulnerabilities</item>
    <item>No command injection vulnerabilities</item>
    <item>Authentication required for sensitive endpoints</item>
    <item>Authorization checked at access points</item>
  </critical>
  <high-priority>
    <item>All user input validated</item>
    <item>Output properly encoded for context</item>
    <item>Error messages don't leak sensitive info</item>
    <item>Dependencies have no critical CVEs</item>
  </high-priority>
</code-review-checklist>

<cicd-security>
  <gates>
    <gate order="1" name="SAST">Static analysis before merge</gate>
    <gate order="2" name="Dependency scanning">Check for vulnerable packages</gate>
    <gate order="3" name="Secret scanning">Detect leaked credentials</gate>
    <gate order="4" name="Container scanning">Check base images</gate>
    <gate order="5" name="DAST">Dynamic testing in staging</gate>
  </gates>
  <tools>
    <category name="SAST">SonarQube, Semgrep, CodeQL</category>
    <category name="Dependencies">Snyk, Dependabot, npm audit</category>
    <category name="Secrets">git-secrets, trufflehog, gitleaks</category>
    <category name="Containers">Trivy, Clair, Anchore</category>
  </tools>
</cicd-security>

<security-headers>
  <header name="Content-Security-Policy">default-src 'self'</header>
  <header name="Strict-Transport-Security">max-age=31536000; includeSubDomains</header>
  <header name="X-Content-Type-Options">nosniff</header>
  <header name="X-Frame-Options">DENY</header>
  <header name="Referrer-Policy">strict-origin-when-cross-origin</header>
</security-headers>

<incident-response>
  <steps>
    <step order="1">Assess severity - Is it actively exploitable?</step>
    <step order="2">Contain - Mitigate without full fix?</step>
    <step order="3">Document - Record findings and evidence</step>
    <step order="4">Fix - Develop and test remediation</step>
    <step order="5">Verify - Confirm fix works</step>
    <step order="6">Learn - Prevent recurrence</step>
  </steps>
  <severity-classification>
    <level name="Critical" criteria="RCE, data breach possible" response="Immediate"/>
    <level name="High" criteria="Auth bypass, injection" response="24-48 hours"/>
    <level name="Medium" criteria="XSS, information disclosure" response="1 week"/>
    <level name="Low" criteria="Minor misconfiguration" response="Next sprint"/>
  </severity-classification>
</incident-response>

</knowledge-base>
