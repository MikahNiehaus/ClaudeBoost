<!-- Source: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2 | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

[ Hugging Face](/)

  * [ Models ](/models)
  * [ Datasets ](/datasets)
  * [ Spaces ](/spaces)
  * [ Buckets new](/storage)
  * [ Docs ](/docs)
  * [ Enterprise ](/enterprise)
  * [Pricing](/pricing)
  *     * Website

      * [ Tasks](/tasks)
      * [ HuggingChat](/chat)
      * [ Collections](/collections)
      * [ Languages](/languages)
      * [ Organizations](/organizations)
    * Community

      * [ Blog](/blog)
      * [ Posts](/posts)
      * [ Daily Papers](/papers)
      * [ Learn](/learn)
      * [ Discord](/join/discord)
      * [ Forum](https://discuss.huggingface.co/)
      * [ GitHub](https://github.com/huggingface)
    * Solutions

      * [ Team & Enterprise](/enterprise)
      * [ Hugging Face PRO](/pro)
      * [ Enterprise Support](/support)
      * [ Inference Providers](/inference/models)
      * [ Inference Endpoints](/inference-endpoints)
      * [ Storage Buckets](/storage)

  * * * *

  * [Log In](/login)
  * [Sign Up](/join)



# 

[ ](/cross-encoder)

[cross-encoder](/cross-encoder)

/

[ms-marco-MiniLM-L6-v2](/cross-encoder/ms-marco-MiniLM-L6-v2)

like 268

Follow

Sentence Transformers - Cross-Encoders 254

[ Text Ranking ](/models?pipeline_tag=text-ranking)[ sentence-transformers ](/models?library=sentence-transformers)[ PyTorch ](/models?library=pytorch)[ JAX ](/models?library=jax)[ ONNX ](/models?library=onnx)[ Safetensors ](/models?library=safetensors)[ OpenVINO ](/models?library=openvino)[ Transformers ](/models?library=transformers)

sentence-transformers/msmarco

[ English ](/models?language=en)[ bert ](/models?other=bert)[ text-classification ](/models?other=text-classification)[ text-embeddings-inference ](/models?other=text-embeddings-inference)

License: apache-2.0

[ Model card ](/cross-encoder/ms-marco-MiniLM-L6-v2)[ Files Files and versions xet ](/cross-encoder/ms-marco-MiniLM-L6-v2/tree/main)[ Community 18 ](/cross-encoder/ms-marco-MiniLM-L6-v2/discussions)

Deploy

Copy to bucket new

Use this model

### Instructions to use cross-encoder/ms-marco-MiniLM-L6-v2 with libraries, inference providers, notebooks, and local apps. Follow these links to get started.

  * Libraries
  * [ sentence-transformers](/cross-encoder/ms-marco-MiniLM-L6-v2?library=sentence-transformers)

How to use cross-encoder/ms-marco-MiniLM-L6-v2 with sentence-transformers:
        
        from sentence_transformers import CrossEncoder
        
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")
        
        query = "Which planet is known as the Red Planet?"
        passages = [
        	"Venus is often called Earth's twin because of its similar size and proximity.",
        	"Mars, known for its reddish appearance, is often referred to as the Red Planet.",
        	"Jupiter, the largest planet in our solar system, has a prominent red spot.",
        	"Saturn, famous for its rings, is sometimes mistaken for the Red Planet."
        ]
        
        scores = model.predict([(query, passage) for passage in passages])
        print(scores)

  * [ Transformers](/cross-encoder/ms-marco-MiniLM-L6-v2?library=transformers)

How to use cross-encoder/ms-marco-MiniLM-L6-v2 with Transformers:
        
        # Load model directly
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        
        tokenizer = AutoTokenizer.from_pretrained("cross-encoder/ms-marco-MiniLM-L6-v2")
        model = AutoModelForSequenceClassification.from_pretrained("cross-encoder/ms-marco-MiniLM-L6-v2")

  * Notebooks
  * [ Google Colab](/cross-encoder/ms-marco-MiniLM-L6-v2/colab)
  * [ Kaggle](/cross-encoder/ms-marco-MiniLM-L6-v2/kaggle)



  * Cross-Encoder for MS Marco
    * Usage with SentenceTransformers
    * Usage with Transformers
    * Performance



#  Cross-Encoder for MS Marco 

This model was trained on the [MS Marco Passage Ranking](https://github.com/microsoft/MSMARCO-Passage-Ranking) task.

The model can be used for Information Retrieval: Given a query, encode the query will all possible passages (e.g. retrieved with ElasticSearch). Then sort the passages in a decreasing order. See [SBERT.net Retrieve & Re-rank](https://www.sbert.net/examples/applications/retrieve_rerank/README.html) for more details. The training code is available here: [SBERT.net Training MS Marco](https://github.com/UKPLab/sentence-transformers/tree/master/examples/cross_encoder/training/ms_marco)

##  Usage with SentenceTransformers 

The usage is easy when you have [SentenceTransformers](https://www.sbert.net/) installed. Then you can use the pre-trained models like this:
    
    
    from sentence_transformers import CrossEncoder
    
    model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')
    scores = model.predict([
        ("How many people live in Berlin?", "Berlin had a population of 3,520,031 registered inhabitants in an area of 891.82 square kilometers."),
        ("How many people live in Berlin?", "Berlin is well known for its museums."),
    ])
    print(scores)
    # [ 8.607138 -4.320078]
    

##  Usage with Transformers 
    
    
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    
    model = AutoModelForSequenceClassification.from_pretrained('cross-encoder/ms-marco-MiniLM-L6-v2')
    tokenizer = AutoTokenizer.from_pretrained('cross-encoder/ms-marco-MiniLM-L6-v2')
    
    features = tokenizer(['How many people live in Berlin?', 'How many people live in Berlin?'], ['Berlin has a population of 3,520,031 registered inhabitants in an area of 891.82 square kilometers.', 'New York City is famous for the Metropolitan Museum of Art.'],  padding=True, truncation=True, return_tensors="pt")
    
    model.eval()
    with torch.no_grad():
        scores = model(**features).logits
        print(scores)
    

##  Performance 

In the following table, we provide various pre-trained Cross-Encoders together with their performance on the [TREC Deep Learning 2019](https://microsoft.github.io/TREC-2019-Deep-Learning/) and the [MS Marco Passage Reranking](https://github.com/microsoft/MSMARCO-Passage-Ranking/) dataset. 

Model-Name | NDCG@10 (TREC DL 19) | MRR@10 (MS Marco Dev) | Docs / Sec  
---|---|---|---  
**Version 2 models** |  |  |   
cross-encoder/ms-marco-TinyBERT-L2-v2 | 69.84 | 32.56 | 9000  
cross-encoder/ms-marco-MiniLM-L2-v2 | 71.01 | 34.85 | 4100  
cross-encoder/ms-marco-MiniLM-L4-v2 | 73.04 | 37.70 | 2500  
cross-encoder/ms-marco-MiniLM-L6-v2 | 74.30 | 39.01 | 1800  
cross-encoder/ms-marco-MiniLM-L12-v2 | 74.31 | 39.02 | 960  
**Version 1 models** |  |  |   
cross-encoder/ms-marco-TinyBERT-L2 | 67.43 | 30.15 | 9000  
cross-encoder/ms-marco-TinyBERT-L4 | 68.09 | 34.50 | 2900  
cross-encoder/ms-marco-TinyBERT-L6 | 69.57 | 36.13 | 680  
cross-encoder/ms-marco-electra-base | 71.99 | 36.41 | 340  
**Other models** |  |  |   
nboost/pt-tinybert-msmarco | 63.63 | 28.80 | 2900  
nboost/pt-bert-base-uncased-msmarco | 70.94 | 34.75 | 340  
nboost/pt-bert-large-msmarco | 73.36 | 36.48 | 100  
Capreolus/electra-base-msmarco | 71.23 | 36.89 | 340  
amberoad/bert-multilingual-passage-reranking-msmarco | 68.40 | 35.54 | 330  
sebastian-hofstaetter/distilbert-cat-margin_mse-T2-msmarco | 72.82 | 37.88 | 720  
  
Note: Runtime was computed on a V100 GPU.

Downloads last month
    81,498,410

Safetensors[](https://huggingface.co/docs/safetensors)

Model size

22.7M params

Tensor type

I64 

·

F32 

·

Files info

Inference Providers [NEW](https://huggingface.co/docs/inference-providers)

[ Text Ranking](/tasks/text-ranking "Learn more about text-ranking")

This model isn't deployed by any Inference Provider. [🙋 Ask for provider support](/spaces/huggingface/InferenceSupport/discussions/new?title=cross-encoder/ms-marco-MiniLM-L6-v2&description=React%20to%20this%20comment%20with%20an%20emoji%20to%20vote%20for%20%5Bcross-encoder%2Fms-marco-MiniLM-L6-v2%5D\(%2Fcross-encoder%2Fms-marco-MiniLM-L6-v2\)%20to%20be%20supported%20by%20Inference%20Providers.%0A%0A\(optional\)%20Which%20providers%20are%20you%20interested%20in%3F%20\(Novita%2C%20Hyperbolic%2C%20Together%E2%80%A6\)%0A)

##  Model tree for cross-encoder/ms-marco-MiniLM-L6-v2 [](/docs/hub/model-cards#specifying-a-base-model)

Base model

[microsoft/MiniLM-L12-H384-uncased](/microsoft/MiniLM-L12-H384-uncased)

Quantized

[cross-encoder/ms-marco-MiniLM-L12-v2](/cross-encoder/ms-marco-MiniLM-L12-v2)

Quantized

([16](/models?other=base_model:quantized:cross-encoder/ms-marco-MiniLM-L12-v2))

this model

Finetunes

[50 models](/models?other=base_model:finetune:cross-encoder/ms-marco-MiniLM-L6-v2)

Quantizations

[22 models](/models?other=base_model:quantized:cross-encoder/ms-marco-MiniLM-L6-v2)

##  Dataset used to train cross-encoder/ms-marco-MiniLM-L6-v2

#### [sentence-transformers/msmarco Viewer • Updated Jan 29 • 527M • 1.34k • 11 ](/datasets/sentence-transformers/msmarco)

##  Spaces using cross-encoder/ms-marco-MiniLM-L6-v2 100

[📊 mteb/leaderboard ](/spaces/mteb/leaderboard)[⚖️ rajivranjan3961/Rag ](/spaces/rajivranjan3961/Rag)[🚀 vishalvarkhede/career_conversation ](/spaces/vishalvarkhede/career_conversation)[🚀 saibalajiomg/customercore ](/spaces/saibalajiomg/customercore)[🏢 ahadprogamer/omni_ai ](/spaces/ahadprogamer/omni_ai)[🏛️ GSMS-B/indian-legal-rag ](/spaces/GSMS-B/indian-legal-rag)[📚 build-small-hackathon/vidyabot-gradio ](/spaces/build-small-hackathon/vidyabot-gradio)[📈 Shankar0747/RAG_Forge ](/spaces/Shankar0747/RAG_Forge) \+ 95 Spaces \+ 92 Spaces

System theme

Company

[TOS](/terms-of-service) [Privacy](/privacy) [About](/huggingface) [Careers](https://apply.workable.com/huggingface/) [](/)

Website

[Models](/models) [Datasets](/datasets) [Spaces](/spaces) [Pricing](/pricing) [Docs](/docs)
