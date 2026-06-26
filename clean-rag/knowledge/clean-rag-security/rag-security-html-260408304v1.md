<!-- Source: https://arxiv.org/html/2604.08304v1 | Tier: A | Topic: rag-security | Fetched: 2026-06-26 -->

##### Report GitHub Issue

×

Title:

Content selection saved. Describe the issue below:

Description:

Submit without GitHub Submit in GitHub

[ Back to arXiv ](/)

[Why HTML?](https://info.arxiv.org/about/accessible_HTML.html) Report Issue [ Back to Abstract ](/abs/2604.08304v1 "Back to abstract page") [ Download PDF](/pdf/2604.08304v1 "Download PDF") [ ](javascript:toggleNavTOC\(\); "Toggle navigation") [ ](javascript:toggleReadingMode\(\); "Disable reading mode, show header and footer")

  1. Abstract
  2. 1 Introduction
  3. 2 RAG Pipeline, Security Surfaces, and Operational Scope
     1. 2.1 RAG Pipeline, Trust Boundaries, and Security Surfaces
     2. 2.2 Operational Boundary
  4. 3 Attack Taxonomy
     1. 3.1 Pre-Retrieval Knowledge-Substrate Corruption
     2. 3.2 Retrieval-Time Access Manipulation
     3. 3.3 Downstream Retrieved-Context Exploitation
     4. 3.4 Knowledge Exfiltration and Privacy Attacks
     5. 3.5 Summary and Observations
  5. 4 Defenses and Remediation Mechanisms
     1. 4.1 Knowledge-Base Integrity, Provenance, and Remediation
     2. 4.2 Retrieval-Time Access Hardening
     3. 4.3 Post-Retrieval Context Isolation and Robust Generation
     4. 4.4 Access Control, Privacy, and Confidentiality
     5. 4.5 Summary and Observations
  6. 5 Benchmarks and Evaluation Studies for Secure RAG
     1. 5.1 Benchmark Studies
        1. Manipulation-oriented benchmarks.
        2. Privacy, extraction, and disclosure-oriented benchmarks.
     2. 5.2 Systematic Evaluation Studies
     3. 5.3 Summary and Observations
  7. 6 Future Directions
  8. 7 Conclusion
  9. References



[ License: arXiv.org perpetual non-exclusive license ](https://info.arxiv.org/help/license/index.html#licenses-available)

arXiv:2604.08304v1 [cs.CR] 09 Apr 2026

# Securing Retrieval-Augmented Generation: A Taxonomy of Attacks, Defenses, and Future Directions

Yuming XU1∗, Mingtao ZHANG1∗, Zhuohan GE1∗, Haoyang LI1, Nicole HU1,   
Jason Chen ZHANG1, Qing LI1, Lei CHEN2   
1The Hong Kong Polytechnic University   
2The Hong Kong University of Science and Technology (Guangzhou)   
martin.xu@connect.polyu.hk

###### Abstract

Retrieval-augmented generation (RAG) significantly enhances large language models (LLMs) but introduces novel security risks through external knowledge access. While existing studies cover various RAG vulnerabilities, they often conflate inherent LLM risks with those specifically introduced by RAG. In this paper, we propose that secure RAG is fundamentally about the security of the external knowledge-access pipeline. We establish an operational boundary to separate inherent LLM flaws from RAG-introduced or RAG-amplified threats. Guided by this perspective, we abstract the RAG workflow into six stages and organize the literature around three trust boundaries and four primary security surfaces, including pre-retrieval knowledge corruption, retrieval-time access manipulation, downstream context exploitation, and knowledge exfiltration. By systematically reviewing the corresponding attacks, defenses, remediation mechanisms, and evaluation benchmarks, we reveal that current defenses remain largely reactive and fragmented. Finally, we discuss these gaps and highlight future directions toward layered, boundary-aware protection across the entire knowledge-access lifecycle.

Securing Retrieval-Augmented Generation: A Taxonomy of Attacks, Defenses, and Future Directions

Yuming XU1∗, Mingtao ZHANG1∗, Zhuohan GE1∗, Haoyang LI1, Nicole HU1, Jason Chen ZHANG1, Qing LI1, Lei CHEN2 1The Hong Kong Polytechnic University 2The Hong Kong University of Science and Technology (Guangzhou) martin.xu@connect.polyu.hk

††footnotetext: ∗ denotes equal contribution.

##  1 Introduction

Retrieval-augmented generation (RAG) has become a practical and widely adopted paradigm for improving large language models (LLMs) with external knowledge at inference time Lewis et al. (2020); Gao et al. (2023); Wu et al. (2024); Gupta et al. (2024); Cheng et al. (2025a). By retrieving evidence from external corpora, databases, or structured repositories and incorporating it into the generation context, RAG improves factuality, updateability, and domain adaptability Gao et al. (2023); Wu et al. (2024); Yu et al. (2024); Gan et al. (2025). At the same time, this shift from parametric knowledge alone to external knowledge access introduces important security risks, because the model is no longer affected only by its parameters and the user prompt, but also by the content and access path of external knowledge Ward and Harguess (2025); Arzanipour et al. (2025); Ammann et al. (2025).

Existing surveys have already advanced the study of RAG from several important perspectives. General RAG surveys review architectures, components, and applications Gao et al. (2023); Wu et al. (2024); Gupta et al. (2024); Cheng et al. (2025a); Sharma (2025), evaluation-oriented surveys summarize metrics, frameworks, and benchmarks Yu et al. (2024); Gan et al. (2025), while trust, security, and privacy oriented surveys discuss broader trustworthiness dimensions, deployment risks, threat models, or privacy issues Zhou et al. (2024); Ni et al. (2025); Ammann et al. (2025); Ward and Harguess (2025); Arzanipour et al. (2025); Bodea et al. (2026). Surveys on general LLM security, privacy, and trustworthy agent systems further clarify the broader ecosystem where secure RAG is situated Yao et al. (2024); Das et al. (2025); Yu et al. (2025); Kim et al. (2026). However, _external knowledge access_ has not yet been established as the main organizing principle for surveying secure RAG. As a result, the boundary between inherent LLM risks and risks introduced or materially amplified by external knowledge access often remains under-specified, and the connections among attacks, defenses, and evaluation remain fragmented under this scope.

Figure 1: Intuition of attack and defense along the RAG knowledge-access pipeline.

Figure 1 gives the basic intuition. In secure RAG, the attacker often does not need to alter model parameters or place the malicious instruction directly in the user prompt. Instead, it can manipulate external content, retrieval behavior, or disclosure behavior so that harmful evidence enters the model-visible context, or so that sensitive knowledge is inferred or extracted through the response interface Choi et al. (2025); Chang et al. (2026). Defenses therefore should not be viewed only as general LLM safety measures. They must be understood as controls distributed along the full knowledge-access path.

To bridge this gap, in this paper, we introduce an important distinction. _Inherent LLM risks_ arise from the parametric model, its prompt interface, or its generation behavior, such as prompt-only jailbreaks or parametric memorization. By contrast, _RAG-introduced or RAG-amplified risks_ depend on _external non-parametric knowledge access_ , where retrieval creates a new entry point, a new disclosure channel, or a mechanism that makes the threat more persistent, transferable, and harder to remediate. Section 2.2 formalizes this operational boundary.

This focus is important because external knowledge access transforms many security failures from transient, query-local events into persistent compromises of a shared knowledge substrate, whose effects can be reused across queries, transferred across users, and become harder to detect, attribute, and remove. Moreover, research on this topic has grown rapidly, spanning attack methods, defense mechanisms, remediation strategies, and evaluation protocols. A dedicated survey is therefore needed to provide a clear scope, a systematic taxonomy, and a structured view of the rapidly growing literature on secure knowledge access in RAG.

Under this scope, we organize secure RAG around four security surfaces: pre-retrieval knowledge-substrate corruption, retrieval-time access manipulation, downstream retrieved-context exploitation, and knowledge exfiltration and privacy attacks. We then review the corresponding defense and remediation layers and summarize recent evaluation studies and benchmarks.

Against this backdrop, Our paper makes the following contributions.

  * •

We present a concise pipeline view of RAG for systematic security analysis, and relate a six-stage RAG pipeline to four primary security surfaces and three trust boundaries.

  * •

We define an operational boundary that separates inherent LLM risks from RAG-introduced or RAG-amplified risks, thereby clarifying which attacks, defenses, and evaluation studies fall within the scope of secure RAG.

  * •

We organize the attack literature and the defense and remediation literature through the same external knowledge access centric frame, which makes the relation between threat entry points and control points explicit.

  * •

We summarize benchmark studies and systematic evaluation studies for secure RAG, and distill observations and future directions for more reusable and threat-model-aware evaluation.




##  2 RAG Pipeline, Security Surfaces, and Operational Scope

###  2.1 RAG Pipeline, Trust Boundaries, and Security Surfaces

Figure 2:  RAG knowledge-access pipeline, security surfaces, and trust boundaries. 

Viewed through the lens of generation grounded in external non-parametric knowledge Lewis et al. (2020); Xiao et al. (2026); Gao et al. (2023), we abstract a standard retrieval-augmented generation (RAG) system into a six-stage workflow as follows: first, external sources provide diverse raw content; second, ingestion pipelines parse, transform, and index this content into a searchable format; third, retrieval and reranking mechanisms select the most relevant candidate evidence for a user query; next, context assembly processes and formats this evidence to construct the final model-visible prompt; then the generator synthesizes an answer conditioned on this assembled context; and finally, the system delivers the response alongside necessary logging, auditing, and potential remediation.

In this paper, we refer to the indexed external corpus, database, or multimodal store from which evidence is drawn as the _knowledge substrate_. Correspondingly, we refer to the entire inference-time process of selecting and incorporating this evidence as _external knowledge access_.

As shown in Figure 2, the pipeline view clearly exposes three trust boundaries and corresponding security surfaces at each stage. Untrusted external content first enters the system during ingestion and indexing, creating a surface for _pre-retrieval knowledge-substrate corruption_ where attackers can poison the underlying corpus. A first upstream boundary is crossed when untrusted external content enters the system through ingestion and indexing. As the system processes a query, _retrieval-time access manipulation_ can occur, where attackers attempt to distort, redirect, or suppress the selection of evidence. After the most relevant context is selected and assembled, the retrieved evidence will be sent into the model-visible context, which introduces the risk of _downstream retrieved-context exploitation_ , allowing external data to directly manipulate the generation behavior. A second, and also the most important, boundary is crossed when retrieved evidence becomes _model-visible context_ , where external content can affect generation directly rather than only retrieval scores. Finally, as the model delivers its output, the system faces _knowledge exfiltration and privacy attacks_ , where adversaries exploit the RAG interface in reverse to infer or extract sensitive information from the knowledge substrate. A final downstream boundary is crossed when the model turns retrieved context into answers or actions. Together, these three boundaries define the main control points of external knowledge access for RAG.

###  2.2 Operational Boundary

This paper focuses on _RAG-introduced_ and _RAG-amplified_ security risks. Operationally, a risk is in scope when external knowledge is the main carrier of the threat; when knowledge access creates a distinct entry point that does not exist in prompt-only LLM use; or when retrieval materially increases the persistence, transferability, or blast radius of the threat.

Under this boundary, we include attack studies, defense and remediation studies, and security evaluation studies whose main object lies in the knowledge-access pipeline. We exclude broad RAG studies whose main focus is answer quality rather than security Friel et al. (2024); Zhu et al. (2025); Park et al. (2025); Strich et al. (2026); Peng et al. (2025). We also exclude inherent LLM risks, such as prompt-only jailbreaks and purely parametric memorization, whose main object is not retrieval-coupled knowledge access Li et al. (2024); Lin et al. (2024); Yan et al. (2024); Jiang et al. (2024); Carlini et al. (2021). Accordingly, retrieved-context injection, poisoning, retrieval-coupled extraction, disclosure control, and security benchmarks for these risks are in scope, while generic prompt attacks and non-security RAG evaluation are not.

##  3 Attack Taxonomy

{forest} Figure 3: Taxonomy of RAG Attack Methods.

We organize RAG attack methods by the stage at which external knowledge enters the pipeline. As illustrated in Figure 3, our taxonomy focuses on where the adversarial payload enters, how access to external knowledge is manipulated, and when harmful external content crosses a trust boundary. Following the operational boundary in Section 2.2, the attack surface of secure RAG can be divided into four families: pre-retrieval knowledge-substrate corruption, retrieval-time access manipulation, downstream retrieved-context exploitation, and knowledge exfiltration and privacy attacks.

###  3.1 Pre-Retrieval Knowledge-Substrate Corruption

Pre-retrieval attacks compromise the external knowledge substrate before evidence is selected for a user query. Their primary goal is to implant malicious content that will later be surfaced by retrieval and reused across queries, users, or sessions. Compared with prompt-only attacks, they often require extra write access to external sources, ingestible files, or indexed repositories, while in return they offer much stronger persistence and shared-substrate blast radius once the poisoned content is admitted into the corpus.

A first line targets _corpus and document poisoning_. _PoisonedRAG_ Zou et al. (2025) formulates knowledge corruption as an optimization problem, showing that injecting a few malicious texts can induce targeted answers. Building on this, _BadRAG_ Xue et al. (2024) introduces trigger-conditioned retrieval backdoors where poisoned passages remain dormant until activated by specific queries. Then recent work develops toward more practical and stealthy settings. For instance, _CorruptRAG_ Zhang et al. (2025a) and _AuthChain_ Chang et al. (2025) demonstrate that a single text optimized for retrievability and coherence is enough for effective poisoning. Meanwhile, _UniC-RAG_ Geng et al. (2025) extends the threat to universal corruption by jointly optimizing a small set of adversarial texts to attack diverse queries efficiently. Other studies explore stealthier carriers, such as low-level perturbations in _GARAG_ Cho et al. (2024), visually inconspicuous triggers in _Retrieval Poisoning_ Zhang et al. (2024a), and retrieval-prompt hijacking in _HijackRAG_ Zhang et al. (2024b).

A second line attacks the _ingestion interface_ rather than the final indexed text. Research on _RAG Data Loaders_ Castagnaro et al. (2025) shows that malicious content hidden in common document formats can be silently introduced during parsing and loading. This view refines the poisoning threat model, demonstrating that attackers can exploit the ingestion toolchain as the attack carrier without directly editing the final corpus.

A third line extends poisoning into _structured and multimodal knowledge_. In GraphRAG systems, _GRAGPoison_ Liang et al. (2025a) uses graph relations to poison multiple queries, focusing on attack paths introduced by shared connections. _TKPA and UKPA_ Wen et al. (2025a) reveal that minimal textual perturbations can significantly distort graph-based retrieval. In multimodal contexts, _MM-PoisonRAG_ Ha et al. (2025) and _Poisoned-MRAG_ Liu et al. (2025b) inject crafted image-text pairs to steer retrieval. Furthermore, _One Pic_ Shereen et al. (2026) demonstrates that a single optimized image can inject targeted disinformation or act as a universal denial-of-service payload in visual-document RAG.

A fourth line focuses on _code-oriented knowledge poisoning_. Studies such as _RACG_ Lin et al. (2025) indicate that poisoning external code examples can propagate vulnerabilities into the generated code. _ImportSnare_ Ye et al. (2025b) extends this supply-chain view by hijacking retrieved documentation to make the model recommend attacker-controlled dependencies. Similarly, _RAG-Pull_ Stambolic et al. (2025) shows that hidden perturbations in external repositories can redirect retrieval toward malicious code.

Overall, this family shares a common property: the attack payload is planted _before retrieval_ and reused by the system as legitimate external knowledge. This mechanism makes pre-retrieval corruption the most persistent attack surface in secure RAG, expanding threats beyond transient prompt-level failures by breaching the upstream trust boundary defined in Section 2.1.

###  3.2 Retrieval-Time Access Manipulation

Retrieval-time attacks do not primarily rely on broad substrate corruption. Instead, they select misleading information desired by the attacker from the existing corpus, typically by altering the relevance ranking of the documents surfaced for a query. These attacks are usually specific to a particular query, making their disruptive persistence lower than that of corpus poisoning. However, because they can be initiated from the query side without altering the database, they remain highly effective even in black-box settings where the attacker can only probe the retrieval interface.

One line of work focuses on _query perturbation for retrieval redirection_. For example, _GGPP_ Hu et al. (2024) shows that adding a short, optimized sequence to the user’s input can trick the retriever into fetching factually incorrect documents. Taking a dynamic approach, _ReGENT_ Song et al. (2025) proposes a reinforcement learning framework to optimize word-level substitutions within target documents, generating imperceptible corpus poisoning payloads that can successfully hijack the generation while remaining natural to human readers. Notably, while these attacks modify the user’s input, their sole objective is to hijack the knowledge retrieval path instead of injecting malicious execution instructions into the LLM generator, which separates them from out-of-scope prompt jailbreaks.

A second line targets the _retrievers and ranking mechanisms_ directly. _FlipedRAG_ Chen et al. (2024) and _Topic-FlipRAG_ Gong et al. (2025) use surrogate models to craft queries that shift the stance of the retrieved evidence, enabling opinion manipulation across related topic clusters. At the system level, _Backdoored Retrievers_ Clop and Teglia (2024) compromises the dense retriever during fine-tuning, ensuring it preferentially ranks attacker-controlled content. Furthermore, _PR-Attack_ Jiao et al. (2025) introduces a coordinated threat by pairing poisoned texts with specific query triggers to exploit the retrieval matching process.

Overall, this family demonstrates that secure RAG can be compromised simply by attacking the _access path_ to external knowledge. It shows that attackers can manipulate the model-visible context without requiring large-scale database corruption by attacking the access path that determines what eventually crosses the second trust boundary. 

###  3.3 Downstream Retrieved-Context Exploitation

The third family assumes that malicious external content has successfully crossed the retrieval boundary and become model-visible context. Unlike the previous two categories that aim to feed misleading information for the LLM generator to process normally, this category focuses on actively controlling the generator’s behavior through the retrieved context. Following our boundary defined in Section 2.2, we strictly limit our discussion to threats where malicious instructions are carried by retrieved external knowledge rather than initiated by the user’s query prompt. This distinction is crucial due to the extreme stealthiness of such attacks. Because the user’s query remains completely benign, conventional prompt-filtering mechanisms commonly used in general LLM security usually fail, allowing hidden payloads within the external knowledge to silently hijack the system and alter its actions.

One line of research explores indirect prompt injection and jailbreaks in retrieved-context. These methods embed malicious instructions within external documents to bypass model safety alignments. For example, _PANDORA_ Deng et al. (2024) demonstrates that simply embedding jailbreak prompts into external documents causes the LLM to unknowingly execute the hidden malicious instructions as if they were valid context. _Phantom_ Chaudhari et al. (2024) refines this into a single-document trigger attack where a poisoned document is retrieved only when a natural trigger sequence appears in the user query, ultimately inducing harmful behaviors or privacy abuse. Additionally, _TrojanRAG_ Cheng et al. (2024) provides a joint backdoor setting that manipulates model behavior through targeted retrieval contexts. Moreover, _PIDP-Attack_ Wang et al. (2026) combines prompt injection principles with database poisoning to adaptively execute malicious instructions regardless of the user’s input.

A second line targets system availability through denial and refusal abuse. These attacks aim to paralyze the system by forcing it to abstain from answering legitimate questions. _Blocker_ Shafran et al. (2025) demonstrates that a single retrieved document can jam a RAG system and force it to refuse answering without relying on explicit instruction injection. Similarly, _MutedRAG_ Suo et al. (2025) reveals a subtle failure mode where the attacker poisons the knowledge base with minimal jailbreak texts designed purely to activate the aligned model’s own safety guardrails. Consequently, the system refuses to process otherwise legitimate queries.

Overall, downstream exploitation highlights the critical vulnerability of the model-visible context. These attacks exploit the final downstream boundary by turning model-visible external context into harmful answers or refusals.

###  3.4 Knowledge Exfiltration and Privacy Attacks

The fourth family focuses on stealing the external knowledge substrate in reverse, instead of manipulating the system’s output or behavior like the previous three categories. These attacks aim to infer or recover sensitive information from the retrieval database by exploiting retrieval-coupled signals in the model’s responses. This threat is particularly critical when RAG systems are deployed over private, proprietary, or regulated corpora.

A first line of work performs membership inference on external knowledge bases. For instance, _MIA-RAG_ Anderson et al. (2025) demonstrates that the presence of a target document in the database can be inferred through carefully designed prompts. Building on this, _S 2MIA_ Li et al. (2025) improves inference accuracy by leveraging semantic similarity between a target sample and the generated text, while _MBA_ Liu et al. (2025a) introduces mask-based inference to reduce interference from unrelated documents. Furthermore, _IA_ Naseh et al. (2025) uses natural language questions whose answers depend on the target document’s presence, making the attack hard to be noticed against prompt-based detectors.

A second line seeks direct document or data-level extraction. Studies such as _Spill the Beans_ Qi et al. (2025) show that instruction-tuned RAG systems can be induced to regurgitate datastore content verbatim. Alternatively, _Backdoor Extraction_ Peng et al. (2024) demonstrates that a compromised LLM inside a benign RAG pipeline can leak retrieved references. Recent work expands this attack surface, with _IKEA_ Wang et al. (2025c) performing implicit knowledge extraction without explicit jailbreaks, and _SECRET_ He et al. (2025b) formalizing the attack into extraction instructions, jailbreak operators, and retrieval triggers to strengthen performance across diverse systems.

A third line studies corpus-scale multi-turn extraction and pivoting. _RAGCRAWLER_ Yao et al. (2026) formulates knowledge-base stealing as an adaptive coverage problem, using a knowledge-graph-guided state to plan extraction queries systematically. In hybrid RAG settings, _Retrieval Pivot_ Thornton (2026) reveals that a semantically retrieved vector seed can pivot into sensitive graph neighborhoods during expansion, highlighting how the transition between retrieval mechanisms can cause leakage.

Overall, this family shows that privacy risk in RAG extends beyond parametric memorization to interface-level recovery of external non-parametric knowledge. The core threat is no longer private information stored in model parameters during training, but what attackers can infer or extract from the external knowledge substrate through retrieval-coupled interaction.

###  3.5 Summary and Observations

Overall, the current attack literature shows that secure RAG risks are best analyzed through the external knowledge-access pipeline view. The four attack surfaces in this section differ in mechanism, but they share the same structural property that untrusted external knowledge can be injected, redirected, exploited, or disclosed after it enters the system.

Among them, upstream poisoning is especially important because it can persist inside a shared knowledge substrate and repeatedly affect later queries, users, and system outputs. Retrieval-time manipulation and downstream retrieved-context exploitation highlight another risk that attackers can mislead more secretly if they can steer what crosses the retrieval boundary or how retrieved evidence interacts with generation. Knowledge exfiltration and privacy attacks further show that the knowledge-access interface can be abused in the reverse direction to infer or extract sensitive external content.

Taken together, secure RAG attacks are not isolated failures at answer time. They are pipeline-level failures in how external knowledge is admitted, accessed, exposed to the generator, and disclosed through the response interface.

##  4 Defenses and Remediation Mechanisms

{forest} Figure 4: Taxonomy of RAG Defense and Remediation Mechanisms.

We organize the defense studies by their primary control point in the RAG knowledge-access pipeline, mirroring the attack surfaces identified in Section 3. Specifically, this section structures RAG security mechanisms into four defensive layers: (i) knowledge-base integrity, provenance, and remediation to counter pre-retrieval substrate corruption; (ii) retrieval-time access hardening to mitigate access manipulation; (iii) post-retrieval context isolation and robust generation to thwart downstream context exploitation; and (iv) access control, privacy, and confidentiality to prevent knowledge exfiltration and unauthorized disclosure. Figure 4 illustrates the RAG defense taxonomy, in which hybrid methods are discussed in the subsection corresponding to their primary intervention stage.

###  4.1 Knowledge-Base Integrity, Provenance, and Remediation

The first defense layer protects the integrity of the external knowledge substrate. Its primary goals are to prevent malicious content from entering the corpus and to support remediation after compromise. Compared with later-stage defenses, methods in this layer either intervene earlier by acting at admission time through provenance and validation, or respond later after an incident through attribution, audit, and rollback. These methods typically require access to corpus management workflows or system logs, and they often trade deployment simplicity for stronger data governance.

Existing work in this layer remains limited. At ingestion time, _D-RAG_ E_Andersen et al. (2025) emphasizes strict admission control through blockchain-backed provenance and expert verification before data is added to the knowledge base. After compromise, _RAGForensics_ Zhang et al. (2025b) focuses on traceback: it identifies which poisoned passages are responsible for a malicious generation, thereby supporting targeted removal and post-incident remediation.

This layer is crucial because it is the only defense family that directly governs the upstream trust boundary defined in Section 2.1, rather than reacting after corrupted knowledge has already entered the shared substrate. Without such admission-level governance, defenses remain inherently reactive; for instance, many retrieval-time methods merely attempt to filter harmful evidence after the shared substrate has already been poisoned. However, current work in this direction is still sparse, and systematic support for provenance, rollback, and corpus recovery remains under-developed.

###  4.2 Retrieval-Time Access Hardening

The second defense layer secures the retrieval interface before external content becomes model-visible context. Its main objective is to prevent corrupted or low-trust evidence from dominating the final evidence set passed to the generator. These methods operate at retrieval or reranking time, and usually require access to retrieved candidates or retriever outputs. While most current methods are empirical, a small line of work provides formal robustness guarantees. Their main trade-off is between adversarial robustness and benign retrieval utility, often incurring additional latency from filtering or aggregation. We group retrieval-time defenses into three families: reliability-aware aggregation, retrieval and reranking purification, and hybrid retrieval-generation hardening.

The first family seeks robustness through _reliability-aware aggregation_. _RobustRAG_ Xiang et al. (2024) generates responses from isolated evidence groups and securely aggregates them, yielding certifiable robustness against bounded retrieval corruption. _ReliabilityRAG_ Shen et al. (2025) extends this line by explicitly using retriever-side reliability signals, such as document rank or reliability scores, to identify a consistent majority of evidence with provable robustness under bounded corruption.

The second family directly purifies retrieved candidates or reranked results. _TrustRAG_ Zhou et al. (2025a) combines cluster-based filtering with LLM self-assessment to remove suspicious or conflicting documents. _GRADA_ Zheng et al. (2025) performs graph-based reranking based on the observation that adversarial documents may look relevant to the query while remaining weakly connected to benign documents in the retrieved set. At the retriever level, _RAGPart and RAGMask_ Pathmanathan et al. (2025) operate directly on the retrieval model through document partitioning and masking-based sensitivity analysis, reducing attack impact without modifying the generator. Lightweight filtering methods, such as _RAGuard_ Cheng et al. (2025c), expand the retrieval scope and then apply chunk-wise perplexity and similarity filtering, while _FilterRAG_ Edemacu et al. (2025) distinguishes poisoned texts through corpus-level statistical cues.

The third family combines retrieval filtering with downstream consistency control. _SeCon-RAG_ Si et al. (2025) first applies semantic and cluster-based filtering, and then performs conflict-aware filtering before final answer generation.

Overall, this layer is the most direct defense counterpart to the first two attack families detailed in Section 3. It explicitly attempts to stop corrupted or manipulated evidence before it crosses the model-visible boundary. Its main limitation remains its sensitivity to adaptive attacks, especially when poisoned passages are semantically well integrated into the benign evidence distribution.

###  4.3 Post-Retrieval Context Isolation and Robust Generation

The third defense layer assumes that harmful content has already passed retrieval-time filters and entered the retrieved context. The objective therefore shifts from prevention to detection and containment after the model-visible boundary has been crossed. These methods typically require access to the retrieved context, model internals, or generation-time interactions, and they remain mostly empirical rather than formally guaranteed. Their main trade-off is that stronger isolation often requires additional model access, inference overhead, or architectural changes.

One line of work performs _post-retrieval detection and filtering_. _RevPRAG_ Tan et al. (2025) detects poisoned responses through distinctive LLM activation patterns during generation. _AV Filter_ Choudhary et al. (2026) instead uses passage-level attention-variance signals to identify retrieved passages that exert anomalously strong influence on the output. _RAGDefender_ Kim et al. (2025) offers a lighter-weight alternative by applying post-retrieval machine learning (ML)-based filtering to separate adversarial from benign passages.

A second line directly constrains how _retrieved documents interact inside the generator_. _SDAG_ Dekel et al. (2026) shows that standard causal attention can enable harmful cross-document interactions, and replaces it with sparse document attention that blocks cross-attention across retrieved documents. This design is notable because it treats poisoning not only as a content problem, but also as an interaction problem inside the generation mechanism.

A third line consists of _robust-generation methods_ that are not always security-native, but remain useful as transferable baselines. Most of these methods were originally proposed to handle imperfect retrieval, misinformation, or internal-external knowledge conflicts, rather than adversarial secure-RAG settings alone. However, they can still reduce attack impact by helping the model verify, cross-check, or discount compromised evidence after the model-visible boundary has already been crossed. For instance, _Discern-and-Answer_ Hong et al. (2024) acts as a guardrail by using a discriminator to identify and discard misleading content before the model answers. _InstructRAG_ Wei et al. (2025) mitigates the impact of malicious context by enforcing explicit denoising through self-synthesized rationales, preventing the model from blindly following adversarial instructions. _Astute RAG_ Wang et al. (2025a) neutralizes context manipulation by actively identifying conflicts between the model’s internal parametric knowledge and the externally retrieved adversarial evidence. Additionally, _RbFT_ Tu et al. (2025) inherently reduces the model’s susceptibility to adversarial steering by fine-tuning it to remain robust when exposed to misleading or counterfactual context.

Overall, this layer provides the last major containment point after the model-visible boundary has been crossed, explicitly securing the final downstream trust boundary defined in Section 2.1. It can reduce the translation of harmful context into unsafe answers or actions, although many methods in this layer remain empirical.

###  4.4 Access Control, Privacy, and Confidentiality

The final defense layer focuses on controlling who may access retrieved knowledge and how sensitive information can be exposed, processed, or leaked. Unlike integrity-oriented defenses, the main focus here is not whether retrieved evidence is benign, but whether it is authorized to be revealed and whether retrieval and generation can proceed without violating confidentiality. These methods often intervene at the system or architecture level, and their guarantees range from empirical policy enforcement to formal differential privacy or cryptographic security. Their main trade-off is stronger confidentiality at the cost of system complexity, latency, or reduced retrieval fidelity.

One line of work enforces _authorization and selective disclosure_ before sensitive content reaches the generator. _SD-RAG_ Masoud et al. (2026) is representative in decoupling disclosure control from generation, enforcing sanitization during retrieval rather than relying on prompt-level refusal alone. Meanwhile, _Access Control RAG (AC-RAG)_ Chen et al. (2025) integrates fine-grained access control explicitly into RAG workflows for sensitive domains.

A second line protects privacy through _differential privacy or corpus transformation_. _DPVoteRAG_ Koga et al. (2024) spends its privacy budget selectively on tokens that require sensitive retrieved knowledge. _RAG with Differential Privacy_ Grislain (2025), _LPRAG_ He et al. (2025a), _VAGUE-Gate_ Hemmat et al. (2025), _PAD_ Wang et al. (2025b), and _InvisibleInk_ Vinod et al. (2025) explore related mechanisms for privacy-preserving generation over sensitive context, ranging from token- or entity-level perturbation to decoding-time protection for long-form generation. _SAGE_ Zeng et al. (2025a) takes a different route by replacing private retrieval corpora entirely with high-utility synthetic alternatives.

A third line secures the _retrieval backend_. _RemoteRAG_ Cheng et al. (2025b) formalizes privacy-preserving cloud RAG, protecting query privacy with efficient distance-based perturbation. What’s more, _ppRAG_ Ye et al. (2025a) supports retrieval over outsourced encrypted databases through distance-preserving encryption, while _FRAG_ Zhao (2024) extends encrypted nearest-neighbor retrieval to federated vector databases across mutually distrusted parties.

A fourth line builds _confidential or cryptographically protected RAG architectures_. _FedE4RAG_ Mao et al. (2025) trains retrievers collaboratively in a federated manner without centralizing raw data, and _C-FedRAG_ Addison et al. (2024) leverages confidential computing for secure cross-party RAG execution. _Privacy-Aware RAG_ Zhou et al. (2025b) encrypts both textual content and embeddings before storage, an approach that _SAG_ Zhou et al. (2025c) further strengthens with formal security proofs. Moreover, as an integrative framework, _SecureRAG_ Bassit and Boddeti (2025) separates secure search from secure document fetching, combining fully homomorphic encryption for search execution with attribute-based encryption for fine-grained document access.

Overall, this layer moves secure RAG from content filtering to system-level protection. It serves as the most direct defense counterpart to the reverse-direction threat surface in Section 3.4, where the attacker seeks to infer, extract, or over-access external knowledge. This layer is especially important for real-world deployments, but it is also the most expensive to implement, since strong confidentiality typically incurs substantial architectural redesign or cryptographic overhead.

###  4.5 Summary and Observations

Overall, the current defense literature is unevenly distributed across the RAG knowledge-access pipeline. The most mature lines of work concentrate around the second and third trust boundaries. These primarily involve retrieval-time hardening before evidence becomes model-visible context, and post-retrieval isolation after that boundary is crossed. By contrast, the first upstream boundary remains much less protected. Knowledge-base integrity, provenance, and post-compromise remediation are still relatively sparse despite their critical importance for long-lived shared corpora. In parallel, access control, privacy, and confidentiality have grown rapidly as a system-level line of defense, particularly through differential privacy, encrypted retrieval, and confidential architectures.

By mapping the attack taxonomy in Figure 3 to the defense mechanisms in Figure 4, we can observe several structural patterns. First, current defenses remain predominantly reactive. Many studies attempt to filter, rerank, or contain harmful evidence only after it has already entered the retrieval flow, while significantly fewer methods govern admission, rollback, or corpus recovery at the substrate level. Second, there is a structural mismatch between threat detection mechanisms and advanced attack construction. Although many retrieval-time defenses implicitly assume that poisoned evidence will appear as a semantic outlier, modern attacks increasingly optimize for retrievability, fluency, and contextual coherence to seamlessly blend with benign evidence. Third, privacy and confidentiality mechanisms are complementary rather than substitutive. Although they are essential for preventing unauthorized disclosure and extraction, they cannot independently resolve integrity corruption or retrieved-context exploitation.

Taken together, these observations suggest that secure RAG should be viewed less as an isolated filtering task and more as a layered control problem across multiple trust boundaries. A robust deployment must synergistically combine upstream governance of the knowledge substrate, retrieval-time evidence hardening, post-retrieval containment, and confidentiality controls, rather than relying on any single defense family in isolation.

##  5 Benchmarks and Evaluation Studies for Secure RAG

Under the operational boundary in Section 2.2, we distinguish between two kinds of evaluation literature. _Benchmark studies_ provide reusable datasets, protocols, or harnesses for secure-RAG testing. _Systematic evaluation studies_ provide broader empirical analyses that clarify how secure-RAG failures behave, even when benchmark construction is not the main contribution. In this section, we review the literature in these two groups and then summarize the main observations.

###  5.1 Benchmark Studies

The current benchmark literature can be roughly divided into two groups. One group evaluates how malicious content or adversarial instructions move through the retrieval and generation pipeline. The other group evaluates privacy, extraction, and disclosure risks, often together with the trade-off between privacy protection and task utility.

#### Manipulation-oriented benchmarks.

_Rag and Roll_ De Stefano et al. (2024) is an early end-to-end evaluation framework for indirect prompt manipulation in LLM application pipelines with RAG components. Its main contribution is to evaluate attacks under realistic framework-level configurations rather than only under isolated retrieval settings. Meanwhile, _SafeRAG_ Liang et al. (2025b) provides a dedicated security benchmark for RAG with multiple attack tasks, task-aware metrics, and evaluations across representative RAG components. It is important because it turns secure-RAG evaluation into a reusable benchmark setting rather than a collection of one-off attack demonstrations. _Benchmarking Poisoning Attacks against Retrieval-Augmented Generation_ Zhang et al. (2025c) broadens this direction by comparing a wide range of poisoning attacks and defenses across datasets and RAG variants under one framework. _OpenRAG-Soc_ Guo and Wei (2026) focuses on web-facing RAG over social-web content and emphasizes realistic end-to-end evaluation of indirect prompt injection and retrieval poisoning together with practical mitigations. Moreover, _MPIB_ Lee et al. (2026) brings prompt-injection evaluation into the medical domain and is notable for measuring clinically grounded harm rather than relying only on attack success.

#### Privacy, extraction, and disclosure-oriented benchmarks.

_S-RAG_ Zeng et al. (2025b) frames privacy evaluation as black-box auditing of whether personal textual data has been used in a RAG system. _SMA_ Sun et al. (2025) extends this line toward source-aware membership auditing in semi-black-box settings and further considers multimodal retrieval. In parallel, _Privacy Protection in RAG_ Zhang et al. (2026) combines a fine-grained privacy protection design with an explicit evaluation framework for studying the privacy-utility balance beyond coarse document-level removal. _KE-Bench_ Qi et al. (2026) standardizes the evaluation of knowledge-extraction attacks and defenses across retrievers, generators, and datasets. Similarly, _MedPriv-Bench_ Guan et al. (2026) introduces a medical benchmark that jointly evaluates contextual leakage and clinical utility. Finally, _SEAL-Tag_ Xie et al. (2026) contributes a structured protocol for adaptive leakage auditing together with utility and latency evaluation for PII-safe RAG. Although Zhang et al. (2026) and Xie et al. (2026) are not benchmark-only papers, we include them here because they contribute reusable security evaluation settings or protocols rather than only reporting a single system result.

Taken together, these benchmark studies show a clear trend toward more realistic evaluation. Recent work increasingly evaluates complete pipelines, domain-specific risk, adaptive attackers, and explicit utility-security trade-offs, rather than reporting attack success on a single simplified setup.

###  5.2 Systematic Evaluation Studies

_The Good and the Bad_ Zeng et al. (2024) is an early broad empirical study of privacy in text RAG. It is important not because it releases a benchmark in the narrow sense, but because it clarifies a central tension in secure RAG. RAG can create new leakage channels for the retrieval database, while at the same time reducing some privacy risks tied to purely parametric generation.

_Beyond Text_ Zhang et al. (2025d) provides the first systematic privacy analysis of multimodal RAG across vision-language and speech-language settings. Its contribution is to show that multimodal carriers create additional leakage paths and that privacy analysis in text-only RAG does not directly transfer to multimodal settings.

_A Systemic Evaluation of Multimodal RAG Privacy_ Al-Lawati and Wang (2026) complements this direction with a focused empirical study of multimodal privacy leakage, especially membership and caption leakage under visual retrieval settings. Compared with benchmark-oriented work, these systematic studies are less about packaging a reusable suite and more about clarifying what should be measured, where leakage appears, and how the threat changes across modalities and system assumptions.

###  5.3 Summary and Observations

Overall, recent benchmarks and evaluation studies have made secure-RAG assessment more systematic and more deployment-relevant. Compared with isolated attack demonstrations, they provide clearer protocols, broader component coverage, and more realistic end-to-end settings for studying how security failures appear in practice.

At the same time, the current evaluation literature still reflects the structure of the attack and defense landscape discussed in the previous two sections. Different studies often focus on different threat surfaces, such as poisoning, prompt injection, privacy leakage, or extraction, and many reported metrics still concentrate on final outputs rather than on intermediate pipeline behavior. As a result, current evaluation is increasingly useful for comparing methods within a threat setting, while cross-surface comparison remains less unified.

Taken together, these studies show that secure-RAG evaluation is becoming a central part of the field rather than a secondary afterthought. It provides an important bridge between attack analysis and defense design by making pipeline-level threats more visible and comparable across systems.

##  6 Future Directions

Building upon our preceding analysis and discussion, we highlight four future directions valuable for advancing the field of secure RAG.

A first important direction is to move secure RAG beyond inference-time filtering toward governance and recoverability of the knowledge substrate. Current defenses still focus mainly on filtering, reranking, and containment at or after retrieval time, as discussed in Section 4. However, the primary threat is that once malicious content enters a shared knowledge substrate, it can persist, be triggered repeatedly, and affect multiple users over time Zou et al. (2025). Recent benchmark work further shows the importance of evaluating poisoning under broader settings, and _RAGForensics_ provides an encouraging step toward practical traceback and post-incident analysis Zhang et al. (2025c, b). Future work should therefore pay more attention to admission control, provenance tracking, versioned corpora, traceback, rollback, and corpus repair. The value of this direction is to make secure RAG not only resistant at answer time, but also governable and recoverable after compromise.

A second direction is to set clearer boundaries for how retrieved content is used, rather than simply concatenating all external content into the model-visible context Ramakrishna et al. (2024); Chang et al. (2026); Guo and Wei (2026); Masoud et al. (2026); Wen et al. (2025b). This concatenation-based approach is natural in standard question answering, but from a security perspective, it dangerously mixes factual evidence with executable instructions. In recent work, instruction detection methods attempt to isolate hidden instructions as distinct objects Wen et al. (2025b), while selective disclosure frameworks move security enforcement before generation Masoud et al. (2026). Future work is encouraged to continue in this direction by separating evidence from control more explicitly, such as through typed evidence, policy-aware context assembly, or bounded interaction between retrieved documents and the generator. This would reduce the chance that untrusted content is upgraded from supporting evidence into behavioral control.

A third direction is to move evaluation beyond output-only testing toward boundary-local, remediation-aware, and cross-surface evaluation. Recent studies have taken meaningful steps to make secure-RAG evaluation more realistic by broadening security-oriented benchmarking, evaluating attacks and defenses across diverse architectures, and moving privacy evaluation toward more unified protocols Liang et al. (2025b); Zhang et al. (2025c); Guo and Wei (2026); Qi et al. (2026). Moving forward, future work should delve deeper by measuring exactly where a failure occurs, how it propagates across trust boundaries, and how effectively the system recovers after mitigation. Robust and comprehensive evaluation frameworks are essential for driving innovative thinking in both offensive and defensive strategies.

A fourth direction is to push secure RAG toward richer deployment settings that better match real applications, including web-native, multimodal, and agent-coupled systems. Recent work has already started to evaluate web-facing RAG, multimodal privacy risks, multi-turn interactions, and agent-related attack settings, revealing that each setting introduces novel threat dimensions not adequately captured by single-turn text evaluations Guo and Wei (2026); Zhang et al. (2025d); Al-Lawati and Wang (2026); Katsis et al. (2025); Chang et al. (2026); Zhang et al. (2025c). Future benchmarks in these settings should remain end-to-end, cover realistic carriers and interaction patterns, and jointly evaluate security, utility, and recovery. On the security side, richer settings also call for further study of cross-modal leakage, long-horizon interactions, and action-coupled failures. This would help defenses evolve in tandem with the actual forms of RAG that are currently moving into deployment.

##  7 Conclusion

Motivated by the fact that external knowledge fundamentally alters the inference path, we proposed that secure RAG must be independently analyzed as the security of the knowledge-access pipeline, which spans data ingestion, retrieval, assembly, and disclosure. Under this perspective, we explicitly distinguished inherent LLM vulnerabilities from RAG-introduced or RAG-amplified risks. Through this operational boundary, we systematically structured the literature into four distinct security surfaces and three trust boundaries, detailing the mechanics of current attacks, defense layers, and evaluation protocols.

Our review reveals a structural mismatch across the current landscape of secure RAG. While attack strategies are rapidly evolving to generate highly coherent and retrievable payloads, most defenses remain strictly reactive, concentrating on mid-stream filtering rather than upstream corpus integrity or data provenance. Furthermore, empirical evaluations remain fragmented across isolated threat models. Moving forward, future research should transition from localized patches to layered, boundary-aware governance. This requires developing unified, cross-surface benchmarks, strengthening pre-retrieval data validation, and ensuring that defense designs incorporate practical rollback and remediation capabilities against adaptive threats.

## References

  * P. Addison, M. H. Nguyen, T. Medan, J. Shah, M. T. Manzari, B. McElrone, L. Lalwani, A. More, S. Sharma, H. R. Roth, et al. (2024) C-fedrag: a confidential federated retrieval-augmented generation system.  arXiv preprint arXiv:2412.13163.  Cited by: §4.4. 
  * A. Al-Lawati and S. Wang (2026) A systemic evaluation of multimodal rag privacy.  arXiv preprint arXiv:2601.17644.  Cited by: §5.2, §6. 
  * L. Ammann, S. Ott, C. R. Landolt, and M. P. Lehmann (2025) Securing rag: a risk assessment and mitigation framework.  In 2025 IEEE Swiss Conference on Data Science (SDS),  pp. 127–134.  Cited by: §1, §1. 
  * M. Anderson, G. Amit, and A. Goldsteen (2025) Is my data in your retrieval database? membership inference attacks against retrieval augmented generation.  In International Conference on Information Systems Security and Privacy,  Vol. 2,  pp. 474–485.  Cited by: §3.4. 
  * A. Arzanipour, R. Behnia, R. Ebrahimi, and K. Dutta (2025) Rag security and privacy: formalizing the threat model and attack surface.  arXiv preprint arXiv:2509.20324.  Cited by: §1, §1. 
  * A. Bassit and V. Boddeti (2025) SecureRAG: end-to-end secure retrieval-augmented generation.  In The Second Workshop on GenAI for Health: Potential, Trust, and Policy Compliance,  External Links: [Link](https://openreview.net/forum?id=njAyzNEaCd) Cited by: §4.4. 
  * A. Bodea, S. Meisenbacher, A. Klymenko, and F. Matthes (2026) SoK: privacy risks and mitigations in retrieval-augmented generation systems.  arXiv preprint arXiv:2601.03979.  Cited by: §1. 
  * N. Carlini, F. Tramer, E. Wallace, M. Jagielski, A. Herbert-Voss, K. Lee, A. Roberts, T. Brown, D. Song, U. Erlingsson, et al. (2021) Extracting training data from large language models.  In 30th USENIX security symposium (USENIX Security 21),  pp. 2633–2650.  Cited by: §2.2. 
  * A. Castagnaro, U. Salviati, M. Conti, L. Pajola, and S. Pizzi (2025) The hidden threat in plain text: attacking rag data loaders.  In Proceedings of the 18th ACM Workshop on Artificial Intelligence and Security,  pp. 170–181.  Cited by: §3.1. 
  * H. Chang, E. Bao, X. Luo, and T. Yu (2026) Overcoming the retrieval barrier: indirect prompt injection in the wild for llm systems.  arXiv preprint arXiv:2601.07072.  Cited by: §1, §6, §6. 
  * Z. Chang, M. Li, X. Jia, J. Wang, Y. Huang, Z. Jiang, Y. Liu, and Q. Wang (2025) One shot dominance: knowledge poisoning attack on retrieval-augmented generation systems.  In Findings of the Association for Computational Linguistics: EMNLP 2025,  Suzhou, China,  pp. 18811–18825.  External Links: [Link](https://aclanthology.org/2025.findings-emnlp.1023/) Cited by: §3.1. 
  * H. Chaudhari, G. Severi, J. Abascal, M. Jagielski, C. A. Choquette-Choo, M. Nasr, C. Nita-Rotaru, and A. Oprea (2024) Phantom: general trigger attacks on retrieval augmented language generation.  Cited by: §3.3. 
  * B. Chen, J. Tackman, M. Setälä, T. Poranen, and Z. Zhang (2025) Integrating access control with retrieval-augmented generation: a proof of concept for managing sensitive patient profiles.  In Proceedings of the 40th ACM/SIGAPP Symposium on Applied Computing,  SAC ’25, New York, NY, USA,  pp. 915–919.  External Links: ISBN 9798400706295, [Link](https://doi.org/10.1145/3672608.3707848), [Document](https://dx.doi.org/10.1145/3672608.3707848) Cited by: §4.4. 
  * Z. Chen, J. Liu, H. Liu, Q. Cheng, F. Zhang, W. Lu, and X. Liu (2024) Black-box opinion manipulation attacks to retrieval-augmented generation of large language models.  arXiv preprint arXiv:2407.13757.  Cited by: §3.2. 
  * M. Cheng, Y. Luo, J. Ouyang, Q. Liu, H. Liu, L. Li, S. Yu, B. Zhang, J. Cao, J. Ma, et al. (2025a) A survey on knowledge-oriented retrieval-augmented generation.  arXiv preprint arXiv:2503.10677.  Cited by: §1, §1. 
  * P. Cheng, Y. Ding, T. Ju, Z. Wu, W. Du, P. Yi, Z. Zhang, and G. Liu (2024) Trojanrag: retrieval-augmented generation can be backdoor driver in large language models.  arXiv preprint arXiv:2405.13401.  Cited by: §3.3. 
  * Y. Cheng, L. Zhang, J. Wang, M. Yuan, and Y. Yao (2025b) Remoterag: a privacy-preserving llm cloud rag service.  In Findings of the Association for Computational Linguistics: ACL 2025,  pp. 3820–3837.  Cited by: §4.4. 
  * Z. Cheng, J. Sun, A. Gao, Y. Quan, Z. Liu, X. Hu, and M. Fang (2025c) Secure retrieval-augmented generation against poisoning attacks.  arXiv preprint arXiv:2510.25025.  Cited by: §4.2. 
  * S. Cho, S. Jeong, J. Seo, T. Hwang, and J. C. Park (2024) Typos that broke the rag’s back: genetic attack on rag pipeline by simulating documents in the wild via low-level perturbations.  In Findings of the Association for Computational Linguistics: EMNLP 2024,  pp. 2826–2844.  Cited by: §3.1. 
  * C. Choi, J. Kim, S. Cho, S. Jeong, and B. Chang (2025) The RAG paradox: a black-box attack exploiting unintentional vulnerabilities in retrieval-augmented generation systems.  In Findings of the Association for Computational Linguistics: EMNLP 2025, C. Christodoulopoulos, T. Chakraborty, C. Rose, and V. Peng (Eds.),  Suzhou, China,  pp. 23723–23744.  External Links: [Link](https://aclanthology.org/2025.findings-emnlp.1291/), [Document](https://dx.doi.org/10.18653/v1/2025.findings-emnlp.1291), ISBN 979-8-89176-335-7 Cited by: §1. 
  * S. Choudhary, N. Palumbo, A. Hooda, K. D. Dvijotham, and S. Jha (2026) Through the stealth lens: attention-aware defenses against poisoning in RAG.  External Links: [Link](https://openreview.net/forum?id=PS43wqCSME) Cited by: §4.3. 
  * C. Clop and Y. Teglia (2024) Backdoored retrievers for prompt injection attacks on retrieval augmented generation of large language models.  arXiv preprint arXiv:2410.14479.  Cited by: §3.2. 
  * B. C. Das, M. H. Amini, and Y. Wu (2025) Security and privacy challenges of large language models: a survey.  ACM Computing Surveys 57 (6),  pp. 1–39.  Cited by: §1. 
  * G. De Stefano, L. Schönherr, and G. Pellegrino (2024) Rag and roll: an end-to-end evaluation of indirect prompt manipulations in llm-based application frameworks.  arXiv preprint arXiv:2408.05025.  Cited by: §5.1. 
  * S. Dekel, M. Tennenholtz, and O. Kurland (2026) Addressing corpus knowledge poisoning attacks on rag using sparse attention.  arXiv preprint arXiv:2602.04711.  Cited by: §4.3. 
  * G. Deng, Y. Liu, K. Wang, Y. Li, T. Zhang, and Y. Liu (2024) Pandora: jailbreak gpts by retrieval augmented generation poisoning.  arXiv preprint arXiv:2402.08416.  Cited by: §3.3. 
  * T. E_Andersen, A. M. Avalos, G. G_Dagher, and M. Long (2025) D-rag: a privacy-preserving framework for decentralized rag using blockchain.  Cited by: §4.1. 
  * K. Edemacu, V. M. Shashidhar, M. Tuape, D. Abudu, B. Jang, and J. W. Kim (2025) Defending against knowledge poisoning attacks during retrieval-augmented generation.  arXiv preprint arXiv:2508.02835.  Cited by: §4.2. 
  * R. Friel, M. Belyi, and A. Sanyal (2024) Ragbench: explainable benchmark for retrieval-augmented generation systems.  arXiv preprint arXiv:2407.11005.  Cited by: §2.2. 
  * A. Gan, H. Yu, K. Zhang, Q. Liu, W. Yan, Z. Huang, S. Tong, and G. Hu (2025) Retrieval augmented generation evaluation in the era of large language models: a comprehensive survey.  arXiv preprint arXiv:2504.14891.  Cited by: §1, §1. 
  * Y. Gao, Y. Xiong, X. Gao, K. Jia, J. Pan, Y. Bi, Y. Dai, J. Sun, H. Wang, H. Wang, et al. (2023) Retrieval-augmented generation for large language models: a survey.  arXiv preprint arXiv:2312.10997 2 (1),  pp. 32.  Cited by: §1, §1, §2.1. 
  * R. Geng, Y. Wang, Y. Chen, and J. Jia (2025) UniC-rag: universal knowledge corruption attacks to retrieval-augmented generation.  arXiv preprint arXiv:2508.18652.  Cited by: §3.1. 
  * Y. Gong, Z. Chen, J. Liu, M. Chen, F. Yu, W. Lu, X. Wang, and X. Liu (2025) {\\{topic-FlipRAG}\\}:{\\{topic-orientated}\\} adversarial opinion manipulation attacks to {\\{retrieval-augmented}\\} generation models.  In 34th USENIX Security Symposium (USENIX Security 25),  pp. 3807–3826.  Cited by: §3.2. 
  * N. Grislain (2025) Rag with differential privacy.  In 2025 IEEE Conference on Artificial Intelligence (CAI),  pp. 847–852.  Cited by: §4.4. 
  * S. Guan, Y. Zhai, H. C. Kwok, J. Du, X. Feng, J. Li, H. Qin, and V. Hui (2026) MedPriv-bench: benchmarking the privacy-utility trade-off of large language models in medical open-end question answering.  arXiv preprint arXiv:2603.14265.  Cited by: §5.1. 
  * H. Guo and Z. Wei (2026) Hidden-in-plain-text: a benchmark for social-web indirect prompt injection in rag.  arXiv preprint arXiv:2601.10923.  Cited by: §5.1, §6, §6, §6. 
  * S. Gupta, R. Ranjan, and S. N. Singh (2024) A comprehensive survey of retrieval-augmented generation (rag): evolution, current landscape and future directions.  arXiv preprint arXiv:2410.12837.  Cited by: §1, §1. 
  * H. Ha, Q. Zhan, J. Kim, D. Bralios, S. Sanniboina, N. Peng, K. Chang, D. Kang, and H. Ji (2025) MM-poisonrag: disrupting multimodal rag with local and global poisoning attacks.  arXiv preprint arXiv:2502.17832.  Cited by: §3.1. 
  * L. He, P. Tang, Y. Zhang, P. Zhou, and S. Su (2025a) Mitigating privacy risks in retrieval-augmented generation via locally private entity perturbation.  Information Processing & Management 62 (4),  pp. 104150.  Cited by: §4.4. 
  * Y. He, Y. Chen, Y. Li, S. Shao, L. Qi, B. Li, D. Tao, and Z. Qin (2025b) External data extraction attacks against retrieval-augmented large language models.  arXiv preprint arXiv:2510.02964.  Cited by: §3.4. 
  * A. Hemmat, M. Moqadas, A. Mamanpoosh, A. Rismanchian, and A. Fatemi (2025) VAGUE-gate: plug-and-play local-privacy shield for retrieval-augmented generation.  In Proceedings of the 14th International Joint Conference on Natural Language Processing and the 4th Conference of the Asia-Pacific Chapter of the Association for Computational Linguistics,  pp. 3715–3730.  Cited by: §4.4. 
  * G. Hong, J. Kim, J. Kang, S. Myaeng, and J. J. Whang (2024) Why so gullible? enhancing the robustness of retrieval-augmented models against counterfactual noise.  In Findings of the Association for Computational Linguistics: NAACL 2024,  pp. 2474–2495.  Cited by: §4.3. 
  * Z. Hu, C. Wang, Y. Shu, H. Paik, and L. Zhu (2024) Prompt perturbation in retrieval-augmented generation based large language models.  In Proceedings of the 30th ACM SIGKDD Conference on Knowledge Discovery and Data Mining,  pp. 1119–1130.  Cited by: §3.2. 
  * C. Jiang, B. Qi, X. Hong, D. Fu, Y. Cheng, F. Meng, M. Yu, B. Zhou, and J. Zhou (2024) On large language models’ hallucination with regard to known facts.  In Proceedings of the 2024 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies (Volume 1: Long Papers),  pp. 1041–1053.  Cited by: §2.2. 
  * Y. Jiao, X. Wang, and K. Yang (2025) Pr-attack: coordinated prompt-rag attacks on retrieval-augmented generation in large language models via bilevel optimization.  In Proceedings of the 48th International ACM SIGIR Conference on Research and Development in Information Retrieval,  pp. 656–667.  Cited by: §3.2. 
  * Y. Katsis, S. Rosenthal, K. Fadnis, C. Gunasekara, Y. Lee, L. Popa, V. Shah, H. Zhu, D. Contractor, and M. Danilevsky (2025) MTRAG: a multi-turn conversational benchmark for evaluating retrieval-augmented generation systems.  Transactions of the Association for Computational Linguistics 13,  pp. 784–808.  Cited by: §6. 
  * J. Kim, X. Liu, Z. Wang, S. Qiu, B. Li, W. Guo, and D. Song (2026) The attack and defense landscape of agentic ai: a comprehensive survey.  arXiv preprint arXiv:2603.11088.  Cited by: §1. 
  * M. Kim, H. Lee, and H. Koo (2025) Rescuing the unpoisoned: efficient defense against knowledge corruption attacks on rag systems.  arXiv preprint arXiv:2511.01268.  Cited by: §4.3. 
  * T. Koga, R. Wu, Z. Zhang, and K. Chaudhuri (2024) Privacy-preserving retrieval-augmented generation with differential privacy.  arXiv preprint arXiv:2412.04697.  Cited by: §4.4. 
  * J. Lee, H. Jang, and K. S. Choi (2026) MPIB: a benchmark for medical prompt injection attacks and clinical safety in llms.  arXiv preprint arXiv:2602.06268.  Cited by: §5.1. 
  * P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, W. Yih, T. Rocktäschel, et al. (2020) Retrieval-augmented generation for knowledge-intensive nlp tasks.  Advances in neural information processing systems 33,  pp. 9459–9474.  Cited by: §1, §2.1. 
  * Q. Li, J. Hong, C. Xie, J. Tan, R. Xin, J. Hou, X. Yin, Z. Wang, D. Hendrycks, Z. Wang, et al. (2024) LLM-pbe: assessing data privacy in large language models.  Proceedings of the VLDB Endowment 17 (11),  pp. 3201–3214.  Cited by: §2.2. 
  * Y. Li, G. Liu, C. Wang, and Y. Yang (2025) Generating is believing: membership inference attacks against retrieval-augmented generation.  In ICASSP 2025-2025 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP),  pp. 1–5.  Cited by: §3.4. 
  * J. Liang, Y. Wang, C. Li, R. Zhu, T. Jiang, N. Gong, and T. Wang (2025a) Graphrag under fire.  arXiv preprint arXiv:2501.14050.  Cited by: §3.1. 
  * X. Liang, S. Niu, Z. Li, S. Zhang, H. Wang, F. Xiong, Z. Fan, B. Tang, J. Zhao, J. Yang, et al. (2025b) SafeRAG: benchmarking security in retrieval-augmented generation of large language model.  In Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers),  pp. 4609–4631.  Cited by: §5.1, §6. 
  * B. Lin, S. Wang, L. Chen, and X. Mao (2025) Exploring the security threats of knowledge base poisoning in retrieval-augmented code generation.  arXiv preprint arXiv:2502.03233.  Cited by: §3.1. 
  * Y. Lin, P. He, H. Xu, Y. Xing, M. Yamada, H. Liu, and J. Tang (2024) Towards understanding jailbreak attacks in llms: a representation space analysis.  In Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing,  pp. 7067–7085.  Cited by: §2.2. 
  * M. Liu, S. Zhang, and C. Long (2025a) Mask-based membership inference attacks for retrieval-augmented generation.  In Proceedings of the ACM on Web Conference 2025,  pp. 2894–2907.  Cited by: §3.4. 
  * Y. Liu, Z. Yuan, G. Tie, J. Shi, P. Zhou, L. Sun, and N. Z. Gong (2025b) Poisoned-mrag: knowledge poisoning attacks to multimodal retrieval augmented generation.  arXiv preprint arXiv:2503.06254.  Cited by: §3.1. 
  * Q. Mao, Q. Zhang, H. Hao, Z. Han, R. Xu, W. Jiang, Q. Hu, Z. Chen, T. Zhou, B. Li, et al. (2025) Privacy-preserving federated embedding learning for localized retrieval-augmented generation.  arXiv preprint arXiv:2504.19101.  Cited by: §4.4. 
  * A. A. Masoud, M. Arazzi, and A. Nocera (2026) SD-rag: a prompt-injection-resilient framework for selective disclosure in retrieval-augmented generation.  arXiv preprint arXiv:2601.11199.  Cited by: §4.4, §6. 
  * A. Naseh, Y. Peng, A. Suri, H. Chaudhari, A. Oprea, and A. Houmansadr (2025) Riddle me this! stealthy membership inference for retrieval-augmented generation.  In Proceedings of the 2025 ACM SIGSAC Conference on Computer and Communications Security,  pp. 1245–1259.  Cited by: §3.4. 
  * B. Ni, Z. Liu, L. Wang, Y. Lei, Y. Zhao, X. Cheng, Q. Zeng, L. Dong, Y. Xia, K. Kenthapadi, et al. (2025) Towards trustworthy retrieval augmented generation for large language models: a survey.  arXiv preprint arXiv:2502.06872.  Cited by: §1. 
  * C. Park, H. Moon, C. Park, and H. Lim (2025) MIRAGE: a metric-intensive benchmark for retrieval-augmented generation evaluation.  In Findings of the Association for Computational Linguistics: NAACL 2025, L. Chiruzzo, A. Ritter, and L. Wang (Eds.),  Albuquerque, New Mexico,  pp. 2883–2900.  External Links: [Link](https://aclanthology.org/2025.findings-naacl.157/), [Document](https://dx.doi.org/10.18653/v1/2025.findings-naacl.157), ISBN 979-8-89176-195-7 Cited by: §2.2. 
  * P. Pathmanathan, M. Panaitescu-Liess, C. J. Chiang, and F. Huang (2025) RAGPart & ragmask: retrieval-stage defenses against corpus poisoning in retrieval-augmented generation.  arXiv preprint arXiv:2512.24268.  Cited by: §4.2. 
  * X. Peng, P. K. Choubey, C. Xiong, and C. Wu (2025) Unanswerability evaluation for retrieval augmented generation.  In Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers),  pp. 8452–8472.  Cited by: §2.2. 
  * Y. Peng, J. Wang, H. Yu, and A. Houmansadr (2024) Data extraction attacks in retrieval-augmented generation via backdoors.  arXiv preprint arXiv:2411.01705.  Cited by: §3.4. 
  * Z. Qi, H. Zhang, E. Xing, S. Kakade, and H. Lakkaraju (2025) Follow my instruction and spill the beans: scalable data extraction from retrieval-augmented generation systems.  In The Thirteenth International Conference on Learning Representations (ICLR 2025),  External Links: [Link](https://openreview.net/forum?id=Y4aWwRh25b) Cited by: §3.4. 
  * Z. Qi, U. Sahu, L. Ma, H. Han, R. Rossi, F. Dernoncourt, M. Halappanavar, N. Ahmed, Y. Dong, Y. Zhao, et al. (2026) Benchmarking knowledge-extraction attack and defense on retrieval-augmented generation.  arXiv preprint arXiv:2602.09319.  Cited by: §5.1, §6. 
  * A. Ramakrishna, J. Majmudar, R. Gupta, and D. Hazarika (2024) Llm-pieval: a benchmark for indirect prompt injection attacks in large language models.  Cited by: §6. 
  * A. Shafran, R. Schuster, and V. Shmatikov (2025) Machine against the {\\{rag}\\}: jamming {\\{retrieval-augmented}\\} generation with blocker documents.  In 34th USENIX Security Symposium (USENIX Security 25),  pp. 3787–3806.  Cited by: §3.3. 
  * C. Sharma (2025) Retrieval-augmented generation: a comprehensive survey of architectures, enhancements, and robustness frontiers.  arXiv preprint arXiv:2506.00054.  Cited by: §1. 
  * Z. Shen, B. Y. Imana, T. Wu, C. Xiang, P. Mittal, and A. Korolova (2025) ReliabilityRAG: effective and provably robust defense for RAG-based web-search.  In The Thirty-ninth Annual Conference on Neural Information Processing Systems,  External Links: [Link](https://openreview.net/forum?id=D9JeNTs5Bu) Cited by: §4.2. 
  * E. Shereen, D. Ristea, S. McFadden, B. Hasircioglu, V. Mavroudis, and C. Hicks (2026) One pic is all it takes: poisoning visual document retrieval augmented generation with a single image.  Transactions on Machine Learning Research.  External Links: ISSN 2835-8856, [Link](https://openreview.net/forum?id=CLkjUidlYg) Cited by: §3.1. 
  * X. Si, M. Zhu, S. Qin, L. Yu, L. Zhang, S. Liu, X. Li, R. Duan, Y. Liu, and X. Jia (2025) SeCon-rag: a two-stage semantic filtering and conflict-free framework for trustworthy rag.  arXiv preprint arXiv:2510.09710.  Cited by: §4.2. 
  * H. Song, Y. Liu, R. Zhang, J. Guo, J. Lv, M. de Rijke, and X. Cheng (2025) The silent saboteur: imperceptible adversarial attacks against black-box retrieval-augmented generation systems.  In Findings of the Association for Computational Linguistics: ACL 2025,  pp. 13935–13952.  Cited by: §3.2. 
  * V. Stambolic, A. Dhar, and L. Cavigelli (2025) RAG-pull: imperceptible attacks on rag systems for code generation.  arXiv preprint arXiv:2510.11195.  Cited by: §3.1. 
  * J. Strich, E. K. Isgorur, M. Trescher, C. Biemann, and M. Semmann (2026) T2-ragbench: text-and-table aware retrieval-augmented generation.  In Proceedings of the 19th Conference of the European Chapter of the Association for Computational Linguistics (Volume 1: Long Papers),  pp. 165–191.  Cited by: §2.2. 
  * S. Sun, S. Liang, R. Chen, J. Huang, J. Li, and X. Cao (2025) SMA: who said that? auditing membership leakage in semi-black-box rag controlling.  arXiv preprint arXiv:2508.09105.  Cited by: §5.1. 
  * P. Suo, Y. Shang, S. Guo, and X. Zhang (2025) Hoist with his own petard: inducing guardrails to facilitate denial-of-service attacks on retrieval-augmented generation of llms.  arXiv preprint arXiv:2504.21680.  Cited by: §3.3. 
  * X. Tan, H. Luan, M. Luo, X. Sun, P. Chen, and J. Dai (2025) RevPRAG: revealing poisoning attacks in retrieval-augmented generation through LLM activation analysis.  In Findings of the Association for Computational Linguistics: EMNLP 2025, C. Christodoulopoulos, T. Chakraborty, C. Rose, and V. Peng (Eds.),  Suzhou, China,  pp. 12999–13011.  External Links: [Link](https://aclanthology.org/2025.findings-emnlp.698/), [Document](https://dx.doi.org/10.18653/v1/2025.findings-emnlp.698), ISBN 979-8-89176-335-7 Cited by: §4.3. 
  * S. Thornton (2026) Retrieval pivot attacks in hybrid rag: measuring and mitigating amplified leakage from vector seeds to graph expansion.  arXiv preprint arXiv:2602.08668.  Cited by: §3.4. 
  * Y. Tu, W. Su, Y. Zhou, Y. Liu, and Q. Ai (2025) RbFT: robust fine-tuning for retrieval-augmented generation against retrieval defects.  arXiv preprint arXiv:2501.18365.  Cited by: §4.3. 
  * V. Vinod, K. Pillutla, and A. G. Thakurta (2025) Invisibleink: high-utility and low-cost text generation with differential privacy.  arXiv preprint arXiv:2507.02974.  Cited by: §4.4. 
  * F. Wang, X. Wan, R. Sun, J. Chen, and S. O. Arik (2025a) Astute rag: overcoming imperfect retrieval augmentation and knowledge conflicts for large language models.  In Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers),  pp. 30553–30571.  Cited by: §4.3. 
  * H. Wang, X. Xu, B. Huang, and K. Shu (2025b) Privacy-aware decoding: mitigating privacy leakage of large language models in retrieval-augmented generation.  arXiv preprint arXiv:2508.03098.  Cited by: §4.4. 
  * H. Wang, H. Liu, J. Zhu, Z. Wang, Y. Guo, and X. Tang (2026) PIDP-attack: combining prompt injection with database poisoning attacks on retrieval-augmented generation systems.  arXiv preprint arXiv:2603.25164.  Cited by: §3.3. 
  * Y. Wang, W. Qu, Y. Jiang, L. Liu, Y. Liu, S. Zhai, Y. Dong, and J. Zhang (2025c) Silent leaks: implicit knowledge extraction attack on RAG systems through benign queries.  In ICML 2025 Workshop on Reliable and Responsible Foundation Models,  External Links: [Link](https://openreview.net/forum?id=F5TD0OExsf) Cited by: §3.4. 
  * C. M. Ward and J. Harguess (2025) Adversarial threat vectors and risk mitigation for retrieval-augmented generation systems.  In Assurance and Security for AI-enabled Systems 2025,  Vol. 13476,  pp. 80–97.  Cited by: §1, §1. 
  * Z. Wei, W. Chen, and Y. Meng (2025) InstructRAG: instructing retrieval-augmented generation via self-synthesized rationales.  In The Thirteenth International Conference on Learning Representations,  External Links: [Link](https://openreview.net/forum?id=P1qhkp8gQT) Cited by: §4.3. 
  * J. Wen, T. Chen, Z. Zheng, and C. Huang (2025a) A few words can distort graphs: knowledge poisoning attacks on graph-based retrieval-augmented generation of large language models.  arXiv preprint arXiv:2508.04276.  Cited by: §3.1. 
  * T. Wen, C. Wang, X. Yang, H. Tang, Y. Xie, L. Lyu, Z. Dou, and F. Wu (2025b) Defending against indirect prompt injection by instruction detection.  In Findings of the Association for Computational Linguistics: EMNLP 2025, C. Christodoulopoulos, T. Chakraborty, C. Rose, and V. Peng (Eds.),  Suzhou, China,  pp. 19472–19487.  External Links: [Link](https://aclanthology.org/2025.findings-emnlp.1060/), [Document](https://dx.doi.org/10.18653/v1/2025.findings-emnlp.1060), ISBN 979-8-89176-335-7 Cited by: §6. 
  * S. Wu, Y. Xiong, Y. Cui, H. Wu, C. Chen, Y. Yuan, L. Huang, X. Liu, T. Kuo, N. Guan, et al. (2024) Retrieval-augmented generation for natural language processing: a survey.  arXiv preprint arXiv:2407.13193.  Cited by: §1, §1. 
  * C. Xiang, T. Wu, Z. Zhong, D. Wagner, D. Chen, and P. Mittal (2024) Certifiably robust rag against retrieval corruption.  arXiv preprint arXiv:2405.15556.  Cited by: §4.2. 
  * Y. Xiao, C. Zhou, Q. Zhang, B. Li, Q. Li, and X. Huang (2026) Reliable reasoning path: distilling effective guidance for llm reasoning with knowledge graphs.  IEEE Transactions on Knowledge and Data Engineering.  Cited by: §2.1. 
  * J. Xie, S. Li, and G. Cheng (2026) SEAL-tag: self-tag evidence aggregation with probabilistic circuits for pii-safe retrieval-augmented generation.  arXiv preprint arXiv:2603.17292.  Cited by: §5.1. 
  * J. Xue, M. Zheng, Y. Hu, F. Liu, X. Chen, and Q. Lou (2024) Badrag: identifying vulnerabilities in retrieval augmented generation of large language models.  arXiv preprint arXiv:2406.00083.  Cited by: §3.1. 
  * J. Yan, V. Yadav, S. Li, L. Chen, Z. Tang, H. Wang, V. Srinivasan, X. Ren, and H. Jin (2024) Backdooring instruction-tuned large language models with virtual prompt injection.  In Proceedings of the 2024 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies (Volume 1: Long Papers),  pp. 6065–6086.  Cited by: §2.2. 
  * M. Yao, Z. Zhang, N. Luo, S. Li, Y. Cai, X. Chen, Y. Guo, and D. Li (2026) Connect the dots: knowledge graph-guided crawler attack on retrieval-augmented generation systems.  arXiv preprint arXiv:2601.15678.  Cited by: §3.4. 
  * Y. Yao, J. Duan, K. Xu, Y. Cai, Z. Sun, and Y. Zhang (2024) A survey on large language model (llm) security and privacy: the good, the bad, and the ugly.  High-Confidence Computing 4 (2),  pp. 100211.  Cited by: §1. 
  * H. Ye, J. Guo, Z. Liu, and K. Lam (2025a) Efficient privacy-preserving retrieval augmented generation with distance-preserving encryption.  In 2025 3rd International Conference on Foundation and Large Language Models (FLLM),  pp. 668–676.  Cited by: §4.4. 
  * K. Ye, L. Su, and C. Qian (2025b) ImportSnare: directed’code manual’hijacking in retrieval-augmented code generation.  In Proceedings of the 2025 ACM SIGSAC Conference on Computer and Communications Security,  pp. 335–349.  Cited by: §3.1. 
  * H. Yu, A. Gan, K. Zhang, S. Tong, Q. Liu, and Z. Liu (2024) Evaluation of retrieval-augmented generation: a survey.  In CCF Conference on Big Data,  pp. 102–120.  Cited by: §1, §1. 
  * M. Yu, F. Meng, X. Zhou, S. Wang, J. Mao, L. Pan, T. Chen, K. Wang, X. Li, Y. Zhang, et al. (2025) A survey on trustworthy llm agents: threats and countermeasures.  In Proceedings of the 31st ACM SIGKDD Conference on Knowledge Discovery and Data Mining V. 2,  pp. 6216–6226.  Cited by: §1. 
  * S. Zeng, J. Zhang, P. He, Y. Liu, Y. Xing, H. Xu, J. Ren, Y. Chang, S. Wang, D. Yin, et al. (2024) The good and the bad: exploring privacy issues in retrieval-augmented generation (rag).  In Findings of the Association for Computational Linguistics: ACL 2024,  pp. 4505–4524.  Cited by: §5.2. 
  * S. Zeng, J. Zhang, P. He, J. Ren, T. Zheng, H. Lu, H. Xu, H. Liu, Y. Xing, and J. Tang (2025a) Mitigating the privacy issues in retrieval-augmented generation (rag) via pure synthetic data.  In Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing,  pp. 24538–24569.  Cited by: §4.4. 
  * Z. Zeng, J. Liu, M. Chiang, J. He, and Z. Zhang (2025b) S-rag: a novel audit framework for detecting unauthorized use of personal data in rag systems.  In Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers),  pp. 10375–10385.  Cited by: §5.1. 
  * B. Zhang, Y. Chen, Z. Liu, L. Nie, T. Li, Z. Liu, and M. Fang (2025a) Practical poisoning attacks against retrieval-augmented generation.  arXiv preprint arXiv:2504.03957.  Cited by: §3.1. 
  * B. Zhang, H. Xin, M. Fang, Z. Liu, B. Yi, T. Li, and Z. Liu (2025b) Traceback of poisoning attacks to retrieval-augmented generation.  In Proceedings of the ACM on Web Conference 2025,  pp. 2085–2097.  Cited by: §4.1, §6. 
  * B. Zhang, H. Xin, J. Li, D. Zhang, M. Fang, Z. Liu, L. Nie, and Z. Liu (2025c) Benchmarking poisoning attacks against retrieval-augmented generation.  arXiv preprint arXiv:2505.18543.  Cited by: §5.1, §6, §6, §6. 
  * J. Zhang, S. Zeng, J. Ren, T. Zheng, H. Liu, X. Tang, and Y. Chang (2025d) Beyond text: unveiling privacy vulnerabilities in multi-modal retrieval-augmented generation.  In Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing,  pp. 24800–24821.  Cited by: §5.2, §6. 
  * Q. Zhang, B. Zeng, C. Zhou, G. Go, H. Shi, and Y. Jiang (2024a) Human-imperceptible retrieval poisoning attacks in llm-powered applications.  In Companion Proceedings of the 32nd ACM International Conference on the Foundations of Software Engineering,  pp. 502–506.  Cited by: §3.1. 
  * Y. Zhang, J. Wu, R. Li, T. Zhang, Y. Song, C. Li, S. Wang, H. Shen, J. Yin, J. Ge, et al. (2026) Privacy protection in rag: a novel method and evaluation framework.  Information Processing & Management 63 (3),  pp. 104505.  Cited by: §5.1. 
  * Y. Zhang, Q. Li, T. Du, X. Zhang, X. Zhao, Z. Feng, and J. Yin (2024b) Hijackrag: hijacking attacks against retrieval-augmented large language models.  arXiv preprint arXiv:2410.22832.  Cited by: §3.1. 
  * D. Zhao (2024) Frag: toward federated vector database management for collaborative and secure retrieval-augmented generation.  arXiv preprint arXiv:2410.13272.  Cited by: §4.4. 
  * J. Zheng, A. P. Gema, G. Hong, X. He, P. Minervini, Y. Sun, and Q. Xu (2025) GRADA: graph-based reranking against adversarial documents attack.  In Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing,  pp. 22255–22277.  Cited by: §4.2. 
  * H. Zhou, K. Lee, Z. Zhan, Y. Chen, Z. Li, Z. Wang, H. Haddadi, and E. Yilmaz (2025a) TrustRAG: enhancing robustness and trustworthiness in retrieval-augmented generation.  arXiv preprint arXiv:2501.00879.  Cited by: §4.2. 
  * P. Zhou, Y. Feng, and Z. Yang (2025b) Privacy-aware rag: secure and isolated knowledge retrieval.  arXiv preprint arXiv:2503.15548.  Cited by: §4.4. 
  * P. Zhou, Y. Feng, and Z. Yang (2025c) Provably secure retrieval-augmented generation.  arXiv preprint arXiv:2508.01084.  Cited by: §4.4. 
  * Y. Zhou, Y. Liu, X. Li, J. Jin, H. Qian, Z. Liu, C. Li, Z. Dou, T. Ho, and P. S. Yu (2024) Trustworthiness in retrieval-augmented generation systems: a survey.  arXiv preprint arXiv:2409.10102.  Cited by: §1. 
  * K. Zhu, Y. Luo, D. Xu, Y. Yan, Z. Liu, S. Yu, R. Wang, S. Wang, Y. Li, N. Zhang, et al. (2025) Rageval: scenario specific rag evaluation dataset generation framework.  In Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers),  pp. 8520–8544.  Cited by: §2.2. 
  * W. Zou, R. Geng, B. Wang, and J. Jia (2025) PoisonedRAG: knowledge corruption attacks to retrieval-augmented generation of large language models.  In 34th USENIX Security Symposium (USENIX Security 25),  pp. 3827–3844.  Cited by: §3.1, §6. 



Experimental support, please [view the build logs](./2604.08304v1/__stdout.txt) for errors. Generated by [ L A T E xml ](https://math.nist.gov/~BMiller/LaTeXML/). 

## Instructions for reporting errors

We are continuing to improve HTML versions of papers, and your feedback helps enhance accessibility and mobile support. To report errors in the HTML that will help us improve conversion and rendering, choose any of the methods listed below:

  * Click the "Report Issue" ( ) button, located in the page header.



**Tip:** You can select the relevant text first, to include it in your report.

Our team has already identified [the following issues](https://github.com/arXiv/html_feedback/issues). We appreciate your time reviewing and reporting rendering errors we may not have found yet. Your efforts will help us improve the HTML versions for all readers, because disability should not be a barrier to accessing research. Thank you for your continued support in championing open access for all.

Have a free development cycle? Help support accessibility at arXiv! Our collaborators at LaTeXML maintain a [list of packages that need conversion](https://github.com/brucemiller/LaTeXML/wiki/Porting-LaTeX-packages-for-LaTeXML), and welcome [developer contributions](https://github.com/brucemiller/LaTeXML/issues).

BETA

[ ](javascript:toggleReadingMode\(\); "Disable reading mode, show header and footer")
