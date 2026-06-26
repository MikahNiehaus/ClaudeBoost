<!-- Source: github.com/remix-run/react-router/docs/api\utils\href.md | Tier: A | Topic: react-router | Fetched: 2026-06-26 -->

---
title: href
---

# href

[MODES: framework]

## Summary

[Reference Documentation ↗](https://api.reactrouter.com/v7/functions/react-router.href.html)

Returns a resolved URL path for the specified route.

```tsx
const h = href("/:lang?/about", { lang: "en" })
// -> `/en/about`

<Link to={href("/products/:id", { id: "abc123" })} />
```
