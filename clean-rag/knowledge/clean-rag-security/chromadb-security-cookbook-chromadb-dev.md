<!-- Source: https://cookbook.chromadb.dev/security/ | Tier: A | Topic: chromadb-security | Fetched: 2026-06-26 -->

Skip to content 

[ ](/ "Chroma Cookbook")

Chroma Cookbook 

Security 

Initializing search 




[ GitHub  ](https://github.com/amikos-tech/chroma-cookbook "Go to repository")

[ ](/ "Chroma Cookbook") Chroma Cookbook 

[ GitHub  ](https://github.com/amikos-tech/chroma-cookbook "Go to repository")

  * [ Home  ](..)
  * [ Core  ](../core/)

Core 
    * [ Chroma API  ](../core/api/)
    * [ Chroma Clients  ](../core/clients/)
    * [ Collections  ](../core/collections/)
    * [ Concepts  ](../core/concepts/)
    * [ Configuration  ](../core/configuration/)
    * [ Document IDs  ](../core/document-ids/)
    * [ Filters  ](../core/filters/)
    * [ Installation  ](../core/install/)
    * [ Resource Requirements  ](../core/resources/)
    * [ Storage Layout  ](../core/storage-layout/)
    * [ Chroma System Constraints  ](../core/system_constraints/)
    * [ Tenants and Databases  ](../core/tenants-and-databases/)
    * Advanced  Advanced 
      * [ Chroma Queries  ](../core/advanced/queries/)
      * [ Write-ahead Log (WAL) Pruning  ](../core/advanced/wal-pruning/)
      * [ Write-ahead Log (WAL)  ](../core/advanced/wal/)
  * Running  Running 
    * [ Running Chroma  ](../running/running-chroma/)
    * [ Deployment Patterns  ](../running/deployment-patterns/)
    * [ Road To Production  ](../running/road-to-prod/)
    * [ Health Checks  ](../running/health-checks/)
    * [ Performance Tips  ](../running/performance-tips/)
    * [ Maintenance  ](../running/maintenance/)
    * [ Systemd service  ](../running/systemd-service/)
  * Embedding  Embedding 
    * [ Creating your own embedding function  ](../embeddings/bring-your-own-embeddings/)
    * [ Cross-Encoders Reranking  ](../embeddings/cross-encoders/)
    * [ Embedding Models  ](../embeddings/embedding-models/)
    * [ Embedding Functions GPU Support  ](../embeddings/gpu-support/)
  * Integrations  Integrations 
    * [ Langchain  ](../integrations/langchain/)

Langchain 
      * [ LangChain Embeddings  ](../integrations/langchain/embeddings/)
      * [ 🦜⛓️ Langchain Retriever  ](../integrations/langchain/retrievers/)
    * [ Llamaindex  ](../integrations/llamaindex/)

Llamaindex 
      * [ LlamaIndex Embeddings  ](../integrations/llamaindex/embeddings/)
    * [ Ollama  ](../integrations/ollama/)

Ollama 
      * [ Ollama  ](../integrations/ollama/embeddings/)
  * Strategies  Strategies 
    * [ ChromaDB Backups  ](../strategies/backup/)
    * [ Batching  ](../strategies/batching/)
    * [ CORS Configuration for Browser-Based Access  ](../strategies/cors/)
    * [ Go Local Markdown CLI with PersistentClient  ](../strategies/go-local-markdown-cli/)
    * [ Image Search (Multimodal Retrieval)  ](../strategies/image-search/)
    * [ Keyword Search  ](../strategies/keyword-search/)
    * [ Metadata Schema Validation (Application Layer)  ](../strategies/metadata-schema-validation/)
    * [ Memory Management  ](../strategies/memory-management/)
    * [ Multi-Category/Tag Filters  ](../strategies/multi-category-filters/)
    * [ Privacy Strategies  ](../strategies/privacy/)
    * [ Rebuilding Chroma DB  ](../strategies/rebuilding/)
    * [ Time-based Queries  ](../strategies/time-based-queries/)
    * [ Multi-Tenancy  ](../strategies/multi-tenancy/)

Multi-Tenancy 
      * [ Implementing OpenFGA Authorization Model In Chroma  ](../strategies/multi-tenancy/authorization-model-impl-with-openfga/)
      * [ Chroma Authorization Model with OpenFGA  ](../strategies/multi-tenancy/authorization-model-with-openfga/)
      * [ Multi-User Basic Auth  ](../strategies/multi-tenancy/multi-user-basic-auth/)
      * [ Naive Multi-tenancy Strategies  ](../strategies/multi-tenancy/naive-multi-tenancy/)
  * [ Security  ](./)

Security 
    * [ Authentication in Chroma v1.0.x  ](auth-1.0.x/)
    * [ SSL/TLS Certificates in Chroma  ](chroma-ssl-cert/)
    * [ Chroma-native Auth (Legacy)  ](legacy-auth/)
    * [ SSL/TLS Proxy  ](ssl-proxies/)
  * Ecosystem  Ecosystem 
    * [ Chroma Ecosystem Clients  ](../ecosystem/clients/)
  * Contributing  Contributing 
    * [ Getting Started with Contributing to Chroma  ](../contributing/getting-started/)
    * [ Useful Shortcuts for Contributors  ](../contributing/useful-shortcuts/)
  * [ FAQ  ](../faq/)

FAQ 



On this page 

  * SSL/TLS Certificates 
  * Authentication and Authorization 



# Security¶

Security is an important topic and this section is devoted to it.

There are many ways to secure a service, such as Chroma and this section attempts to encompass the most common use cases.

Way to secure Chroma include:

  * In-transit encryption using SSL/TLS certificates
  * Access control
  * At-rest encryption
  * Adding authentication and authorization



## SSL/TLS Certificates¶

Securing your Chroma with a proxy is one of the most common ways to secure your Chroma. Ensuring that all traffic between your client and Chroma server is encrypted is a good practice.

There are multiple ways to secure your Chroma instance using SSL/TLS certificates and here we'll explore a few.

  * [SSL/TLS certificate in Chroma server](chroma-ssl-cert/) \- configure and use SSL/TLS certificates directly in Chroma.
  * [Proxy with SSL/TLS termination](ssl-proxies/) \- use a proxy to terminate SSL/TLS and forward traffic to Chroma.
  * (Coming soon) Cloud Provider API Gateway with SSL/TLS termination - use a cloud provider's API Gateway to terminate SSL/TLS and forward traffic to Chroma.



## Authentication and Authorization¶

Version prior to 1.0.x support [legacy authentication and authorization](legacy-auth/) \- Configure Chroma built-in authentication and authorization.

Versions 1.0.0-1.0.10 do not support Authentication or Authorization natively so you will need to adjust your deployment with a [proxy-based authentcation](auth-1.0.x/).

May 28, 2025

Amikos Tech LTD, 2025 (Chroma contributors) 

Made with [ Material for MkDocs ](https://squidfunk.github.io/mkdocs-material/)

[ ](https://twitter.com/AmikosTech "Amikos on Twitter") [ ](https://github.com/amikos-tech "Amikos on GitHub") [ ](https://medium.com/@amikostech "Amikos on Medium")

#### Cookie consent

We use cookies for analytics purposes. By continuing to use this website, you agree to their use.

  * Google Analytics 
  * GitHub 



Accept Manage settings
