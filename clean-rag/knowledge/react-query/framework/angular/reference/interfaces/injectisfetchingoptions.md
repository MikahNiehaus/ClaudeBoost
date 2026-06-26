<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\interfaces\InjectIsFetchingOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: InjectIsFetchingOptions
title: InjectIsFetchingOptions
---

# Interface: InjectIsFetchingOptions

Defined in: [inject-is-fetching.ts:13](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-is-fetching.ts#L13)

## Properties

### injector?

```ts
optional injector: Injector;
```

Defined in: [inject-is-fetching.ts:19](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-is-fetching.ts#L19)

The `Injector` in which to create the isFetching signal.

If this is not provided, the current injection context will be used instead (via `inject`).
