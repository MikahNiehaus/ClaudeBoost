<!-- Source: https://arxiv.org/html/2404.01037v1 | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

  1. [1 Introduction](https://arxiv.org/html/2404.01037v1#S1 "In ARAGOG: Advanced RAG Output Grading")
  2. [2 RAG Techniques](https://arxiv.org/html/2404.01037v1#S2 "In ARAGOG: Advanced RAG Output Grading")
     1. [2.1 Sentence-window retrieval](https://arxiv.org/html/2404.01037v1#S2.SS1 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
     2. [2.2 Document summary index](https://arxiv.org/html/2404.01037v1#S2.SS2 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
     3. [2.3 HyDE](https://arxiv.org/html/2404.01037v1#S2.SS3 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
     4. [2.4 Multi-query](https://arxiv.org/html/2404.01037v1#S2.SS4 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
     5. [2.5 Maximum Marginal Relevance](https://arxiv.org/html/2404.01037v1#S2.SS5 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
     6. [2.6 Cohere Rerank](https://arxiv.org/html/2404.01037v1#S2.SS6 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
     7. [2.7 LLM rerank](https://arxiv.org/html/2404.01037v1#S2.SS7 "In 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading")
  3. [3 Methods](https://arxiv.org/html/2404.01037v1#S3 "In ARAGOG: Advanced RAG Output Grading")
     1. [3.1 Data](https://arxiv.org/html/2404.01037v1#S3.SS1 "In 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
        1. [3.1.1 RAG Database Construction](https://arxiv.org/html/2404.01037v1#S3.SS1.SSS1 "In 3.1 Data ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
        2. [3.1.2 Chunking Approach](https://arxiv.org/html/2404.01037v1#S3.SS1.SSS2 "In 3.1 Data ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
        3. [3.1.3 Evaluation Data Preparation](https://arxiv.org/html/2404.01037v1#S3.SS1.SSS3 "In 3.1 Data ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
     2. [3.2 Mitigating LLM Output Variability](https://arxiv.org/html/2404.01037v1#S3.SS2 "In 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
     3. [3.3 Metrics](https://arxiv.org/html/2404.01037v1#S3.SS3 "In 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
        1. [3.3.1 Retrieval Precision](https://arxiv.org/html/2404.01037v1#S3.SS3.SSS1 "In 3.3 Metrics ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
        2. [3.3.2 Answer Similarity](https://arxiv.org/html/2404.01037v1#S3.SS3.SSS2 "In 3.3 Metrics ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
        3. [3.3.3 Rationale for Metric Selection](https://arxiv.org/html/2404.01037v1#S3.SS3.SSS3 "In 3.3 Metrics ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
     4. [3.4 LLM](https://arxiv.org/html/2404.01037v1#S3.SS4 "In 3 Methods ‣ ARAGOG: Advanced RAG Output Grading")
  4. [4 Results](https://arxiv.org/html/2404.01037v1#S4 "In ARAGOG: Advanced RAG Output Grading")
     1. [4.1 Comparative Performance Analysis: Boxplots](https://arxiv.org/html/2404.01037v1#S4.SS1 "In 4 Results ‣ ARAGOG: Advanced RAG Output Grading")
     2. [4.2 Statistical Validation of Differences](https://arxiv.org/html/2404.01037v1#S4.SS2 "In 4 Results ‣ ARAGOG: Advanced RAG Output Grading")
        1. [4.2.1 Classic VDB](https://arxiv.org/html/2404.01037v1#S4.SS2.SSS1 "In 4.2 Statistical Validation of Differences ‣ 4 Results ‣ ARAGOG: Advanced RAG Output Grading")
        2. [4.2.2 Sentence window](https://arxiv.org/html/2404.01037v1#S4.SS2.SSS2 "In 4.2 Statistical Validation of Differences ‣ 4 Results ‣ ARAGOG: Advanced RAG Output Grading")
        3. [4.2.3 Document Summary Index](https://arxiv.org/html/2404.01037v1#S4.SS2.SSS3 "In 4.2 Statistical Validation of Differences ‣ 4 Results ‣ ARAGOG: Advanced RAG Output Grading")
  5. [5 Limitations](https://arxiv.org/html/2404.01037v1#S5 "In ARAGOG: Advanced RAG Output Grading")
  6. [6 Conclusion](https://arxiv.org/html/2404.01037v1#S6 "In ARAGOG: Advanced RAG Output Grading")
  7. [7 Future Work](https://arxiv.org/html/2404.01037v1#S7 "In ARAGOG: Advanced RAG Output Grading")



# ARAGOG: Advanced RAG Output Grading

Matouš Eibich   
Predli   
[matous@predli.com](matous@predli.com) Shivay Nagpal   
Predli   
[shivay@predli.com](shivay@predli.com) Alexander Fred-Ojala   
Predli & UC Berkeley   
[afo@berkeley.edu](afo@berkeley.edu)

###### Abstract

Retrieval-Augmented Generation (RAG) is essential for integrating external knowledge into Large Language Model (LLM) outputs. While the literature on RAG is growing, it primarily focuses on systematic reviews and comparisons of new state-of-the-art (SoTA) techniques against their predecessors, with a gap in extensive experimental comparisons. This study begins to address this gap by assessing various RAG methods’ impacts on retrieval precision and answer similarity. We found that Hypothetical Document Embedding (HyDE) and LLM reranking significantly enhance retrieval precision. However, Maximal Marginal Relevance (MMR) and Cohere rerank did not exhibit notable advantages over a baseline Naive RAG system, and Multi-query approaches underperformed. Sentence Window Retrieval emerged as the most effective for retrieval precision, despite its variable performance on answer similarity. The study confirms the potential of the Document Summary Index as a competent retrieval approach. All resources related to this research are publicly accessible for further investigation through our GitHub repository [ARAGOG](https://github.com/predlico/ARAGOG). We welcome the community to further this exploratory study in RAG systems.

##  1 Introduction

Large Language Models (LLMs) have significantly advanced the field of natural language processing, enabling a wide range of applications from text generation to question answering. However, integrating dynamic, external information remains a challenge for these models. Retrieval Augmented Generation (RAG) techniques address this limitation by incorporating external knowledge sources into the generation process, thus enhancing the models’ ability to produce contextually relevant and informed outputs. This integration of retrieval mechanisms with generative models is a key development in improving the performance and versatility of LLMs, facilitating more accurate and context-aware responses. See Figure [1](https://arxiv.org/html/2404.01037v1#S1.F1 "Figure 1 ‣ 1 Introduction ‣ ARAGOG: Advanced RAG Output Grading") for an overview of the standard RAG workflow.

Despite the growing interest in RAG techniques within the domain of LLMs, the existing body of literature primarily consists of systematic reviews (Gao et al., [2024](https://arxiv.org/html/2404.01037v1#bib.bib7)) and direct comparisons between successive state-of-the-art (SoTA) models (Gao et al., [2022](https://arxiv.org/html/2404.01037v1#bib.bib6), Jiang et al., [2023](https://arxiv.org/html/2404.01037v1#bib.bib9)). This pattern reveals a notable gap: a comprehensive experimental comparison across a broad spectrum of advanced RAG techniques is missing. Such a comparison is crucial for understanding the relative strengths and weaknesses of these techniques in enhancing LLMs’ performance across various tasks. This study seeks to contribute to bridging this gap by providing an extensive evaluation of multiple RAG techniques and their combinations, thereby offering insights into their efficacy and applicability in real-world scenarios.

The focus of this investigation is a spectrum of advanced RAG techniques aimed at optimizing the retrieval process. These techniques can be categorized into several areas:

RAG Technique | Type  
---|---  
Sentence-window retrieval | Decoupling of Retrieval and Generation  
Document summary index  
HyDE | Query Expansion  
Multi-query  
Maximal Marginal Relevance (MMR) | Enhancement Mechanism  
Cohere Re-ranker | Re-rankers  
LLM-based Re-ranker  
  
To evaluate the RAG techniques, this study leverages two metrics: Retrieval Precision and Answer Similarity (Tonic AI, [2023](https://arxiv.org/html/2404.01037v1#bib.bib20)). Retrieval Precision measures the relevance of the retrieved context to the question asked, while Answer Similarity assesses how closely the system’s answers align with reference responses, on a scale from 0 to 5.

Figure 1: A high-level overview of the workflow within a Retrieval-Augmented Generation (RAG) system. This process diagram shows how a user query is processed by the system to retrieve relevant documents from a database and how these documents inform the generation of a response.

##  2 RAG Techniques

###  2.1 Sentence-window retrieval

The Sentence-window Retrieval technique is grounded in the principle of optimizing both retrieval and generation processes by tailoring the text chunk size to the specific needs of each stage (Yang, [2023](https://arxiv.org/html/2404.01037v1#bib.bib21)). For retrieval, this technique emphasizes single sentences to take advantage of small data chunks for potentially better retrieving capabilities. On the generation side, it adds more sentences around the initial one to offer the LLM extended context, aiming for richer, more detailed outputs. This decoupling is supposed to increase the performance of both retrieval and generation, ultimately leading to better performance of the whole RAG system.

###  2.2 Document summary index

The Document Summary Index method enhances RAG systems by indexing document summaries for efficient retrieval, while providing LLMs with full text documents for response generation (Liu, [2023a](https://arxiv.org/html/2404.01037v1#bib.bib12)). This decoupling strategy optimizes retrieval speed and accuracy through summary-based indexing and supports comprehensive response synthesis by utilizing the original text.

###  2.3 HyDE

The Hypothetical Document Embedding (Gao et al., [2022](https://arxiv.org/html/2404.01037v1#bib.bib6)) technique enhances the document retrieval by leveraging LLMs to generate a hypothetical answer to a query. HyDE capitalizes on the ability of LLMs to produce context-rich answers, which, once embedded, serve as a powerful tool to refine and focus document retrieval efforts. See Figure [2](https://arxiv.org/html/2404.01037v1#S2.F2 "Figure 2 ‣ 2.3 HyDE ‣ 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading") for overview of HyDE RAG system workflow.

Figure 2: The process flow of Hypothetical Document Embedding (HyDE) technique within a Retrieval-Augmented Generation system. The diagram illustrates the steps from the initial query input to the generation of a hypothetical answer and its use in retrieving relevant documents to inform the final generated response.

###  2.4 Multi-query

The Multi-query technique (Langchain, [2023](https://arxiv.org/html/2404.01037v1#bib.bib11)) enhances document retrieval by expanding a single user query into multiple similar queries with the assistance of an LLM. This process involves generating N alternative questions that echo the intent of the original query but from different angles, thereby capturing a broader spectrum of potential answers. Each query, including the original, is then vectorized and subjected to its own retrieval process, which increases the chances of fetching a higher volume of relevant information from the document repository. To manage the resultant expanded dataset, a re-ranker is often employed, utilizing machine learning models to sift through the retrieved chunks and prioritize those most relevant in regards to the initial query. See Figure [3](https://arxiv.org/html/2404.01037v1#S2.F3 "Figure 3 ‣ 2.4 Multi-query ‣ 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading") for an overview of how Multi-query RAG system workflow.

Figure 3: This diagram showcases how multiple similar queries are generated from an initial user query, and how they contribute to retrieving a wider range of relevant documents.

###  2.5 Maximum Marginal Relevance

The Maximal Marginal Relevance (MMR) technique (Carbonell and Goldstein, [1998](https://arxiv.org/html/2404.01037v1#bib.bib3)) aims to refine the retrieval process by striking a balance between relevance and diversity in the documents retrieved. By employing MMR, the retrieval system evaluates potential documents not only for their closeness to the query’s intent but also for their uniqueness compared to documents already selected. This approach mitigates the issue of redundancy, ensuring that the set of retrieved documents covers a broader range of information.

###  2.6 Cohere Rerank

Rerankers aim to enhance the RAG process by refining the selection of documents retrieved in response to a query, with the goal of prioritizing the most relevant and contextually appropriate information for generating responses (Pinecone, [2023](https://arxiv.org/html/2404.01037v1#bib.bib17)). This step employs ML algorithms (such as cross-encoder) to reassess the initially retrieved set, using criteria that extend beyond cosine similarity. Through this evaluation, rerankers are expected to improve the input for generative models, potentially leading to more accurate and contextually rich outputs. See Figure [4](https://arxiv.org/html/2404.01037v1#S2.F4 "Figure 4 ‣ 2.6 Cohere Rerank ‣ 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading") for an overview of the Reranker RAG system workflow.

One tool in this domain is Cohere rerank, which uses a cross-encoder architecture to assess the relevance of documents to the query. This approach differs from methods that process queries and documents separately, as cross-encoders analyze them jointly, which could allow for a more comprehensive understanding of their mutual relevance.

Figure 4: This flowchart outlines the reranking process in a RAG system. It illustrates how retrieved documents are further assessed for relevance using a reranking step, which refines the set of documents that will inform the generated response.

###  2.7 LLM rerank

Following the introduction of cross-encoder based rerankers such as Cohere rerank, the LLM reranker offers an alternative strategy by directly applying LLMs to the task of reranking retrieved documents (Liu, [2023b](https://arxiv.org/html/2404.01037v1#bib.bib13)). This method prioritizes the comprehensive analytical abilities of LLMs over the joint query-document analysis typical of cross-encoders. Although less efficient in terms of processing speed and cost compared to cross-encoder models, LLM rerankers can achieve higher accuracy by leveraging the advanced understanding of language and context inherent in LLMs. This makes the LLM reranker suitable for applications where the quality of the reranked results is more critical than computational efficiency. Figure [4](https://arxiv.org/html/2404.01037v1#S2.F4 "Figure 4 ‣ 2.6 Cohere Rerank ‣ 2 RAG Techniques ‣ ARAGOG: Advanced RAG Output Grading") workflow applies to LLM reranker as well.

##  3 Methods

###  3.1 Data

This study utilizes a tailored dataset derived from the AI ArXiv collection, accessible via Hugging Face (James Calam, [2023](https://arxiv.org/html/2404.01037v1#bib.bib8)). The dataset consists of 423 selected research papers centered around the themes of AI and LLMs, sourced from arXiv. This selection offers a comprehensive foundation for constructing a database to test the RAG techniques and creating a set of evaluation data to assess their effectiveness.

####  3.1.1 RAG Database Construction

For the study, a subset of 13 key research papers was selected for their potential to generate specific, technical questions suitable for evaluating Retrieval-Augmented Generation (RAG) systems. Among the selected papers were significant contributions such as RoBERTa: A Robustly Optimized BERT Pretraining Approach (Liu et al., [2019](https://arxiv.org/html/2404.01037v1#bib.bib14)) and BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding (Devlin et al., [2019](https://arxiv.org/html/2404.01037v1#bib.bib5)). To better simulate a real-world vector database environment, where noise and irrelevant documents are present, the database was expanded to include the full dataset of 423 papers available. The additional 410 papers act as noise, enhancing the complexity and diversity of the retrieval challenges faced by the RAG system.

####  3.1.2 Chunking Approach

Multiple chunking strategies were utilized to create vector databases for different retrieval methods. For the classic vector database, a [TokenTextSplitter](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/token_text_splitter/) was employed with a chunk size of 512 tokens and an overlap of 50 tokens. This approach split the documents into smaller chunks while maintaining context by allowing for overlapping text between chunks. For the sentence window method, a [SentenceWindowNodeParser](https://docs.llamaindex.ai/en/stable/examples/node_postprocessor/MetadataReplacementDemo/) was used with a window size of 3 sentences, effectively creating overlapping chunks consisting of three consecutive sentences. Lastly, for the document summary index, a [TokenTextSplitter](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/token_text_splitter/) was employed with a larger chunk size of 3072 tokens and an overlap of 100 tokens, generating larger chunks to be summarized by the language model.

####  3.1.3 Evaluation Data Preparation

The evaluation dataset comprises 107 question-answer (QA) pairs generated with the assistance of GPT-4. The generation process was guided by specific criteria to ensure that the questions were challenging, technically precise, and reflective of potential user inquiries sent to a RAG system. Each QA pair was then reviewed by humans to validate its relevance and accuracy, ensuring that the evaluation data accurately measures the RAG techniques’ performance in real-world applications. The QA dataset is available in this paper’s associated Github repository [ARAGOG](https://github.com/predlico/ARAGOG). See Figure [5](https://arxiv.org/html/2404.01037v1#S3.F5 "Figure 5 ‣ 3.1.3 Evaluation Data Preparation ‣ 3.1 Data ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading") for an overview of the data preparation process.

Figure 5: The visualization of the AI ArXiv dataset preparation process. This diagram shows the selection of papers for question-answer generation, the employment of the full dataset to provide ample noise for the RAG system, and the chunking approaches used to process the documents for the vector database.

###  3.2 Mitigating LLM Output Variability

To address the inherent variability of LLM outputs, the methodology included conducting 10 runs for each RAG technique. This strategy was chosen to balance the need for statistical reliability against the limitations of computational resources and time. While more runs could increase statistical reliability, they would also complicate the need to distinguish between statistical and practical significance.

###  3.3 Metrics

To evaluate the performance of various RAG techniques within this study, two primary metrics were employed from the Tonic Validate package/platform: Retrieval Precision and Answer Similarity (Tonic AI, [2023](https://arxiv.org/html/2404.01037v1#bib.bib20)). These metrics were selected to evaluate both the retrieval process and the generative capabilities of the LLMs used, with a primary focus on the precision of information retrieval.

####  3.3.1 Retrieval Precision

This metric serves as the cornerstone of the evaluation, directly measuring the efficacy of the retrieval techniques implemented in the RAG system. Retrieval Precision quantifies the percentage of context retrieved by the system that is relevant to answering a given question, with scores ranging from 0 to 1. A higher score indicates a greater proportion of the retrieved content is pertinent to the query. The evaluation is conducted by asking an LLM evaluator to determine the relevance of each piece of retrieved context, ensuring that the assessment focuses on the accuracy of information retrieval, rather than the subsequent generation quality. See Figure [6](https://arxiv.org/html/2404.01037v1#S3.F6 "Figure 6 ‣ 3.3.1 Retrieval Precision ‣ 3.3 Metrics ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading") for visual explanation of retrieval precision grading workflow.

Figure 6: This diagram illustrates the evaluation process in a RAG system, where each chunk’s relevance is scored, contributing to the overall retrieval precision metric. The process highlights how individual chunks are evaluated for their utility in responding to user queries.

####  3.3.2 Answer Similarity

As a complementary metric, Answer Similarity assesses how well the answers generated by the RAG system align with reference answers, scored on a scale from 0 to 5. While this end-to-end test provides valuable insights into the system’s overall performance, it was considered secondary to the primary objective of evaluating retrieval techniques. This is because Answer Similarity could be influenced by the generative capabilities of the LLM, potentially confounding the assessment of retrieval effectiveness alone.

####  3.3.3 Rationale for Metric Selection

To select appropriate metrics for the study the goal was to move beyond simplistic measures of similarity, such as cosine similarity between embeddings (which do not fully capture the complexity of effective retrieval and generation). The landscape of available metrics and evaluation platforms revealed a lack of consensus on optimal evaluation strategies for RAG systems, particularly with a focus on retrieval. While some methods, such as those proposed by RAGAS (RAGAS Documentation, [2023](https://arxiv.org/html/2404.01037v1#bib.bib19)), involve detailed calculations with LLMs and F1 scores, these were deemed to be unsuitable for the objectives in this paper. Their complexity often led to results that were unreliable. Conversely, simple embedding comparisons were deemed insufficient for capturing the nuanced effectiveness of retrieval techniques. Ultimately, the selection of Retrieval Precision as the primary metric, complemented by Answer Similarity, was driven by the focus on evaluating the retrieval component of RAG systems. Though confident in the appropriateness of these metrics, especially Retrieval Precision, one has to acknowledge the ongoing development in this area and remain open to future advancements and consensus in evaluation methodologies.

###  3.4 LLM

For the experimental setup GPT-3.5-turbo was selected because of its cost-effectiveness and ease of implementation. Tonic Validate’s requirement for OpenAI models led us to choose GPT-3.5-turbo due to its cost-effectiveness, even though GPT-4 might provide more precise grading at a higher expense. It is important to note that the choice of the LLM used for generation itself was less critical for the main objective—evaluating retrieval precision, since answer similarity can be regarded as a supplementary metric.

##  4 Results

The study systematically evaluates a variety of advanced RAG techniques using metrics of Retrieval Precision and Answer Similarity. A comparative analysis is presented through boxplots to visualize the distribution of these metrics, followed by ANOVA and Tukey’s HSD tests to determine the statistical significance of the differences observed.

###  4.1 Comparative Performance Analysis: Boxplots

The boxplots for Retrieval Precision (Figure [7](https://arxiv.org/html/2404.01037v1#S4.F7 "Figure 7 ‣ 4.1 Comparative Performance Analysis: Boxplots ‣ 4 Results ‣ ARAGOG: Advanced RAG Output Grading")) indicate varied performance across RAG techniques. The Sentence Window Retrieval approach is notably effective, with a high median precision, though this does not directly correlate with Answer Similarity performance (see Figure [8](https://arxiv.org/html/2404.01037v1#S4.F8 "Figure 8 ‣ 4.1 Comparative Performance Analysis: Boxplots ‣ 4 Results ‣ ARAGOG: Advanced RAG Output Grading")). Techniques utilizing LLM Rerank and Hypothetical Document Embedding (HyDE) show enhanced precision, markedly outperforming the Naive RAG baseline. Conversely, Maximal Marginal Relevance (MMR) and Cohere Rerank demonstrate limited benefits, with median precision scores comparable to or below the baseline. Multi-query, interestingly, presents a reduction in retrieval precision compared to Naive RAG, warranting further investigation into its application. Document summary index performance is similar to the best setting of Classic VDB, indicating that with further enhancements, Document summary technique would surpass Classic VDB.

Figure 7: Boxplot of Retrieval Precision by Experiment. Each boxplot demonstrates the range and distribution of retrieval precision scores across different RAG techniques. Higher median values and tighter interquartile ranges suggest better performance and consistency.

The analysis of answer similarity (Figure [8](https://arxiv.org/html/2404.01037v1#S4.F8 "Figure 8 ‣ 4.1 Comparative Performance Analysis: Boxplots ‣ 4 Results ‣ ARAGOG: Advanced RAG Output Grading")) presents intriguing patterns that both align with and diverge from those observed in retrieval precision. For Classic Vector Database (VDB) techniques and Document Summary Index, there is a notable positive correlation between retrieval precision and answer similarity, suggesting that when relevant information is accurately retrieved, it can lead to answers that more closely mirror reference responses.

In contrast, Sentence Window Retrieval displays a disparity between high retrieval precision and lower answer similarity scores. This could indicate that while the technique is adept at identifying relevant passages, it may not be translating this information into answers that are semantically parallel to the reference, possibly due to the generation phase not fully leveraging the retrieved context.

Figure 8: Boxplot of Answer Similarity by Experiment. Each boxplot demonstrates the range and distribution of answer similarity scores across different RAG techniques. Higher median values and tighter interquartile ranges suggest better performance and consistency.

###  4.2 Statistical Validation of Differences

As described in section [3.2](https://arxiv.org/html/2404.01037v1#S3.SS2 "3.2 Mitigating LLM Output Variability ‣ 3 Methods ‣ ARAGOG: Advanced RAG Output Grading"), 10 iterations of each experiment were conducted to mitigate the impact of inherent LLM variability on the results. An ANOVA test applied to these results confirmed significant differences in Retrieval Precision across the various techniques, validating that observed variations were not due to random chance but reflect true performance disparities. Following this, Tukey’s Honestly Significant Difference (HSD) test provided a more granular understanding of these performance differentials. The statistical tests focus only on the primary metric of this study, retrieval precision. In light of the extensive range of possible pairwise comparisons, the analysis concentrated on the comparisons deemed to be most relevant.

####  4.2.1 Classic VDB

The Tukey post-hoc test results for the Classic VDB setup confirm that both HyDE and its combinations with Cohere Rerank and LLM Rerank significantly outperform the Naive RAG, aligning with the boxplot observations of higher retrieval precision. Significant improvemnt is also observed for LLM Rerank alone. However, the Maximal Marginal Relevance (MMR) and Cohere Rerank do not show a significant improvement over Naive RAG, which is also reflected in their closer median precision scores in the boxplots. Interestingly, the Multi Query + Reciprocal technique, while statistically significant, presents a mean difference suggesting lower performance compared to Naive RAG, contradicting the anticipated outcome and calling for additional scrutiny.

Technique | Comparison | Mean Diff. | P-adj | Reject Null  
---|---|---|---|---  
Cohere Rerank | Naive RAG | -0.0150 | 0.4515 | False  
HyDE | Naive RAG | -0.0648 | 0.0000 | True  
HyDE + Cohere Rerank | Naive RAG | -0.0371 | 0.0000 | True  
HyDE + LLM Rerank | Naive RAG | -0.0749 | 0.0000 | True  
LLM Rerank | Naive RAG | -0.0514 | 0.0000 | True  
Maximal Marginal Relevance (MMR) | Naive RAG | -0.0156 | 0.3787 | False  
Multi Query + Cohere Rerank | Naive RAG | 0.0012 | 1.0000 | False  
Multi Query + Reciprocal | Naive RAG | 0.0542 | 0.0000 | True  
Table 1: Tukey’s HSD test results comparing RAG techniques to Naive RAG, all within the Classic VDB framework

Next, the focus is on techniques which have shown statistically significant improvement over the Naive RAG approach. The table below presents the results from Tukey’s post-hoc tests, contrasting each of the high-performing techniques against each other.

Technique | Comparison | Mean Diff. | P-adj | Reject Null  
---|---|---|---|---  
HyDE | HyDE + Cohere Rerank | -0.0277 | 0.0002 | True  
HyDE | HyDE + LLM Rerank | 0.0101 | 0.3255 | False  
HyDE | LLM Rerank | -0.0134 | 0.1175 | False  
HyDE + Cohere Rerank | HyDE + LLM Rerank | 0.0378 | 0.0000 | True  
HyDE + Cohere Rerank | LLM Rerank | 0.0143 | 0.0842 | False  
HyDE + LLM Rerank | LLM Rerank | -0.0235 | 0.0015 | True  
Table 2: Tukey’s HSD test results of RAG techniques that offer significant improvement over Naive RAG

The combination of HyDE and LLM Rerank emerged as the most potent in enhancing retrieval precision within the Classic VDB framework, surpassing other techniques. However, this superior performance comes with higher latency and cost implications due to the additional LLM calls required for both reranking and hypothetical document embedding. Close second is HyDE alone, not showing significant difference from HyDE + LLM rerank combination. Experiments including Cohere Rerank did not demonstrate anticipated benefits.

####  4.2.2 Sentence window

This section delves into the analysis of Sentence Window retrieval techniques. First, the worst sentence window retriever technique is compared with the best classic VDB technique.

Technique | Comparison | Mean Diff. | P-adj | Reject Null  
---|---|---|---|---  
HyDE + LLM Rerank | Sentence Window + Cohere Rerank | 0.1021 | 0.0000 | True  
Table 3: Tukey’s HSD test results for the best performing Classic VDB technique against the worst Sentence Window retrieval technique.

The Tukey’s HSD test clearly indicates that even the least performing Sentence Window technique surpasses the best Classic VDB method in retrieval precision. This underscores the potential of the Sentence Window approach in RAG systems. However, the contrasting results from the Answer Similarity metric serve as a reminder to interpret these findings cautiously.   


Next is a comparison of individual Sentence Window retrieval variants.

Base Technique | Compared Technique | Mean Diff. | P-adj | Reject Null  
---|---|---|---|---  
Sentence Window | Sentence Window + Cohere Rerank | 0.0090 | 0.9768 | False  
Sentence Window | Sentence Window + HyDE | -0.0025 | 1.0000 | False  
Sentence Window | Sentence Window + HyDE + Cohere Rerank | -0.0078 | 0.9945 | False  
Sentence Window | Sentence Window + LLM Rerank | 0.0332 | 0.0000 | True  
Table 4: Tukey’s HSD test results for Sentence Window retrieval enhancements

The Tukey’s HSD test delineates Sentence Window retrieval with LLM Rerank as the only variant to offer a statistically significant improvement over the base Sentence Window technique.

####  4.2.3 Document Summary Index

The Document Summary Index technique was analyzed, focusing on two variations: one augmented with Cohere Rerank and another with HyDE plus Cohere Rerank. The choice to limit the study to these two is due to computational constraints and the need for comparability across experiments. The table below shows that there is no significant difference between the two techniques.

Technique | Comparison | Mean Diff. | P-adj | Reject Null  
---|---|---|---|---  
Doc Sum + Cohere Re | Doc Summ + HyDE + Cohere Re | 0.0109 | 0.8935 | False  
Table 5: Tukey’s HSD test results comparing Document Summary Index variants

To finish off the analysis, a basic version of every vector database set up were compared with another, i.e. Sentence Window, Naive RAG and Document Summary with Cohere rerank. Utilizing plain Document Summary without enhancements was not feasible for this analysis, as it aggregates multiple chunks into one summary, leading to results not directly comparable to other techniques that operate on different chunk quantities.

Technique | Comparison | Mean Diff. | P-adj | Reject Null  
---|---|---|---|---  
Doc Summ Index + Cohere Rerank | Classic VDB + Naive RAG | 0.0545 | 0.0000 | True  
Doc Summ Index + Cohere Rerank | Sentence Window Retrieval | 0.1679 | 0.0000 | True  
Classic VDB + Naive RAG | Sentence Window Retrieval | 0.1134 | 0.0000 | True  
Table 6: Tukey’s HSD test results comparing the performance of Sentence Window retrieval and Document Summary Index + Cohere Rerank against the baseline Naive RAG

The Tukey’s HSD test results establish the Sentence Window retrieval as the leading technique, surpassing the Document Summary Index in precision. Document Summary Index with Cohere Rerank trails behind as a viable second, whereas the Classic VDB, in its standard form, demonstrates the least retrieval precision among the evaluated techniques.   


##  5 Limitations

  * •

Model selection: We used GPT-3.5-turbo for evaluating responses due to the constraints of Tonic Validate, which requires the use of OpenAI models. The choice of GPT-3.5-turbo, while cost-effective, may not offer the same depth of analysis as more advanced models like GPT-4.

  * •

Data and question scope: The study was conducted using a singular dataset and a set of 107 questions, which may affect the generalizability of the findings across different LLM applications. Expanding the variety of datasets and questions could potentially yield more comprehensive insights.

  * •

Chunking variability: While the use of multiple chunking strategies allowed for a comprehensive evaluation of different retrieval methods, it also highlighted the inherent challenges in directly comparing their performance against the same metrics. Each retrieval method required a distinct chunking approach tailored to its specific needs. For instance, the sentence window retrieval method necessitated overlapping chunks of consecutive sentences, while the document summary index used larger chunks to leverage the language model’s summarization capabilities effectively. Consequently, the retrieval methods were evaluated on chunk types with varying degrees of context and information density, making it difficult to draw definitive conclusions about their relative strengths and weaknesses. This limitation stems from the fundamental differences in how these retrieval methods operate and the distinct chunking requirements they impose.

  * •

Evaluation metrics: The lack of a clear consensus on the optimal metrics for evaluating RAG systems means our chosen metrics—Retrieval Precision and Answer Similarity—are based on conceptual alignment rather than empirical evidence of their efficacy. This highlights an area for future research to solidify the evaluation framework for RAG systems.

  * •

Technique Selection: The subset of RAG techniques evaluated, while selected based on current relevance and potential, is not exhaustive. Excluded techniques such as Step back prompting (Dai et al., [2023](https://arxiv.org/html/2404.01037v1#bib.bib4)), Auto-merging retrieval (Phaneendra, [2023](https://arxiv.org/html/2404.01037v1#bib.bib16)), and Hybrid search (Akash, [2023](https://arxiv.org/html/2404.01037v1#bib.bib1)) reflect the study’s scope limitation and the subjective nature of selection. Future research should consider these and other emerging methods to broaden the understanding of RAG system enhancements.




##  6 Conclusion

Our investigation into Retrieval-Augmented Generation (RAG) techniques has identified HyDE and LLM reranking as notable enhancers of retrieval precision in LLMs. These approaches, however, necessitate additional LLM queries, incurring greater latency and cost. Surprisingly, established techniques like MMR and Cohere rerank did not demonstrate significant benefits, and Multi-query was found to be less effective than baseline Naive RAG.

The results demonstrate the efficacy of the Sentence Window Retrieval technique in achieving high precision for retrieval tasks, although a discrepancy was observed between retrieval precision and answer similarity scores. Given its conceptual similarity to Sentence Window retrieval, we suggest that Auto-merging retrieval (Phaneendra, [2023](https://arxiv.org/html/2404.01037v1#bib.bib16)) might offer comparable benefits, warranting future investigation. The Document Summary Index approach also exhibited satisfactory performance, however, it requires an upfront investment in generating summaries for each document in the corpus.

Due to constraints such as dataset singularity, limited questions, and the use of GPT-3.5-turbo for evaluation, the results may not fully capture the potential of more advanced models. Future studies with broader datasets and higher-capability LLMs could provide more comprehensive insights. This research contributes a foundational perspective to the field, encouraging subsequent works to refine, validate, and expand upon our findings.

To facilitate this continuation of research and allow for the replication and extension of our work, we have made our experimental pipeline available through a publicly accessible GitHub repository. (Predlico, [2024](https://arxiv.org/html/2404.01037v1#bib.bib18))

##  7 Future Work

  * •

Knowledge Graph RAG: Integrating Knowledge Graphs (KGs) with RAG systems represents a promising direction for enhancing retrieval precision and contextual relevance. KGs offer a well-organized framework of relationship-rich data that could refine the retrieval phase of RAG systems (Bratanic, [2023](https://arxiv.org/html/2404.01037v1#bib.bib2)). Although setting up such systems is resource-demanding, the potential for significantly improved retrieval processes justifies further investigation.

  * •

Unfrozen RAG systems: Unlike the static application of RAG systems in our study, future investigations can benefit from adapting RAG components, including embedding models and rerankers, directly to specific datasets (Gao et al., [2024](https://arxiv.org/html/2404.01037v1#bib.bib7), Kiela, [2024](https://arxiv.org/html/2404.01037v1#bib.bib10)). This ”unfrozen” approach allows for fine-tuning on nuanced use-case data, potentially enhancing system specificity and output quality. Exploring these adaptations could lead to more adaptable and effective RAG systems tailored to diverse application needs.

  * •

Experiment replication across diverse datasets: To ensure the robustness and generalizability of our findings, it is imperative for future research to replicate our experiments using a variety of datasets. Conducting these experiments across multiple datasets is important to verify the applicability of our results and to identify any context-specific adjustments needed.

  * •

Auto-RAG: The idea of automatically optimizing RAG systems, akin to Auto-ML’s approach in traditional machine learning, presents a significant opportunity for future exploration. Currently, selecting the optimal configuration of RAG components — e.g., chunking strategies, window sizes, and parameters within rerankers — relies on manual experimentation and intuition. An automated system could systematically explore a vast space of RAG configurations and select the very best model (Markr.AI, [2024](https://arxiv.org/html/2404.01037v1#bib.bib15)).




## References

  * Akash (2023) Akash.  Hybrid search: Optimizing rag implementation.  <https://medium.com/@csakash03/hybrid-search-is-a-method-to-optimize-rag-implementation-98d9d0911341>, 2023.  Accessed: 2024-04-01. 
  * Bratanic (2023) T. Bratanic.  Using a knowledge graph to implement a rag application.  <https://neo4j.com/developer-blog/knowledge-graph-rag-application/>, 2023.  Accessed: 2024-03-24. 
  * Carbonell and Goldstein (1998) J. Carbonell and J. Goldstein.  The use of mmr, diversity-based reranking for reordering documents and producing summaries.  <https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf>, 1998.  Accessed: 2024-03-24. 
  * Dai et al. (2023) Z. Dai, J. Callan, K.-W. Chang, D. Chen, K. Guu, X. Han, K. Hashimoto, H. He, M. Joshi, D. Jurafsky, J. Karishnamurthy, D. Khashabi, D. Kiela, A. Kumar, Z. Lan, M. Lewis, X. Ma, S. Min, A. Neelakantan, A. Y. Ng, P. Pasupat, P. Qi, C. Raffel, S. Roller, K. Shih, and L. Zettlemoyer.  Step back prompting: Enhancing llms with historical context retrieval.  <https://arxiv.org/abs/2310.06117>, 2023. 
  * Devlin et al. (2019) J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova.  Bert: Pre-training of deep bidirectional transformers for language understanding, 2019. 
  * Gao et al. (2022) L. Gao, X. Ma, J. Lin, and J. Callan.  Precise zero-shot dense retrieval without relevance labels, 2022. 
  * Gao et al. (2024) Y. Gao, Y. Xiong, X. Gao, K. Jia, J. Pan, Y. Bi, Y. Dai, J. Sun, Q. Guo, M. Wang, and H. Wang.  Retrieval-augmented generation for large language models: A survey, 2024. 
  * James Calam (2023) James Calam.  Ai arxiv dataset.  <https://huggingface.co/datasets/jamescalam/ai-arxiv>, 2023.  Accessed: 2024-03-24. 
  * Jiang et al. (2023) Z. Jiang, F. F. Xu, L. Gao, Z. Sun, Q. Liu, J. Dwivedi-Yu, Y. Yang, J. Callan, and G. Neubig.  Active retrieval augmented generation, 2023. 
  * Kiela (2024) D. Kiela.  Stanford cs25: V3 i retrieval augmented language models.  <https://www.youtube.com/watch?v=mE7IDf2SmJg>, 2024.  Accessed: 2024-03-24. 
  * Langchain (2023) Langchain.  Query transformations.  <https://blog.langchain.dev/query-transformations/>, 2023.  Accessed: 2024-03-23. 
  * Liu (2023a) J. Liu.  A new document summary index for llm-powered qa systems.  <https://www.llamaindex.ai/blog/a-new-document-summary-index-for-llm-powered-qa-systems-9a32ece2f9ec>, 2023a.  Accessed: 2024-03-23. 
  * Liu (2023b) J. Liu.  Using llms for retrieval and reranking.  <https://www.llamaindex.ai/blog/using-llms-for-retrieval-and-reranking-23cf2d3a14b6>, 2023b.  Accessed: 2024-03-24. 
  * Liu et al. (2019) Y. Liu, M. Ott, N. Goyal, J. Du, M. Joshi, D. Chen, O. Levy, M. Lewis, L. Zettlemoyer, and V. Stoyanov.  Roberta: A robustly optimized bert pretraining approach, 2019. 
  * Markr.AI (2024) Markr.AI.  Autorag: A framework for automated retrieval-augmented generation.  <https://github.com/Marker-Inc-Korea/AutoRAG>, 2024.  Accessed: 2024-03-24. 
  * Phaneendra (2023) K. Phaneendra.  Deep dive into advanced rag applications in llm-based systems.  <https://phaneendrakn.medium.com/deep-dive-into-advanced-rag-applications-in-llm-based-systems-1ccee0473b3b>, 2023.  Accessed: 2024-04-01. 
  * Pinecone (2023) Pinecone.  Rerankers.  <https://www.pinecone.io/learn/series/rag/rerankers/>, 2023.  Accessed: 2024-03-24. 
  * Predlico (2024) Predlico.  Aragog - advanced retrieval augmented generation output grading.  <https://github.com/predlico/ARAGOG>, 2024.  Accessed: 2024-03-24. 
  * RAGAS Documentation (2023) RAGAS Documentation.  Metrics.  <https://docs.ragas.io/en/v0.0.17/concepts/metrics/index.html>, 2023.  Accessed: 2024-03-24. 
  * Tonic AI (2023) Tonic AI.  About rag metrics: Tonic validate rag metrics summary.  <https://docs.tonic.ai/validate/about-rag-metrics/tonic-validate-rag-metrics-summary>, 2023.  Accessed: 2024-03-24. 
  * Yang (2023) S. Yang.  Advanced rag 01: Small to big retrieval.  <https://towardsdatascience.com/advanced-rag-01-small-to-big-retrieval-172181b396d4>, 2023.  Accessed: 2024-03-23. 



Generated on Thu May 2 18:53:23 2024 by [LaTeXML](http://dlmf.nist.gov/LaTeXML/)
