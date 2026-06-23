<!-- Source: https://docs.trychroma.com/cloud/schema/sparse-vector-search | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

> ## Documentation Index
> 
> Fetch the complete documentation index at: [/llms.txt](/llms.txt)
> 
> Use this file to discover all available pages before exploring further.

Skip to main content

[Chroma Docs home page](/)

Search...

⌘KAsk Assistant

  * [27k](https://github.com/chroma-core/chroma)
  * [11k](https://discord.gg/dSHcBEMSk7)
  * [29k](https://x.com/trychroma)
  * [Dashboard](https://trychroma.com/login)
  * [Dashboard](https://trychroma.com/login)



Search...

Navigation

Schema

Sparse Vector Search Setup

[Docs](/docs/overview/introduction)[Chroma Cloud](/cloud/getting-started)[Guides](/guides/build/building-with-ai)[Integrations](/integrations/chroma-integrations)[Reference](/reference/overview)



  * [Getting Started](/cloud/getting-started)


  * [Pricing](/cloud/pricing)


  * [Quotas & Limits](/cloud/quotas-limits)



### Features

  * [Collection Forking](/cloud/features/collection-forking)



### Schema

  * [Schema Overview](/cloud/schema/overview)
  * [Schema Basics](/cloud/schema/schema-basics)
  * [Sparse Vector Search Setup](/cloud/schema/sparse-vector-search)
  * [Index Configuration Reference](/cloud/schema/index-reference)



### Search API

  * [Overview](/cloud/search-api/overview)
  * [Search Basics](/cloud/search-api/search-basics)
  * [Filtering with Where](/cloud/search-api/filtering)
  * [Ranking and Scoring](/cloud/search-api/ranking)
  * [Group By & Aggregation](/cloud/search-api/group-by)
  * [Hybrid Search with RRF](/cloud/search-api/hybrid-search)
  * [Pagination & Selection](/cloud/search-api/pagination-selection)
  * [Batch Operations](/cloud/search-api/batch-operations)
  * [Examples & Patterns](/cloud/search-api/examples)
  * [Migration Guide](/cloud/search-api/migration)



### Sync

  * [Overview](/cloud/sync/overview)
  * [S3 Sync](/cloud/sync/s3)
  * [GitHub](/cloud/sync/github)
  * [Web Sync](/cloud/sync/web)
  * [File Upload](/cloud/sync/file-upload)



### Package Search

  * [MCP](/cloud/package-search/mcp)
  * [Registry](/cloud/package-search/registry)



## On this page

  * What are Sparse Vectors?
  * Enabling Sparse Vector Index
  * Create Collection and Add Data
    * Create Collection with Schema
    * Add Data
  * Using Sparse Vectors for Search
    * Sparse Vector Search
  * Hybrid Search
    * Benefits of Hybrid Search
    * Combining Dense and Sparse with RRF
  * Next Steps



Schema

# Sparse Vector Search Setup

Copy page

Learn how to configure and use sparse vectors for keyword-based search, and combine them with dense embeddings for powerful hybrid search capabilities.

Copy page

## 

​

What are Sparse Vectors?

Sparse vectors are high-dimensional vectors with mostly zero values, designed for keyword-based retrieval. Unlike dense embeddings which capture semantic meaning, sparse vectors excel at:

  * **Exact keyword matching** : Finding documents containing specific terms
  * **Domain-specific terminology** : Better at matching technical terms, proper nouns, and rare words
  * **Lexical retrieval** : BM25-style retrieval patterns

Sparse vectors use models like SPLADE that assign importance weights to specific tokens, making them complementary to dense semantic embeddings.

## 

​

Enabling Sparse Vector Index

To use sparse vectors, add a sparse vector index to your schema. The `key` parameter is the metadata field name where sparse embeddings will be stored - you can name it whatever you want:

Python

TypeScript
    
    
    from chromadb import Schema, SparseVectorIndexConfig, K
    from chromadb.utils.embedding_functions import ChromaCloudSpladeEmbeddingFunction
    
    schema = Schema()
    
    # Add sparse vector index for keyword-based search
    # "sparse_embedding" is just a metadata key name - use any name you prefer
    sparse_ef = ChromaCloudSpladeEmbeddingFunction()
    schema.create_index(
        config=SparseVectorIndexConfig(
            source_key=K.DOCUMENT,
            embedding_function=sparse_ef
        ),
        key="sparse_embedding"
    )
    

The `source_key` specifies which field to generate sparse embeddings from (typically `K.DOCUMENT` for document text), and `embedding_function` specifies the function to generate the sparse embeddings. This example uses `ChromaCloudSpladeEmbeddingFunction`, but you can also use other sparse embedding functions like `HuggingFaceSparseEmbeddingFunction` or `FastembedSparseEmbeddingFunction`. The sparse embeddings are automatically generated and stored in the metadata field you specify as the `key`.

## 

​

Create Collection and Add Data

### 

​

Create Collection with Schema

Python

TypeScript
    
    
    import chromadb
    
    client = chromadb.CloudClient(
        tenant="your-tenant",
        database="your-database",
        api_key="your-api-key"
    )
    
    collection = client.create_collection(
        name="hybrid_search_collection",
        schema=schema
    )
    

### 

​

Add Data

When you add documents, sparse embeddings are automatically generated from the source key:

Python

TypeScript
    
    
    collection.add(
        ids=["doc1", "doc2", "doc3"],
        documents=[
            "The quick brown fox jumps over the lazy dog",
            "A fast auburn fox leaps over a sleepy canine",
            "Machine learning is a subset of artificial intelligence"
        ],
        metadatas=[
            {"category": "animals"},
            {"category": "animals"},
            {"category": "technology"}
        ]
    )
    
    # Sparse embeddings for "sparse_embedding" are generated automatically
    # from the documents (source_key=K.DOCUMENT)
    

## 

​

Using Sparse Vectors for Search

Once configured, you can search using sparse vectors alone or combine them with dense embeddings for hybrid search.

### 

​

Sparse Vector Search

Use sparse vectors for keyword-based retrieval:

Python

TypeScript
    
    
    from chromadb import Search, K, Knn
    
    # Search using sparse embeddings only
    sparse_rank = Knn(query="fox animal", key="sparse_embedding")
    
    # Build and execute search
    search = (Search()
        .rank(sparse_rank)
        .limit(10)
        .select(K.DOCUMENT, K.SCORE))
    
    results = collection.search(search)
    
    # Process results
    for row in results.rows()[0]:
        print(f"Score: {row['score']:.3f} - {row['document']}")
    

## 

​

Hybrid Search

Hybrid search combines dense semantic embeddings with sparse keyword embeddings for improved retrieval quality. By merging results from both approaches using Reciprocal Rank Fusion (RRF), you often achieve better results than either approach alone.

### 

​

Benefits of Hybrid Search

  * **Semantic + Lexical** : Dense embeddings capture meaning while sparse vectors catch exact keywords
  * **Improved recall** : Finds relevant documents that either semantic or keyword search might miss alone
  * **Balanced results** : Combines the strengths of both retrieval methods



### 

​

Combining Dense and Sparse with RRF

Use RRF (Reciprocal Rank Fusion) to merge dense and sparse search results:

Python

TypeScript
    
    
    from chromadb import Search, K, Knn, Rrf
    
    # Create RRF ranking combining dense and sparse embeddings
    hybrid_rank = Rrf(
        ranks=[
            Knn(query="fox animal", return_rank=True),           # Dense semantic search
            Knn(query="fox animal", key="sparse_embedding", return_rank=True)  # Sparse keyword search
        ],
        weights=[0.7, 0.3],  # 70% semantic, 30% keyword
        k=60
    )
    
    # Build and execute search
    search = (Search()
        .rank(hybrid_rank)
        .limit(10)
        .select(K.DOCUMENT, K.SCORE))
    
    results = collection.search(search)
    
    # Process results
    for row in results.rows()[0]:
        print(f"Score: {row['score']:.3f} - {row['document']}")
    

For comprehensive details on RRF parameters, weight tuning, and advanced hybrid search strategies, see the [Search API Hybrid Search documentation](../search-api/hybrid-search).

## 

​

Next Steps

  * **[Search API Hybrid Search with RRF](../search-api/hybrid-search)** \- Learn RRF parameters, weight tuning, and advanced strategies
  * [Index Configuration Reference](./index-reference) \- Detailed parameters for all index types
  * [Schema Basics](./schema-basics) \- General Schema usage and patterns



Was this page helpful?

YesNo

[Suggest edits](https://github.com/chroma-core/chroma/edit/main/docs/mintlify/cloud/schema/sparse-vector-search.mdx)

[Schema BasicsPrevious](/cloud/schema/schema-basics)[Index Configuration ReferenceNext](/cloud/schema/index-reference)

⌘I

[Chroma Docs home page](/)

[github](https://github.com/chroma-core/chroma)[x](https://x.com/trychroma)[discord](https://discord.gg/MMeYNTmh3x)[youtube](https://youtube.com/@trychroma)

[Enterprise](https://trychroma.com/enterprise)[Pricing](https://trychroma.com/pricing)[Changelog](https://trychroma.com/changelog)

[github](https://github.com/chroma-core/chroma)[x](https://x.com/trychroma)[discord](https://discord.gg/MMeYNTmh3x)[youtube](https://youtube.com/@trychroma)

[github](https://github.com/chroma-core/chroma)[x](https://x.com/trychroma)[discord](https://discord.gg/MMeYNTmh3x)[youtube](https://youtube.com/@trychroma)

Assistant

Responses are generated using AI and may contain mistakes.

[Contact support](mailto:support@trychroma.com)
