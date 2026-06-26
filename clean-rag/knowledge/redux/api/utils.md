<!-- Source: github.com/reduxjs/redux/docs/api\utils.md | Tier: A | Topic: redux | Fetched: 2026-06-26 -->

---
id: utils
title: Additional Utilities
hide_title: true
description: 'API > utils: Additional utility functions'
---

&nbsp;

# Utility Functions

The Redux core exports additional utility functions for reuse.

## `isAction`

Returns true if the parameter is a valid Redux action object (a plain object with a string `type` field).

This also serves as a TypeScript type predicate, which will narrow the TS type to `Action<string>`.

## `isPlainObject`

Returns true if the value appears to be a plain JS object.
