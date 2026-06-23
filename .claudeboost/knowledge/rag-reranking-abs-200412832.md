<!-- Source: https://arxiv.org/abs/2004.12832 | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

Skip to main content

[](https://www.cornell.edu/)

[Learn about arXiv becoming an independent nonprofit.](https://tech.cornell.edu/arxiv/)

We gratefully acknowledge support from the Simons Foundation, [member institutions](https://info.arxiv.org/about/ourmembers.html), and all contributors. [Donate](https://info.arxiv.org/about/donate.html)

[](/IgnoreMe)

[](/) > [cs](/list/cs/recent) > arXiv:2004.12832 

[Help](https://info.arxiv.org/help) | [Advanced Search](https://arxiv.org/search/advanced)

All fields Title Author Abstract Comments Journal reference ACM classification MSC classification Report number arXiv identifier DOI ORCID arXiv author ID Help pages Full text

Search

[](https://arxiv.org/)

[ ](https://www.cornell.edu/)

open search

GO

open navigation menu

## quick links

  * [Login](https://arxiv.org/login)
  * [Help Pages](https://info.arxiv.org/help)
  * [About](https://info.arxiv.org/about)



# Computer Science > Information Retrieval

**arXiv:2004.12832** (cs) 

[Submitted on 27 Apr 2020 ([v1](https://arxiv.org/abs/2004.12832v1)), last revised 4 Jun 2020 (this version, v2)]

# Title:ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT

Authors:[Omar Khattab](https://arxiv.org/search/cs?searchtype=author&query=Khattab,+O), [Matei Zaharia](https://arxiv.org/search/cs?searchtype=author&query=Zaharia,+M)

View a PDF of the paper titled ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT, by Omar Khattab and Matei Zaharia

[View PDF](/pdf/2004.12832)

> Abstract:Recent progress in Natural Language Understanding (NLU) is driving fast-paced advances in Information Retrieval (IR), largely owed to fine-tuning deep language models (LMs) for document ranking. While remarkably effective, the ranking models based on these LMs increase computational cost by orders of magnitude over prior approaches, particularly as they must feed each query-document pair through a massive neural network to compute a single relevance score. To tackle this, we present ColBERT, a novel ranking model that adapts deep LMs (in particular, BERT) for efficient retrieval. ColBERT introduces a late interaction architecture that independently encodes the query and the document using BERT and then employs a cheap yet powerful interaction step that models their fine-grained similarity. By delaying and yet retaining this fine-granular interaction, ColBERT can leverage the expressiveness of deep LMs while simultaneously gaining the ability to pre-compute document representations offline, considerably speeding up query processing. Beyond reducing the cost of re-ranking the documents retrieved by a traditional model, ColBERT's pruning-friendly interaction mechanism enables leveraging vector-similarity indexes for end-to-end retrieval directly from a large document collection. We extensively evaluate ColBERT using two recent passage search datasets. Results show that ColBERT's effectiveness is competitive with existing BERT-based models (and outperforms every non-BERT baseline), while executing two orders-of-magnitude faster and requiring four orders-of-magnitude fewer FLOPs per query. 

Comments: | Accepted at SIGIR 2020  
---|---  
Subjects: |  Information Retrieval (cs.IR); Computation and Language (cs.CL)  
Cite as: | [arXiv:2004.12832](https://arxiv.org/abs/2004.12832) [cs.IR]  
  | (or  [arXiv:2004.12832v2](https://arxiv.org/abs/2004.12832v2) [cs.IR] for this version)   
  |  <https://doi.org/10.48550/arXiv.2004.12832> Focus to learn more arXiv-issued DOI via DataCite  
  
## Submission history

From: Omar Khattab [[view email](/show-email/d1145b02/2004.12832)]   
**[[v1]](/abs/2004.12832v1)** Mon, 27 Apr 2020 14:21:03 UTC (1,437 KB)  
**[v2]** Thu, 4 Jun 2020 05:28:21 UTC (3,959 KB)  


Full-text links:

## Access Paper:

View a PDF of the paper titled ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT, by Omar Khattab and Matei Zaharia

  * [View PDF](/pdf/2004.12832)
  * [TeX Source ](/src/2004.12832)



[view license](http://arxiv.org/licenses/nonexclusive-distrib/1.0/ "Rights to this article")

Current browse context: 

cs.IR

[< prev](/prevnext?id=2004.12832&function=prev&context=cs.IR "previous in cs.IR \(accesskey p\)")   |   [next >](/prevnext?id=2004.12832&function=next&context=cs.IR "next in cs.IR \(accesskey n\)")   


[new](/list/cs.IR/new) |  [recent](/list/cs.IR/recent) | [2020-04](/list/cs.IR/2020-04)

Change to browse by: 

[cs](/abs/2004.12832?context=cs)  
[cs.CL](/abs/2004.12832?context=cs.CL)  


### References & Citations

  * [NASA ADS](https://ui.adsabs.harvard.edu/abs/arXiv:2004.12832)
  * [Google Scholar](https://scholar.google.com/scholar_lookup?arxiv_id=2004.12832)
  * [Semantic Scholar](https://api.semanticscholar.org/arXiv:2004.12832)



### [ 1 blog link](/tb/2004.12832)

([what is this?](https://info.arxiv.org/help/trackback.html)) 

### [DBLP](https://dblp.uni-trier.de) \- CS Bibliography

[listing](https://dblp.uni-trier.de/db/journals/corr/corr2004.html#abs-2004-12832 "listing on DBLP") | [bibtex](https://dblp.uni-trier.de/rec/bibtex/journals/corr/abs-2004-12832 "DBLP bibtex record")

[Omar Khattab](https://dblp.uni-trier.de/search/author?author=Omar%20Khattab "DBLP author search")  
[Matei Zaharia](https://dblp.uni-trier.de/search/author?author=Matei%20Zaharia "DBLP author search")

export BibTeX citation Loading...

## BibTeX formatted citation

×

loading...

Data provided by: 

### Bookmark

[ ](http://www.bibsonomy.org/BibtexHandler?requTask=upload&url=https://arxiv.org/abs/2004.12832&description=ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT "Bookmark on BibSonomy") [ ](https://reddit.com/submit?url=https://arxiv.org/abs/2004.12832&title=ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT "Bookmark on Reddit")

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

[Which authors of this paper are endorsers?](/auth/show-endorsers/2004.12832) | [Disable MathJax](javascript:setMathjaxCookie\(\)) ([What is MathJax?](https://info.arxiv.org/help/mathjax.html)) 

  * [About](https://info.arxiv.org/about)
  * [Help](https://info.arxiv.org/help)



  * contact arXivClick here to contact arXiv [ Contact](https://info.arxiv.org/help/contact.html)
  * subscribe to arXiv mailingsClick here to subscribe [ Subscribe](https://info.arxiv.org/help/subscribe)



  * [Copyright](https://info.arxiv.org/help/license/index.html)
  * [Privacy Policy](https://info.arxiv.org/help/policies/privacy_policy.html)



  * [Web Accessibility Assistance](https://info.arxiv.org/help/web_accessibility.html)
  * [arXiv Operational Status ](https://status.arxiv.org)  




