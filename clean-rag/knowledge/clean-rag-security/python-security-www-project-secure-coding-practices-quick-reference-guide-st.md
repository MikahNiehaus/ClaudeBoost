<!-- Source: https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/stable-en/ | Tier: A | Topic: python-security | Fetched: 2026-06-26 -->

For full functionality of this site it is necessary to enable JavaScript. Here are the [ instructions how to enable JavaScript in your web browser](http://turnonjs.com/).

__ [ ](https://owasp.org/)

[ ](https://owasp.org/)

[__Store](https://owasp.org/store) [Donate](https://owasp.org/donate?reponame=www-project-secure-coding-practices-quick-reference-guide&title=Secure+Coding+Practices) [Join](https://owasp.org/membership)

This website uses cookies to analyze our traffic and only share that information with our analytics partners.

Accept

x

[__Store](https://owasp.org/store)

[Donate](https://owasp.org/donate?reponame=www-project-secure-coding-practices-quick-reference-guide&title=Secure+Coding+Practices)

[Join](https://owasp.org/membership)

OWASP Secure Coding Practices - Quick Reference Guide

# Secure Coding Practices




[Home](/www-project-secure-coding-practices-quick-reference-guide/) > [Stable-en](/www-project-secure-coding-practices-quick-reference-guide/stable-en/)

## Table of Contents

### 1\. [Introduction](/www-project-secure-coding-practices-quick-reference-guide/stable-en/01-introduction/05-introduction.html)

### 2\. [Checklist](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist.html)

### Appendix A. [Overview](/www-project-secure-coding-practices-quick-reference-guide/stable-en/03-appendices/03-overview.html)

### Appendix B. [Glossary](/www-project-secure-coding-practices-quick-reference-guide/stable-en/03-appendices/05-glossary.html)

### Appendix C. [External References](/www-project-secure-coding-practices-quick-reference-guide/stable-en/03-appendices/07-references.html)




* * *

[Watch](https://github.com/owasp/www-project-secure-coding-practices-quick-reference-guide/subscription) [Star](https://github.com/owasp/www-project-secure-coding-practices-quick-reference-guide)

**The OWASP ® Foundation** works to improve the security of software through its community-led open source software projects, hundreds of chapters worldwide, tens of thousands of members, and by hosting local and global conferences. 

## [Secure Coding Practice Quick-reference Guide](/www-project-secure-coding-practices-quick-reference-guide/stable-en/)

  * [1\. Introduction](/www-project-secure-coding-practices-quick-reference-guide/stable-en/01-introduction/05-introduction)
  * [2\. Checklist](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist)
  * [2.1 Input validation](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#input-validation)
  * [2.2 Output encoding](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#output-encoding)
  * [2.3 Authentication and password management](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#authentication-and-password-management)
  * [2.4 Session management](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#session-management)
  * [2.5 Access control](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#access-control)
  * [2.6 Cryptographic practices](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#cryptographic-practices)
  * [2.7 Error handling and logging](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#error-handling-and-logging)
  * [2.8 Data protection](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#data-protection)
  * [2.9 Communication security](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#communication-security)
  * [2.10 System configuration](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#system-configuration)
  * [2.11 Database security](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#database-security)
  * [2.12 File management](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#file-management)
  * [2.13 Memory management](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#memory-management)
  * [2.14 General coding practices](/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-checklist/05-checklist#general-coding-practices)
  * [Appendix A. Overview](/www-project-secure-coding-practices-quick-reference-guide/stable-en/03-appendices/03-overview)
  * [Appendix B. Glossary](/www-project-secure-coding-practices-quick-reference-guide/stable-en/03-appendices/05-glossary)
  * [Appendix C. External references](/www-project-secure-coding-practices-quick-reference-guide/stable-en/03-appendices/07-references)



### Upcoming OWASP Global Events

## Corporate Supporters

[Become a corporate supporter](https://owasp.org/supporters)

[__](https://github.com/OWASP/)[__](https://owasp.org/slack/invite)[__](https://www.facebook.com/OWASPFoundation) [](https://infosec.exchange/@owasp) [](https://twitter.com/owasp) [__](https://www.linkedin.com/company/owasp/)[__](https://www.youtube.com/user/OWASPGLOBAL)

  * [HOME](https://owasp.org/)
  * [PROJECTS](https://owasp.org/projects/)
  * [CHAPTERS](https://owasp.org/chapters/)
  * [EVENTS](https://owasp.org/events/)
  * [ABOUT](https://owasp.org/about/)
  * [PRIVACY](https://owasp.org/www-policy/operational/privacy)
  * [SITEMAP](https://owasp.org/sitemap/)
  * [CONTACT](https://owasp.org/contact/)



OWASP, the OWASP logo, and Global AppSec are registered trademarks and AppSec Days, AppSec California, AppSec Cali, SnowFROC, and LASCON are trademarks of the OWASP Foundation, Inc. Unless otherwise specified, all content on the site is Creative Commons Attribution-ShareAlike v4.0 and provided without warranty of service or accuracy. For more information, please refer to our [General Disclaimer](/www-policy/operational/general-disclaimer.html). OWASP does not endorse or recommend commercial products or services, allowing our community to remain vendor neutral with the collective wisdom of the best minds in software security worldwide. Copyright 2024, OWASP Foundation, Inc. 
