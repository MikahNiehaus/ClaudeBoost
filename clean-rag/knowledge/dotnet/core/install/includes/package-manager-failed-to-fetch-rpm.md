<!-- Source: github.com/dotnet/docs/docs/core\install\includes\package-manager-failed-to-fetch-rpm.md | Tier: A | Topic: dotnet | Fetched: 2026-06-26 -->

---
author: adegeo
ms.author: adegeo
ms.date: 11/14/2023
ms.topic: include
---

While installing the .NET package, you may see an error similar to `signature verification failed for file 'repomd.xml' from repository 'packages-microsoft-com-prod'`. Generally speaking, this error means that the package feed for .NET is being upgraded with newer package versions, and that you should try again later. During an upgrade, the package feed should not be unavailable for more than 2 hours. If you continually receive this error for more than 2 hours, please file an issue at <https://github.com/dotnet/core/issues>.
