<!-- Source: https://securityonline.info/chromadb-pre-auth-rce-vulnerability-cve-2026-45829/ | Tier: B | Topic: chromadb-security | Fetched: 2026-06-26 -->

###  Critical Alert 2 Active Exploits Detected Today 

[ CVE-2026-12569 -- PTC Windchill and FlexPLM Improper Input Validation Vulnerability -> ](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-12569) [ CVE-2026-20230 -- Cisco Unified Communications Manager Server-Side Request Forgery (SSRF) Vulnerability -> ](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-20230)

Powered by [CVE Watchtower](https://securityonline.info/cve-watchtower/)

🔔 Enable Desktop Alerts 

×

Skip to content

June 26, 2026 

  * [Linkedin](https://www.linkedin.com/in/do-van-son-892a06265/)
  * [Twitter](https://www.twitter.com/the_yellow_fall)
  * [Facebook](https://www.facebook.com/DdoS-109131310571187/)
  * [Youtube](https://www.youtube.com/c/penetrationtestingwithddos)



[Daily CyberSecurity](https://securityonline.info/)

Zero-hour alerts. Unmatched analysis.

[ ]()

Primary Menu  __

  * [Home](https://securityonline.info)
  * [CVE Watchtower](https://securityonline.info/cve-watchtower/)
  * [Cyber Criminals](https://securityonline.info/category/news/cybercriminals/)
  * [Data Leak](https://securityonline.info/category/news/dataleak/)
  * [Linux](https://securityonline.info/category/linux/)
  * [Malware](https://securityonline.info/category/news/malware/)
  * [Vulnerability](https://securityonline.info/category/news/vulnerability/)
  * [Submit Press Release](https://securityonline.info/submit-press-release/)
  * [Vulnerability Report](https://securityonline.info/category/news/vulnerability-report/)



Light/Dark Button

__

Search for:

  * [Home](https://securityonline.info/)
  * [News](https://securityonline.info/category/news/)
  * [Vulnerability Report](https://securityonline.info/category/news/vulnerability-report/)
  * [Unpatched CVSS 10 Alert: ChromaDB Python Server Grants Pre-Auth RCE via Malicious Hugging Face Models](https://securityonline.info/chromadb-pre-auth-rce-vulnerability-cve-2026-45829/)



  * [ Vulnerability Report ](https://securityonline.info/category/news/vulnerability-report/)



# Unpatched CVSS 10 Alert: ChromaDB Python Server Grants Pre-Auth RCE via Malicious Hugging Face Models

[ Do Son ](https://securityonline.info/author/ddos/) __May 21, 2026 3 minutes read

[ __ 0  ](https://securityonline.info/chromadb-pre-auth-rce-vulnerability-cve-2026-45829/#respond)

[ Add as a preferred  
source on Google  ](https://google.com/preferences/source?q=securityonline.info)

ChromaDB, one of the most widely adopted open-source vector databases engineered to enable semantic matching, retrieval-augmented generation (RAG), and memory retention in AI applications, is facing a severe security flaw. A newly released technical report from HiddenLayer has exposed a critical flaw that grants completely unauthenticated attackers full remote code execution (RCE) over vulnerable instances.

With a maximum CVSS base score of 10.0, the vulnerability threatens a significant portion of the enterprise AI landscape. Boasting over 13 million monthly pip downloads and more than 27,500 GitHub stars, ChromaDB's footprint stretches across prominent tech organizations and Fortune 500 giants alike, including publicly documented production dependencies at Mintlify, Weights & Biases, Factory AI, Capital One, and United Healthcare.

The underlying mechanics of the vulnerability, tracked as [CVE-2026-45829](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-45829), trace back to a classic architectural flaw: performing unsafe, user-controlled initializations before enforcing identity validation gates.

When developers interact with ChromaDB's built-in API documentation page, the endpoint for creating new data collections (POST /api/v2/tenants/{tenant}/databases/{db}/collections) is explicitly labeled as an authenticated route. Under standard operations, this design reassures security teams that any unauthenticated external requests will be promptly dropped at the perimeter.

However, HiddenLayer's reverse-engineering efforts exposed a fatal sequence of operations within the database's Python FastAPI server implementation. As HiddenLayer [explains](https://www.hiddenlayer.com/research/chromatoast-served-pre-auth) in the report:

"ChromaDB's Python FastAPI server can instantiate user-controlled embedding function settings before checking access permissions. This allows an unauthenticated attacker with HTTP API access to trigger remote code execution (RCE) by supplying a malicious Hugging Face model reference, giving the attacker full control of the server process."

By passing a custom model configuration inside the embedding_function metadata block of the HTTP request, an attacker can trick the server into stepping away from the verification check. The server reads the configuration, reaches out to a public registry to pull down the model, and initializes the execution environment before ever evaluating whether the bearer token or session cookie is valid.

The core catalyst that transforms this authentication ordering bypass into full system compromise is how the Python ecosystem interacts with public model registries like Hugging Face.

Many modern machine learning models require custom configuration blocks or execution scripts to parse input data properly. To accommodate this, Python clients support the parameter trust_remote_code=True, which authorizes the application to dynamically download and execute arbitrary Python code packaged directly inside the remote model repository.

By supplying an unauthenticated request pointing to a poisoned Hugging Face repository containing an embedded exploit payload, the attacker forces the underlying ChromaDB server process to pull down and reflectively execute the malicious code natively. HiddenLayer highlights that the flaw relies on a compounding failure of design principles:

"The root cause of CVE-2026-45829 (CVSS 10) is two independent failures that compound each other. The server trusts client-supplied model identifiers without restriction, and acts on that trust before authenticating the user sending the request."

The vulnerability is confirmed to have been introduced during a major feature overhaul in version 1.0.0 and remains entirely unpatched across subsequent updates up to the current 1.5.8 build.

To quantify the real-world impact of the bug, HiddenLayer conducted a global scanning sweep of internet-facing database infrastructure using the Shodan search engine. The resulting exposure metrics are deeply concerning for enterprise security teams:

"The vulnerability was introduced in version 1.0.0 and is unpatched as of version 1.5.8. Of internet-exposed ChromaDB instances we discovered via Shodan, 73% are running version 1.0.0 or later, the version range in which the vulnerable feature exists."

This means that nearly three-quarters of all publicly accessible ChromaDB deployments worldwide are currently sitting entirely unprotected against a single-request zero-day exploit execution vector.

### Related coverage

  * [Copy Fail: Public PoC and Full Details Disclosed for the 732-Byte Linux Root Exploit (CVE-2026-31431)](https://securityonline.info/linux-kernel-copy-fail-root-exploit-poc-public-disclosure/)
  * [High-Severity Flaws in Sunshine for Windows Allow Privilege Escalation](https://securityonline.info/high-severity-flaws-in-sunshine-for-windows-allow-privilege-escalation/)
  * [The 30-Year Glitch: RCE and ARM Exploits Uncovered in libpng Reference Library](https://securityonline.info/libpng-vulnerability-rce-arm-neon-cve-2026-33636-cve-2026-33416/)
  * [Critical CISA Advisory Unmasks Severe Flaws in EV2GO Charging Networks](https://securityonline.info/critical-cisa-advisory-unmasks-severe-flaws-in-ev2go-charging-networks/)
  * [CISA Adds Three D-Link Flaws to KEV Catalog: EOL IP Cameras Under Active Exploitation](https://securityonline.info/cisa-adds-three-d-link-flaws-to-kev-catalog-eol-ip-cameras-under-active-exploitation/)



#### Support Our Threat Intelligence

If you find our CVE report and cybersecurity news helpful, consider supporting our work.

[ Buy Me a Coffee ](https://buymeacoffee.com/ddos/membership) [ PayPal ](https://securityonline.info/become-a-contributor/)

Crypto 

USDT (TRC20):

TN8BdV8cp4T1Cd28gK9qTAnZknzzuwyUtm Copy

USDT (ERC20):

0x3725e1a7d3bc5765499fa6aaafe307fabcd75bce Copy

Share this article:

[ Facebook](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fsecurityonline.info%2Fchromadb-pre-auth-rce-vulnerability-cve-2026-45829%2F)[ Post](https://twitter.com/intent/tweet?url=https%3A%2F%2Fsecurityonline.info%2Fchromadb-pre-auth-rce-vulnerability-cve-2026-45829%2F&text=Unpatched+CVSS+10+Alert%3A+ChromaDB+Python+Server+Grants+Pre-Auth+RCE+via+Malicious+Hugging+Face+Models)[ LinkedIn](https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fsecurityonline.info%2Fchromadb-pre-auth-rce-vulnerability-cve-2026-45829%2F&title=Unpatched+CVSS+10+Alert%3A+ChromaDB+Python+Server+Grants+Pre-Auth+RCE+via+Malicious+Hugging+Face+Models)[ Telegram](https://t.me/share/url?url=https%3A%2F%2Fsecurityonline.info%2Fchromadb-pre-auth-rce-vulnerability-cve-2026-45829%2F&text=Unpatched+CVSS+10+Alert%3A+ChromaDB+Python+Server+Grants+Pre-Auth+RCE+via+Malicious+Hugging+Face+Models) Copy Link

Written by

@DdoS · Security Researcher

#### Do Son

Do Son is the Founder and Editor of SecurityOnline.info. Working in cybersecurity since 2013, he reports on vulnerabilities, malware, and emerging threats, providing timely analysis to help organizations and individuals stay ahead of evolving risks.

[](mailto:the.yellow.fall@gmail.com "Email Me")[](https://securityonline.info/ "Website")[](https://x.com/the_yellow_fall "Twitter")[](https://www.linkedin.com/in/do-van-son-892a06265/?lipi=urnlipaged_flagship3_feedIhFD4byFQxOw6qPUBwqsnw "LinkedIn")[](https://www.youtube.com/c/penetrationtestingwithddos "YouTube")

Tags: [ChromaDB](https://securityonline.info/tag/chromadb/) [CVE-2026-45829](https://securityonline.info/tag/cve-2026-45829/) [Cyber Security](https://securityonline.info/tag/cyber-security/) [FastAPI](https://securityonline.info/tag/fastapi/) [HiddenLayer](https://securityonline.info/tag/hiddenlayer/) [Hugging Face](https://securityonline.info/tag/hugging-face/) [infosec](https://securityonline.info/tag/infosec/) [Machine Learning Security](https://securityonline.info/tag/machine-learning-security/) [Pre-Authentication RCE](https://securityonline.info/tag/pre-authentication-rce/) [trust_remote_code](https://securityonline.info/tag/trust_remote_code/) [Vector Database](https://securityonline.info/tag/vector-database/)

### Leave a Reply [Cancel reply](/chromadb-pre-auth-rce-vulnerability-cve-2026-45829/#respond)

You must be [logged in](https://securityonline.info/wp-login.php?redirect_to=https%3A%2F%2Fsecurityonline.info%2Fchromadb-pre-auth-rce-vulnerability-cve-2026-45829%2F) to post a comment.

## Search

## Translation

CVE WATCHTOWER

🚨

Receive alerts for vulnerabilities being **exploited in the wild**.

⚡

Get notified instantly when a **Proof of Concept (PoC)** exploit is published.

🔍

Access critical info on vulnerabilities even when marked as **"RESERVED"**.

🧠

Insights powered by decades of expertise and **global intelligence sources**.

🎯

Customize alerts with up to **10 keywords** for your specific tech stack.

📊

Export the raw CVE database for **SIEM integration** and reporting.

[Upgrade Package](https://securityonline.info/cve-watchtower/?upgrade=true)

### 🚨 Active Exploits in the Wild

  * [CVE-2026-12569](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-12569)

A critical remote code execution (RCE) vulnerability has been reported in PTC Windchill PDMlink and PTC FlexPLM. The...

  * [CVE-2026-20230](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-20230)CVSS 8.6

A vulnerability in Cisco Unified Communications Manager (Unified CM) and Cisco Unified Communications Manager Session Management Edition (Unified...

  * [CVE-2026-28496](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-28496-admin&source=ADMIN)CVSS 9.4

FOSSBilling is a free, open-source billing and client management system. Versions prior to 0.8.0 have a Server-Side Template...

  * [CVE-2026-21509](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-21509)CVSS 7.8

Reliance on untrusted inputs in a security decision in Microsoft Office allows an unauthorized attacker to bypass a...

  * [CVE-2026-34908](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-34908)CVSS 10.0

A malicious actor with access to the network could exploit an Improper Access Control vulnerability found in UniFi...

  * [CVE-2026-34909](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-34909)CVSS 10.0

A malicious actor with access to the network could exploit a Path Traversal vulnerability found in UniFi OS...

  * [CVE-2026-34910](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-34910)CVSS 10.0

A malicious actor with access to the network could exploit an Improper Input Validation vulnerability found in UniFi...

  * [CVE-2025-67038](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2025-67038)CVSS 9.8

An issue was discovered in Lantronix EDS5000 2.1.0.0R3. The HTTP RPC module executes a shell command to write...

  * [CVE-2024-23692](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2024-23692)CVSS 9.8

Rejetto HTTP File Server, up to and including version 2.3m, is vulnerable to a template injection vulnerability. This...

  * [CVE-2026-48907](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-48907)

A vulnerability in the JCE editor extension for Joomla allows the creation of new editor profiles for unauthenticated...




[Powered by CVE Watchtower](https://securityonline.info/cve-watchtower/?upgrade=true)

#### 🔴 Live Critical Threats

  * [CVE-2026-55166CVSS 9.9Lemur 1.9.0: any SSO-authenticated user achieves AWS IAM compromise and permanent PKI...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-55166)
  * [CVE-2025-71338CVSS 10.0Flowise contains a path traversal vulnerability in the /api/v1/document-store/loader/process endpoint that allows...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2025-71338)
  * [CVE-2025-71336CVSS 9.8Flowise before 3.0.6 (affected versions 2.2.7-patch.1 and earlier) contains an unsandboxed remote...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2025-71336)
  * [CVE-2025-71334CVSS 9.8Flowise before 3.0.6 (affected versions 2.2.8 and earlier) contains an arbitrary file...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2025-71334)
  * [CVE-2025-71327CVSS 9.1Flowise contains an authentication bypass vulnerability in the unprotected /api/v1/account/register endpoint that...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2025-71327)
  * [CVE-2026-40702CVSS 9.4WebSocket endpoints lack proper authentication mechanisms, enabling attackers to impersonate charging stations....](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-40702)
  * [CVE-2026-56445CVSS 9.1The qrscp application's C-STORE handler uses a specific instance from attacker-supplied DICOM...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-56445)
  * [CVE-2026-57700CVSS 10.0Unrestricted Upload of File with Dangerous Type vulnerability in Daan.Dev OMGF Pro...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-57700)
  * [CVE-2026-54089CVSS 9.1File Browser is a file managing interface for uploading, deleting, previewing, renaming,...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-54089)
  * [CVE-2026-56786CVSS 9.8RTKLIB through 2.4.3 contains an out-of-bounds write vulnerability in decode_type1033 function that...](https://securityonline.info/cve-watchtower/?cve_detail=CVE-2026-56786)



Powered by [CVE WATCHTOWER](https://securityonline.info/cve-watchtower/?upgrade=true)

**Our Websites**
* [Penetration Testing Tools](https://meterpreter.org/)
* [The Daily Information Technology](https://securityexpress.info/)

## Daily CyberSecurity

  * [About SecurityOnline.info](https://securityonline.info/about-us/)
  * [Advertise with us](https://securityonline.info/advertise-on-securityonline-cybersecurity/)
  * [Announcement](https://securityonline.info/category/announcement/)
  * [Contact](https://securityonline.info/contact-us/)
  * [Contributor Register](https://securityonline.info/register-supporter/)
  * [Login](https://securityonline.info/wp-login.php)



  * **[About SecurityOnline.info](https://securityonline.info/about-us/)**
  * **[Advertise on SecurityOnline.info](https://securityonline.info/advertise-on-securityonline-cybersecurity/)**
  * [**Contact Us**](https://securityonline.info/contact-us/)



When you purchase through links on our site, we may earn an affiliate commission. [**Here’s how it works**](https://securityonline.info/affiliate-advertising-disclosure/)

  * [Disclaimer](https://securityonline.info/disclaimer/)
  * [Privacy Policy](https://securityonline.info/privacy-policy/)
  * [DMCA NOTICE](https://securityonline.info/dmca-notice/)



  * [Linkedin](https://www.linkedin.com/in/do-van-son-892a06265/)
  * [Twitter](https://www.twitter.com/the_yellow_fall)
  * [Facebook](https://www.facebook.com/DdoS-109131310571187/)
  * [Youtube](https://www.youtube.com/c/penetrationtestingwithddos)



© 2017 - 2026 Daily CyberSecurity. All Rights Reserved. 
