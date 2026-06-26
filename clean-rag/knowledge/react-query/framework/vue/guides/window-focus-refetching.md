<!-- Source: github.com/TanStack/query/docs/framework\vue\guides\window-focus-refetching.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: window-focus-refetching
title: Window Focus Refetching
ref: docs/framework/react/guides/window-focus-refetching.md
replace: { '@tanstack/react-query': '@tanstack/vue-query' }
---

[//]: # 'Example'

```js
const vueQueryPluginOptions: VueQueryPluginOptions = {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
      },
    },
  },
}
app.use(VueQueryPlugin, vueQueryPluginOptions)
```

[//]: # 'Example'
[//]: # 'ReactNative'
[//]: # 'ReactNative'
