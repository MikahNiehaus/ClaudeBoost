<!-- Source: https://arxiv.org/abs/2403.12968 | Tier: A | Topic: context-compression | Fetched: 2026-06-23 -->

Skip to main content

[](https://www.cornell.edu/)

[Learn about arXiv becoming an independent nonprofit.](https://tech.cornell.edu/arxiv/)

We gratefully acknowledge support from the Simons Foundation, [member institutions](https://info.arxiv.org/about/ourmembers.html), and all contributors. [Donate](https://info.arxiv.org/about/donate.html)

[](/IgnoreMe)

[](/) > [cs](/list/cs/recent) > arXiv:2403.12968 

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

**arXiv:2403.12968** (cs) 

[Submitted on 19 Mar 2024 ([v1](https://arxiv.org/abs/2403.12968v1)), last revised 12 Aug 2024 (this version, v2)]

# Title:LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression

Authors:[Zhuoshi Pan](https://arxiv.org/search/cs?searchtype=author&query=Pan,+Z), [Qianhui Wu](https://arxiv.org/search/cs?searchtype=author&query=Wu,+Q), [Huiqiang Jiang](https://arxiv.org/search/cs?searchtype=author&query=Jiang,+H), [Menglin Xia](https://arxiv.org/search/cs?searchtype=author&query=Xia,+M), [Xufang Luo](https://arxiv.org/search/cs?searchtype=author&query=Luo,+X), [Jue Zhang](https://arxiv.org/search/cs?searchtype=author&query=Zhang,+J), [Qingwei Lin](https://arxiv.org/search/cs?searchtype=author&query=Lin,+Q), [Victor Rühle](https://arxiv.org/search/cs?searchtype=author&query=R%C3%BChle,+V), [Yuqing Yang](https://arxiv.org/search/cs?searchtype=author&query=Yang,+Y), [Chin-Yew Lin](https://arxiv.org/search/cs?searchtype=author&query=Lin,+C), [H. Vicky Zhao](https://arxiv.org/search/cs?searchtype=author&query=Zhao,+H+V), [Lili Qiu](https://arxiv.org/search/cs?searchtype=author&query=Qiu,+L), [Dongmei Zhang](https://arxiv.org/search/cs?searchtype=author&query=Zhang,+D)

View a PDF of the paper titled LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression, by Zhuoshi Pan and 12 other authors

[View PDF](/pdf/2403.12968) [HTML (experimental)](https://arxiv.org/html/2403.12968v2)

> Abstract:This paper focuses on task-agnostic prompt compression for better generalizability and efficiency. Considering the redundancy in natural language, existing approaches compress prompts by removing tokens or lexical units according to their information entropy obtained from a causal language model such as LLaMa-7B. The challenge is that information entropy may be a suboptimal compression metric: (i) it only leverages unidirectional context and may fail to capture all essential information needed for prompt compression; (ii) it is not aligned with the prompt compression objective.   
> To address these issues, we propose a data distillation procedure to derive knowledge from an LLM to compress prompts without losing crucial information, and meantime, introduce an extractive text compression dataset. We formulate prompt compression as a token classification problem to guarantee the faithfulness of the compressed prompt to the original one, and use a Transformer encoder as the base architecture to capture all essential information for prompt compression from the full bidirectional context. Our approach leads to lower latency by explicitly learning the compression objective with smaller models such as XLM-RoBERTa-large and mBERT.   
> We evaluate our method on both in-domain and out-of-domain datasets, including MeetingBank, LongBench, ZeroScrolls, GSM8K, and BBH. Despite its small size, our model shows significant performance gains over strong baselines and demonstrates robust generalization ability across different LLMs. Additionally, our model is 3x-6x faster than existing prompt compression methods, while accelerating the end-to-end latency by 1.6x-2.9x with compression ratios of 2x-5x. Our code is available at [this https URL](https://aka.ms/LLMLingua-2). 

Comments: | Accepted at Findings of ACL 2024  
---|---  
Subjects: |  Computation and Language (cs.CL); Machine Learning (cs.LG)  
Cite as: | [arXiv:2403.12968](https://arxiv.org/abs/2403.12968) [cs.CL]  
  | (or  [arXiv:2403.12968v2](https://arxiv.org/abs/2403.12968v2) [cs.CL] for this version)   
  |  <https://doi.org/10.48550/arXiv.2403.12968> Focus to learn more arXiv-issued DOI via DataCite  
  
## Submission history

From: Huiqiang Jiang [[view email](/show-email/5cdf0f76/2403.12968)]   
**[[v1]](/abs/2403.12968v1)** Tue, 19 Mar 2024 17:59:56 UTC (3,604 KB)  
**[v2]** Mon, 12 Aug 2024 04:48:11 UTC (225 KB)  


Full-text links:

## Access Paper:

View a PDF of the paper titled LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression, by Zhuoshi Pan and 12 other authors

  * [View PDF](/pdf/2403.12968)
  * [HTML (experimental)](https://arxiv.org/html/2403.12968v2)
  * [TeX Source ](/src/2403.12968)



[view license](http://arxiv.org/licenses/nonexclusive-distrib/1.0/ "Rights to this article")

### Current browse context:

cs.CL

[< prev](/prevnext?id=2403.12968&function=prev&context=cs.CL "previous in cs.CL \(accesskey p\)")   |   [next >](/prevnext?id=2403.12968&function=next&context=cs.CL "next in cs.CL \(accesskey n\)")   


[new](/list/cs.CL/new) |  [recent](/list/cs.CL/recent) | [2024-03](/list/cs.CL/2024-03)

Change to browse by: 

[cs](/abs/2403.12968?context=cs)  
[cs.LG](/abs/2403.12968?context=cs.LG)  


### References & Citations

  * [NASA ADS](https://ui.adsabs.harvard.edu/abs/arXiv:2403.12968)
  * [Google Scholar](https://scholar.google.com/scholar_lookup?arxiv_id=2403.12968)
  * [Semantic Scholar](https://api.semanticscholar.org/arXiv:2403.12968)



export BibTeX citation Loading...

## BibTeX formatted citation

×

loading...

Data provided by: 

### Bookmark

[ ](http://www.bibsonomy.org/BibtexHandler?requTask=upload&url=https://arxiv.org/abs/2403.12968&description=LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression "Bookmark on BibSonomy") [ ](https://reddit.com/submit?url=https://arxiv.org/abs/2403.12968&title=LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression "Bookmark on Reddit")

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

[Which authors of this paper are endorsers?](/auth/show-endorsers/2403.12968) | [Disable MathJax](javascript:setMathjaxCookie\(\)) ([What is MathJax?](https://info.arxiv.org/help/mathjax.html)) 

  * [About](https://info.arxiv.org/about)
  * [Help](https://info.arxiv.org/help)



  * contact arXivClick here to contact arXiv [ Contact](https://info.arxiv.org/help/contact.html)
  * subscribe to arXiv mailingsClick here to subscribe [ Subscribe](https://info.arxiv.org/help/subscribe)



  * [Copyright](https://info.arxiv.org/help/license/index.html)
  * [Privacy Policy](https://info.arxiv.org/help/policies/privacy_policy.html)



  * [Web Accessibility Assistance](https://info.arxiv.org/help/web_accessibility.html)
  * [arXiv Operational Status ](https://status.arxiv.org)  




