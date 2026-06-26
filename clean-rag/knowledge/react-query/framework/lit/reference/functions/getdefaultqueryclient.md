<!-- Source: github.com/TanStack/query/docs/framework\lit\reference\functions\getDefaultQueryClient.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: getDefaultQueryClient
title: getDefaultQueryClient
---

# Function: getDefaultQueryClient()

```ts
function getDefaultQueryClient(): QueryClient | undefined;
```

Defined in: [packages/lit-query/src/context.ts:72](https://github.com/TanStack/query/blob/main/packages/lit-query/src/context.ts#L72)

Returns the registered default `QueryClient`, if exactly one default client is
available.

## Returns

`QueryClient` \| `undefined`

The default query client, or `undefined` when there is no registered
client or more than one registered client.
