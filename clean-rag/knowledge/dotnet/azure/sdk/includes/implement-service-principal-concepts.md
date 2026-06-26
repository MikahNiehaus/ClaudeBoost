<!-- Source: github.com/dotnet/docs/docs/azure\sdk\includes\implement-service-principal-concepts.md | Tier: A | Topic: dotnet | Fetched: 2026-06-26 -->

---
ms.topic: include
ms.date: 02/12/2025
---

## Authenticate to Azure services from your app

The [Azure Identity library](/dotnet/api/azure.identity?view=azure-dotnet&preserve-view=true) provides various *credentials*&mdash;implementations of `TokenCredential` adapted to supporting different scenarios and Microsoft Entra authentication flows. The steps ahead demonstrate how to use <xref:Azure.Identity.ClientSecretCredential> when working with service principals locally and in production.
