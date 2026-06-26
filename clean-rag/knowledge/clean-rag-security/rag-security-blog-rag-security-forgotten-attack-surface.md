<!-- Source: https://christian-schneider.net/blog/rag-security-forgotten-attack-surface/ | Tier: B | Topic: rag-security | Fetched: 2026-06-26 -->

  * [mail@christian-schneider.net](mailto:mail@christian-schneider.net)
  * [+49 178 3081340](tel:+49%20178%203081340)



[](/)

  * [About](/about/)
  * [Service](/service/)

[Application Pentest](/service/application-pentest/) [API Security Check](/service/api-security-check/) [Attack Surface Mapping](/service/attack-surface-mapping/) [Container Platform Review](/service/container-platform-review/) [Cloud Security Check](/service/cloud-security-check/) [Secure SDLC Process Review](/service/secure-sdlc-process-review/)

  * [Consulting](/consulting/)

[Agile Threat Modeling](/consulting/agile-threat-modeling/) [Attack Tree Quickstart](/consulting/attacktree-quickstart/) [Agentic AI Security](/consulting/agentic-ai-security/) [Coding Agent Security](/consulting/coding-agent-security/) [Security Sparring Partner](/consulting/security-sparring-partner/) [Security Architecture](/consulting/security-architecture/) [DevSecOps Pipeline](/consulting/devsecops-pipeline/)

  * [Training](/training/)

[Web Security Bootcamp](/training/web-security-bootcamp/) [Review & Reflect](/training/review-and-reflect/) [Custom Focus Session](/training/custom-focus-session/) [Pentesting Training](/training/pentesting-training/) [Live Hacking Event](/training/live-hacking-event/)

  * [Development](/development/)

[Attack Tree](/development/attacktree-free-saas/) [Threagile](/development/threagile-support-subscription/) [Workshop Board](/development/workshopboard-free-saas/)

  * [Blog](/blog/)

[Contact](/contact/)

# RAG security: the forgotten attack surface

Your knowledge base might be your biggest vulnerability

Christian Schneider · 19 Feb 2026 · 12 min read

### The trust paradox in RAG systems

This post is part of my [series on securing agentic AI systems](/securing-agentic-ai/), covering attack surfaces, defense patterns, and threat modeling for AI agents.

TL;DR

RAG systems have a fundamental trust paradox: user queries are treated as untrusted input, but retrieved context from the knowledge base is implicitly trusted, even though both enter the same prompt. According to research published at USENIX Security 2025, just five carefully crafted documents targeting a specific query can manipulate AI responses with over 90% success, even in a database of millions. OWASP's LLM08:2025 now formally recognizes vector and embedding weaknesses as a top-10 risk, including embedding inversion attacks that can recover 50-70% of original input words if the vectors are compromised. Securing RAG requires defense-in-depth across ingestion, retrieval, and generation phases, treating every document like code and every embedding like sensitive data.

_Read on if your AI application retrieves context from a knowledge base — the trust boundary you're probably not defending is between your documents and the prompt._

If you have deployed a Retrieval-Augmented Generation (RAG) system, your security team likely focused on the obvious attack vector: malicious user queries. You added input validation, implemented guardrails (filters that detect and block malicious prompts), maybe even deployed a prompt injection classifier. The user-facing door is locked.

**But there’s a second trust boundary. And it’s often left unguarded.**  


Retrieval-Augmented Generation works by fetching relevant documents from a knowledge base and injecting them into the LLM's context alongside the user's query. The architecture creates an implicit trust distinction that most security teams never question: user input is untrusted, but retrieved content is trusted. After all, it comes from your own knowledge base.

This assumption is the architectural flaw that makes RAG systems especially vulnerable. An attacker who can influence what enters your knowledge base (the corpus of documents your system retrieves from), whether through document uploads, data integrations, or compromised data pipelines, can inject malicious instructions that bypass every user-facing control you have deployed. The threat doesn't come through the front door you're guarding. It enters through the corpus you're trusting.

If you've been in security architecture discussions around RAG deployments, you've probably noticed a pattern: teams spend hours on input validation and prompt injection defenses, then wave through the document ingestion pipeline because "that's all internal data." It's a blind spot that keeps showing up, and it's exactly where the interesting attack surface is.

The RAG trust paradox: user inputs are validated while retrieved context is implicitly trusted

[](/images/blog/diagrams/rag-security-forgotten-attack-surface/trust-paradox.svg "Open larger image in new tab")

#### The attack math: five documents in millions

