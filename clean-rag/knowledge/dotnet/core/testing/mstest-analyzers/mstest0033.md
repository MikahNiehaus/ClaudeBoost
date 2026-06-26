<!-- Source: github.com/dotnet/docs/docs/core\testing\mstest-analyzers\mstest0033.md | Tier: A | Topic: dotnet | Fetched: 2026-06-26 -->

---
title: "MSTEST0033: Non-nullable reference not initialized suppressor."
description: "Learn about code suppressor MSTEST0033: Non-nullable reference not initialized suppressor."
ms.date: 08/09/2024
f1_keywords:
- MSTEST0033
- NonNullableReferenceNotInitializedSuppressor
helpviewer_keywords:
- NonNullableReferenceNotInitializedSuppressor
- MSTEST0033
author: Evangelink
ms.author: amauryleve
---
# MSTEST0033: Non-nullable reference not initialized suppressor

| Property                            | Value                                    |
|-------------------------------------|------------------------------------------|
| **Rule ID**                         | MSTEST0033                               |
| **Title**                           | Suppress CS8618 for TestContext property |
| **Category**                        | Suppressor                               |
| **Introduced in version**           | 3.6.0                                    |

## Suppressor description

Suppress the [CS8618: Non-nullable variable must contain a non-null value when exiting constructor. Consider declaring it as nullable.](../../../csharp/language-reference/compiler-messages/nullable-warnings.md#nonnullable-reference-not-initialized) diagnostic for the `TestContext` property as its value is always initialized by the MSTest framework.

## When to disable suppressor

.NET suppressors cannot be disabled.
