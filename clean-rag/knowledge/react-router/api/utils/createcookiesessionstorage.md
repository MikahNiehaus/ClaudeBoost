<!-- Source: github.com/remix-run/react-router/docs/api\utils\createCookieSessionStorage.md | Tier: A | Topic: react-router | Fetched: 2026-06-26 -->

---
title: createCookieSessionStorage
---

# createCookieSessionStorage

[MODES: framework, data]

## Summary

[Reference Documentation ↗](https://api.reactrouter.com/v7/functions/react-router.createCookieSessionStorage.html)

Creates and returns a SessionStorage object that stores all session data
directly in the session cookie itself.

This has the advantage that no database or other backend services are
needed, and can help to simplify some load-balanced scenarios. However, it
also has the limitation that serialized session data may not exceed the
browser's maximum cookie size. Trade-offs!