How efficient are these attacks in practice? According to [PoisonedRAG](https://www.usenix.org/conference/usenixsecurity25/presentation/zou-poisonedrag) (Zou et al.), research published at USENIX Security 2025 by researchers at Pennsylvania State University and Illinois Institute of Technology, just five carefully crafted documents targeting a specific query can manipulate AI responses with over 90% success, even in a knowledge base containing millions of documents.

This is not a broad compromise of the entire system. The attack is highly targeted and works only if two conditions are met. First, the malicious document must be semantically similar enough to the intended question that the retrieval component consistently selects it. Second, once included in the context, it must successfully steer the model toward the attacker’s desired answer. When both conditions are satisfied, a handful of poisoned documents is enough to reliably influence specific high-value queries.

The researchers also evaluated proposed defensive measures and found them inadequate, indicating that more fundamental architectural changes may be required.

#### Vector databases: built for speed, not adversaries

The 2025 revision of the OWASP Top 10 for LLM Applications introduced a new entry that security teams should study carefully: [LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/). This category recognizes that the infrastructure underlying RAG systems, specifically vector databases and embedding pipelines, introduces its own class of vulnerabilities.

Vector databases store documents as embeddings: high-dimensional numerical vectors that capture semantic meaning. When you embed a sentence, the resulting vector places it in a mathematical space where similar sentences cluster together. This is what makes retrieval work. It's also what makes these systems vulnerable.

Here's a structural mismatch I think the industry hasn’t fully addressed yet: vector databases were designed for similarity search at scale. They excel at finding documents that are semantically close to a query. They were not designed for adversarial environments where attackers actively try to manipulate what gets retrieved.

##### Embedding inversion: your vectors leak more than you think

One of the more concerning findings in recent research is that embeddings can be inverted to recover significant portions of the original text. Organizations often treat embeddings as a form of abstraction, assuming that the original content cannot be reconstructed from its vector representation. This assumption is wrong.

The threat model here requires an attacker to obtain access to the stored embeddings, whether through a database breach, insider access, a misconfigured API, or querying a vector store that lacks proper access controls. Once an attacker has the vectors, they can train a surrogate model to function as an "embedding decoder," essentially reversing the embedding process to reconstruct the original text.

According to research on [transferable embedding inversion attacks](https://aclanthology.org/2024.acl-long.230/) presented at ACL 2024, Huang et al. demonstrated that these attacks work even without direct access to the original embedding model. Building on earlier work that established the 50-70% recovery rate for original input words, their research showed that attackers can use surrogate models to infer content from vectors alone. Proper nouns, technical terms, and unique phrases are particularly vulnerable since they occupy distinctive regions of the embedding space.

For RAG systems that embed confidential documents, customer data, or internal communications, this means the vector database itself becomes a source of data leakage if compromised. Even if the original documents are protected behind access controls, an attacker who can steal or intercept the embeddings can decode a substantial portion of the original text content, including sensitive terms like names, account numbers, or proprietary information.

##### Multi-tenant isolation failures

In environments where multiple users or applications share a vector database, there is also risk of cross-context information leakage. If access controls are not properly implemented at the embedding and retrieval layer, queries from one user context might retrieve documents from another. According to OWASP's guidance, inadequate or misaligned access controls can lead to unauthorized access to embeddings containing sensitive information.

Consider a financial SaaS platform where each customer's documents are embedded in a shared vector store. A user from Company A asks an innocuous question about quarterly revenue projections. If the vectors aren't isolated by tenant, the similarity search might retrieve semantically related content from Company B's confidential financial documents, leaking B's revenue data to A's user. The query wasn't malicious; the architecture was.

The challenge is that traditional database access controls don’t map cleanly to vector similarity search. A query doesn’t request specific documents by ID; it requests documents similar to a query embedding. While many vector databases support multi-tenancy through namespaces, collections, or metadata filtering, they typically rely on application-level enforcement rather than built-in, policy-driven row-level security guarantees. In practice, this means teams either maintain separate vector indexes per tenant (with associated cost and operational complexity) or ensure every vector query is augmented with permission-aware metadata filters to enforce access boundaries. If you’ve ever tried to retrofit access controls onto a system that wasn’t designed for them, you know how many edge cases that creates.

#### When theory meets production

These aren't theoretical concerns. Researchers and security teams have demonstrated real-world exploitation of RAG vulnerabilities in production systems.

##### Slack AI: indirect prompt injection via public channels

In August 2024, security researchers disclosed a vulnerability in Slack AI that combined indirect prompt injection with Slack AI's RAG-style retrieval. Slack AI ingests messages from channels to provide AI-powered summaries and responses, and by design, public channel messages are searchable by all workspace members regardless of whether they've joined the channel.

The attack exploited this by posting a message containing malicious instructions in a public channel. When Slack AI retrieved that message as context for answering a user's query, the embedded instructions could trick the AI into constructing a phishing link that leaked data from the user's conversation context. The vulnerability was real, but its scope was narrower than it might sound: it required the attacker to already have an account in the same Slack workspace, and the public channel retrieval behavior was by design rather than a bug in access controls.

Slack [acknowledged the issue on August 20, 2024](https://slack.com/intl/de-de/blog/news/slack-security-update-082124) and deployed a patch the same day. In their advisory, they described it as a scenario where "under very limited and specific circumstances, a malicious actor with an existing account in the same Slack workspace could phish users for certain data." They reported no evidence of unauthorized access to customer data.

The interesting part here isn't the (non-)severity of this particular finding, it's the pattern: once an LLM retrieves attacker-influenced content as trusted context, prompt injection becomes the amplifier that turns a minor design decision into a data leakage path.

##### ChatGPT memory: persistent spyware via poisoned context

In September 2024, security researcher Johann Rehberger demonstrated [SpAIware](https://embracethered.com/blog/posts/2024/chatgpt-macos-app-persistent-data-exfiltration/), a technique for achieving persistent data exfiltration from ChatGPT by poisoning its memory feature. By tricking a user into visiting a malicious website or analyzing a maliciously crafted document, an attacker could inject instructions into ChatGPT's memory that persist across sessions, causing the AI to exfiltrate all future conversations to an attacker-controlled server.

_This attack represents a broader category of persistence vulnerabilities that I 'll explore in [my post on agentic memory poisoning](/blog/persistent-memory-poisoning-in-ai-agents/)._

#### Defense-in-depth for RAG systems

So what do you actually do about all of this? Securing RAG requires controls at three distinct layers: ingestion, retrieval, and generation. A failure at any single layer should not result in complete compromise.

Three-layer defense architecture for RAG systems

[](/images/blog/diagrams/rag-security-forgotten-attack-surface/defense-layers.svg "Open larger image in new tab")

##### Ingestion controls: treat documents like code

The knowledge base is now part of your attack surface. Every document that enters should be treated with the same suspicion you apply to user input.

**Provenance verification** means accepting data only from trusted and verified sources. Maintain an audit trail of what entered the knowledge base, when, and from where. If your RAG system ingests documents from external sources, data partnerships, or user uploads, you need validation pipelines that verify origin before embedding.

**Preprocessing for hidden instructions** involves scanning documents before embedding for patterns that look like prompt injection attempts. This includes phrases like _" ignore previous instructions,"_ _" you are now,"_ and similar command-like constructs — and those are just the obvious ones. Tools like Meta's open-source [PromptGuard](https://github.com/meta-llama/PurpleLlama/tree/main/Llama-Prompt-Guard-2) can help identify injection attempts in document content. Regex-based filters provide a first line of defense, but LLM-based classifiers catch more sophisticated attempts.

**Content integrity monitoring** requires regularly auditing the knowledge base for unexpected changes. Implement immutable logging of all modifications. If documents can be updated after initial ingestion, validate that updates come from authorized sources.

**Embedding encryption** treats vectors as sensitive data that warrant protection at rest and in transit. Many vector databases prioritize performance over security and don't encrypt embeddings by default, relying instead on application-layer security. If an attacker gains network access or a stolen API token, they could dump the entire embedding index and run inversion attacks offline. Encrypting embeddings at rest and enforcing TLS for all vector database connections raises the bar for data theft.

##### Retrieval controls: permission-aware search

The retrieval layer needs access controls that respect user context, not just query similarity.

**Permission-aware retrieval** ensures that when a user queries the RAG system, retrieved documents are filtered based on what that user is authorized to access. This requires propagating user identity and permissions into the retrieval process, not just the application layer.

**Tenant isolation** in multi-user environments means maintaining strict logical partitioning of datasets in the vector database. Different user groups or applications should not be able to retrieve each other's documents through similarity search.

**Retrieval anomaly detection** involves monitoring for queries that retrieve unusual combinations of documents, or documents that are retrieved with unusual frequency for specific query patterns. Poisoned documents often have distinctive retrieval signatures: they activate on narrow query ranges designed to match attacker-chosen targets.

**Query authentication and audit logging** ensures that every vector database query is authenticated and logged. Monitor for unusual bulk reads of embeddings, which could indicate an attacker preparing for inversion attacks or data exfiltration. Rate limiting on embedding retrieval can prevent mass extraction while allowing normal application queries.

##### Generation controls: guardrails and monitoring

Even with ingestion and retrieval controls, assume some malicious content may reach the generation phase.

**Context injection detection** monitors the assembled prompt for suspicious patterns before sending it to the LLM. The same kind of prompt injection classifiers used during ingestion (like the PromptGuard mentioned above) can also run here, this time scanning the fully assembled context rather than individual documents. The goal is to catch injection attempts that made it past the ingestion filters, for example because the malicious instruction only becomes apparent when combined with certain retrieved documents.

**Output monitoring** treats LLM outputs with suspicion when they contain unexpected elements: URLs, requests for sensitive information, instructions to perform actions, or content that deviates significantly from expected response patterns. For example, if an answer to _" What's our refund policy?"_ suddenly contains `https://attacker.example.com/?data=...` or asks the user to provide their password, that's a strong indicator of a successful injection. Automated scanning for URLs pointing to external domains, base64-encoded strings, or requests for credentials can catch exfiltration attempts before they reach the user.

**Retrieval attribution** maintains clear tracking of which documents contributed to each response. When anomalies are detected, you need the ability to trace back to the source documents and remove or quarantine them.

#### Takeaways

The trust paradox in RAG systems creates attack paths that bypass traditional input validation. Organizations deploying RAG need to recognize that their knowledge base is now part of their attack surface, not a trusted internal resource.

**Corpus poisoning is remarkably efficient.** Academic research demonstrates that five documents in millions can achieve 90%+ attack success rates. Attackers don't need to compromise your entire knowledge base to manipulate high-value responses.

**Vector databases introduce their own vulnerabilities.** Embedding inversion attacks can recover significant portions of original text from vectors. Multi-tenant environments risk cross-context leakage without permission-aware retrieval.

**Production systems have already been affected.** The Slack AI indirect prompt injection and the ChatGPT memory poisoning incidents show that these attack patterns aren't just academic. Even when individual findings are limited in scope, they illustrate how RAG-style retrieval can amplify otherwise minor issues.

**Defense requires three layers.** Ingestion controls treat documents like code. Retrieval controls enforce permissions at query time. Generation controls assume some malicious content will reach the LLM and detect it before or after generation.

> The weakness isn't the model — it's what you feed it. Treat your knowledge base as untrusted input.

  
  


##### _If this resonated..._

_I conduct[agentic AI security assessments](/consulting/agentic-ai-security/) for organizations deploying RAG pipelines and agentic systems, covering corpus poisoning, retrieval manipulation, and defense architecture. If you're building systems where the knowledge base is part of the attack surface, [get in touch](/contact/) to discuss defense-in-depth strategies tailored to your architecture._

##### Tags:

  * [genai](https://christian-schneider.net/tags/genai)
  * [llm](https://christian-schneider.net/tags/llm)
  * [rag](https://christian-schneider.net/tags/rag)



#### Support

 __##### [Agentic AI Security](https://christian-schneider.net/consulting/agentic-ai-security/)

 __##### [Custom Focus Session](https://christian-schneider.net/training/custom-focus-session/)

#### [Related Articles](/securing-agentic-ai/)[ RSS](https://christian-schneider.net/blog/index.xml "Subscribe to RSS feed")

 __##### [Closing the AI agent identity governance gap](https://christian-schneider.net/blog/non-human-identity-governance-gap-ai-agents/)

 __##### [Verifying agentic AI controls with attack tree micro simulations](https://christian-schneider.net/blog/verifying-agentic-ai-controls-attack-tree-micro-simulations/)

 __##### [Multimodal prompt injection: attacks in images, audio, and video](https://christian-schneider.net/blog/multimodal-prompt-injection/)

 __##### [AI agents as attack pivots: the new lateral movement](https://christian-schneider.net/blog/ai-agent-lateral-movement-attack-pivots/)

 __##### [Memory poisoning in AI agents: exploits that wait](https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents/)

 __##### [Securing MCP: a defense-first architecture guide](https://christian-schneider.net/blog/securing-mcp-defense-first-architecture/)

 __##### [Threat modeling agentic AI: a scenario-driven approach](https://christian-schneider.net/blog/threat-modeling-agentic-ai/)

 __##### [From LLM to agentic AI: prompt injection got worse](https://christian-schneider.net/blog/prompt-injection-agentic-amplification/)

[See more in blog ->](/blog/)

#### All Categories

  * [Best Practice](/categories/best-practice)
  * [Conference](/categories/conference)
  * [Vulnerability](/categories/vulnerability)



#### All Tags

  * [api](/tags/api)
  * [architecture](/tags/architecture)
  * [attack-tree](/tags/attack-tree)
  * [browser](/tags/browser)
  * [ci/cd](/tags/ci/cd)
  * [cloud](/tags/cloud)
  * [devops](/tags/devops)
  * [genai](/tags/genai)
  * [iam](/tags/iam)
  * [java](/tags/java)
  * [llm](/tags/llm)
  * [mcp](/tags/mcp)
  * [multimodal](/tags/multimodal)
  * [pentesting](/tags/pentesting)
  * [prompt-injection](/tags/prompt-injection)
  * [rag](/tags/rag)
  * [red-team](/tags/red-team)
  * [secure-sdlc](/tags/secure-sdlc)
  * [siem](/tags/siem)
  * [supply-chain](/tags/supply-chain)
  * [threat-modeling](/tags/threat-modeling)
  * [websocket](/tags/websocket)
  * [xml](/tags/xml)



[](/)

Christian Schneider  
Security Architect, Hacker, Trainer

#### Profile

  * [ __](https://github.com/cschneider4711)
  * [__](https://twitter.com/cschneider4711)
  * [__](https://de.linkedin.com/in/cschneider4711)
  * [__](https://www.xing.com/profile/Christian_Schneider248)



#### Membership

[OWASP – Open Worldwide Application Security Project](https://www.owasp.org/)  
[CCC – Chaos Computer Club](https://ccc.de/)  
[Allianz für Cybersicherheit](https://www.allianz-fuer-cybersicherheit.de/)  



#### Contact

[+49 178 3081340](tel:+49%20178%203081340)  
[mail@christian-schneider.net](mailto:mail@christian-schneider.net)  
Herbert-Lewin-Str. 3, 50931 Köln, Germany  


#### Info

PGP-Key: [2898B0BE](https://christian-schneider.net/pgp-key.asc)  
Insured during project assignments: [Exali IT Insurance](https://christian-schneider.net/insurance.pdf)  
Tracking: Nope, visiting my website is cookieless

#### Newsletter

Low-volume newsletter to announce new trainings, services, and conference talks

Subscribe

#### [Service](https://christian-schneider.net/service/)

  * [Application Pentest](https://christian-schneider.net/service/application-pentest/)
  * [API Security Check](https://christian-schneider.net/service/api-security-check/)
  * [Attack Surface Mapping](https://christian-schneider.net/service/attack-surface-mapping/)
  * [Container Platform Review](https://christian-schneider.net/service/container-platform-review/)
  * [Cloud Security Check](https://christian-schneider.net/service/cloud-security-check/)
  * [Secure SDLC Process Review](https://christian-schneider.net/service/secure-sdlc-process-review/)



#### [Consulting](https://christian-schneider.net/consulting/)

  * [Agile Threat Modeling](https://christian-schneider.net/consulting/agile-threat-modeling/)
  * [Attack Tree Quickstart](https://christian-schneider.net/consulting/attacktree-quickstart/)
  * [Agentic AI Security](https://christian-schneider.net/consulting/agentic-ai-security/)
  * [Coding Agent Security](https://christian-schneider.net/consulting/coding-agent-security/)
  * [Security Sparring Partner](https://christian-schneider.net/consulting/security-sparring-partner/)
  * [Security Architecture](https://christian-schneider.net/consulting/security-architecture/)
  * [DevSecOps Pipeline](https://christian-schneider.net/consulting/devsecops-pipeline/)



#### [Training](https://christian-schneider.net/training/)

  * [Web Security Bootcamp](https://christian-schneider.net/training/web-security-bootcamp/)
  * [Review & Reflect](https://christian-schneider.net/training/review-and-reflect/)
  * [Custom Focus Session](https://christian-schneider.net/training/custom-focus-session/)
  * [Pentesting Training](https://christian-schneider.net/training/pentesting-training/)
  * [Live Hacking Event](https://christian-schneider.net/training/live-hacking-event/)



#### [Development](https://christian-schneider.net/development/)

  * [Attack Tree](/development/attacktree-free-saas)
  * [Threagile](/development/threagile-support-subscription)
  * [Workshop Board](/development/workshopboard-free-saas)



Copyright (C) 2026 by Christian Schneider

  * [Imprint & Disclaimer](/disclaimer/)


