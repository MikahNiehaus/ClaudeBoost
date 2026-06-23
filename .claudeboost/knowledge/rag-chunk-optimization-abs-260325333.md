<!-- Source: https://arxiv.org/abs/2603.25333 | Tier: A | Topic: rag-chunk-optimization | Fetched: 2026-06-23 -->

Skip to main content

[](https://www.cornell.edu/)

[Learn about arXiv becoming an independent nonprofit.](https://tech.cornell.edu/arxiv/)

We gratefully acknowledge support from the Simons Foundation, [member institutions](https://info.arxiv.org/about/ourmembers.html), and all contributors. [Donate](https://info.arxiv.org/about/donate.html)

[](/IgnoreMe)

[](/) > [cs](/list/cs/recent) > arXiv:2603.25333 

[Help](https://info.arxiv.org/help) | [Advanced Search](https://arxiv.org/search/advanced)

All fields Title Author Abstract Comments Journal reference ACM classification MSC classification Report number arXiv identifier DOI ORCID arXiv author ID Help pages Full text

Search

[](https://arxiv.org/)

[ ](https://www.cornell.edu/)

GO

## quick links

  * [Login](https://arxiv.org/login)
  * [Help Pages](https://info.arxiv.org/help)
  * [About](https://info.arxiv.org/about)



# Computer Science > Computation and Language

**arXiv:2603.25333** (cs) 

[Submitted on 26 Mar 2026]

# Title:Adaptive Chunking: Optimizing Chunking-Method Selection for RAG

Authors:[Paulo Roberto de Moura Júnior](https://arxiv.org/search/cs?searchtype=author&query=de+Moura+J%C3%BAnior,+P+R), [Jean Lelong](https://arxiv.org/search/cs?searchtype=author&query=Lelong,+J), [Annabelle Blangero](https://arxiv.org/search/cs?searchtype=author&query=Blangero,+A)

View a PDF of the paper titled Adaptive Chunking: Optimizing Chunking-Method Selection for RAG, by Paulo Roberto de Moura J\'unior and 2 other authors

[View PDF](/pdf/2603.25333)

> Abstract:The effectiveness of Retrieval-Augmented Generation (RAG) is highly dependent on how documents are chunked, that is, segmented into smaller units for indexing and retrieval. Yet, commonly used "one-size-fits-all" approaches often fail to capture the nuanced structure and semantics of diverse texts. Despite its central role, chunking lacks a dedicated evaluation framework, making it difficult to assess and compare strategies independently of downstream performance. We challenge this paradigm by introducing Adaptive Chunking, a framework that selects the most suitable chunking strategy for each document based on a set of five novel intrinsic, document-based metrics: References Completeness (RC), Intrachunk Cohesion (ICC), Document Contextual Coherence (DCC), Block Integrity (BI), and Size Compliance (SC), which directly assess chunking quality across key dimensions. To support this framework, we also introduce two new chunkers, an LLM-regex splitter and a split-then-merge recursive splitter, alongside targeted post-processing techniques. On a diverse corpus spanning legal, technical, and social science domains, our metric-guided adaptive method significantly improves downstream RAG performance. Without changing models or prompts, our framework increases RAG outcomes, raising answers correctness to 72% (from 62-64%) and increasing the number of successfully answered questions by over 30% (65 vs. 49). These results demonstrate that adaptive, document-aware chunking, guided by a complementary suite of intrinsic metrics, offers a practical and effective path to more robust RAG systems. Code available at [this https URL](https://github.com/ekimetrics/adaptive-chunking). 

Comments: | Accepted at LREC 2026. 10 pages, 4 figures. Code: [this https URL](https://github.com/ekimetrics/adaptive-chunking)  
---|---  
Subjects: |  Computation and Language (cs.CL); Artificial Intelligence (cs.AI); Information Retrieval (cs.IR)  
Cite as: | [arXiv:2603.25333](https://arxiv.org/abs/2603.25333) [cs.CL]  
  | (or  [arXiv:2603.25333v1](https://arxiv.org/abs/2603.25333v1) [cs.CL] for this version)   
  |  <https://doi.org/10.48550/arXiv.2603.25333> Focus to learn more arXiv-issued DOI via DataCite  
  
## Submission history

From: Jean Lelong [[view email](/show-email/28add9ae/2603.25333)]   
**[v1]** Thu, 26 Mar 2026 11:20:52 UTC (108 KB)  


Full-text links:

## Access Paper:

View a PDF of the paper titled Adaptive Chunking: Optimizing Chunking-Method Selection for RAG, by Paulo Roberto de Moura J\'unior and 2 other authors

  * [View PDF](/pdf/2603.25333)
  * [TeX Source ](/src/2603.25333)



[ view license ](http://creativecommons.org/licenses/by/4.0/ "Rights to this article")

### Current browse context:

cs.CL

[< prev](/prevnext?id=2603.25333&function=prev&context=cs.CL "previous in cs.CL \(accesskey p\)")   |   [next >](/prevnext?id=2603.25333&function=next&context=cs.CL "next in cs.CL \(accesskey n\)")   


[new](/list/cs.CL/new) |  [recent](/list/cs.CL/recent) | [2026-03](/list/cs.CL/2026-03)

Change to browse by: 

[cs](/abs/2603.25333?context=cs)  
[cs.AI](/abs/2603.25333?context=cs.AI)  
[cs.IR](/abs/2603.25333?context=cs.IR)  


### References & Citations

  * [NASA ADS](https://ui.adsabs.harvard.edu/abs/arXiv:2603.25333)
  * [Google Scholar](https://scholar.google.com/scholar_lookup?arxiv_id=2603.25333)
  * [Semantic Scholar](https://api.semanticscholar.org/arXiv:2603.25333)



export BibTeX citation Loading...

## BibTeX formatted citation

×

loading...

Data provided by: 

### Bookmark

[ ](http://www.bibsonomy.org/BibtexHandler?requTask=upload&url=https://arxiv.org/abs/2603.25333&description=Adaptive Chunking: Optimizing Chunking-Method Selection for RAG "Bookmark on BibSonomy") [ ](https://reddit.com/submit?url=https://arxiv.org/abs/2603.25333&title=Adaptive Chunking: Optimizing Chunking-Method Selection for RAG "Bookmark on Reddit")

Bibliographic Tools

# Bibliographic and Citation Tools

Bibliographic Explorer Toggle

Bibliographic Explorer _([What is the Explorer?](https://info.arxiv.org/labs/showcase.html#arxiv-bibliographic-explorer))_

Connected Papers Toggle

Connected Papers _([What is Connected Papers?](https://www.connectedpapers.com/about))_

Litmaps Toggle

Litmaps _([What is Litmaps?](https://www.litmaps.co/))_

scite.ai Toggle

scite Smart Citations _([What are Smart Citations?](https://www.scite.ai/))_

Code, Data, Media

# Code, Data and Media Associated with this Article

alphaXiv Toggle

alphaXiv _([What is alphaXiv?](https://alphaxiv.org/))_

Links to Code Toggle

CatalyzeX Code Finder for Papers _([What is CatalyzeX?](https://www.catalyzex.com))_

DagsHub Toggle

DagsHub _([What is DagsHub?](https://dagshub.com/))_

GotitPub Toggle

Gotit.pub _([What is GotitPub?](http://gotit.pub/faq))_

Huggingface Toggle

Hugging Face _([What is Huggingface?](https://huggingface.co/huggingface))_

ScienceCast Toggle

ScienceCast _([What is ScienceCast?](https://sciencecast.org/welcome))_

Demos

# Demos

Replicate Toggle

Replicate _([What is Replicate?](https://replicate.com/docs/arxiv/about))_

Spaces Toggle

Hugging Face Spaces _([What is Spaces?](https://huggingface.co/docs/hub/spaces))_

Spaces Toggle

TXYZ.AI _([What is TXYZ.AI?](https://txyz.ai))_

Related Papers

# Recommenders and Search Tools

Link to Influence Flower

Influence Flower _([What are Influence Flowers?](https://influencemap.cmlab.dev/))_

Core recommender toggle

CORE Recommender _([What is CORE?](https://core.ac.uk/services/recommender))_

  * Author
  * Venue
  * Institution
  * Topic



About arXivLabs 

# arXivLabs: experimental projects with community collaborators

arXivLabs is a framework that allows collaborators to develop and share new arXiv features directly on our website.

Both individuals and organizations that work with arXivLabs have embraced and accepted our values of openness, community, excellence, and user data privacy. arXiv is committed to these values and only works with partners that adhere to them.

Have an idea for a project that will add value for arXiv's community? [**Learn more about arXivLabs**](https://info.arxiv.org/labs/index.html).

[Which authors of this paper are endorsers?](/auth/show-endorsers/2603.25333) | [Disable MathJax](javascript:setMathjaxCookie\(\)) ([What is MathJax?](https://info.arxiv.org/help/mathjax.html)) 

  * [About](https://info.arxiv.org/about)
  * [Help](https://info.arxiv.org/help)



  * contact arXivClick here to contact arXiv [ Contact](https://info.arxiv.org/help/contact.html)
  * subscribe to arXiv mailingsClick here to subscribe [ Subscribe](https://info.arxiv.org/help/subscribe)



  * [Copyright](https://info.arxiv.org/help/license/index.html)
  * [Privacy Policy](https://info.arxiv.org/help/policies/privacy_policy.html)



  * [Web Accessibility Assistance](https://info.arxiv.org/help/web_accessibility.html)
  * [arXiv Operational Status ](https://status.arxiv.org)  




