# Original Request (verbatim)

Where they come up with a detailed plan on how to make lot properly be more commutative instead of just deciding what to do I wanted so that way it would never make an architectural change without at least consulting me first For example if it makes an end point it would need to talk to me about validation middle security stuff like that it would make suggestions what it wants to do when I could add to it or talk about it you also need to do research to make sure you're doing this properly and then also fully understand the project to make sure you're implementing it correctly it should probably also be a mandatory look that this will happen no matter what unless it explicitly given free rome There should also be a free roam slash command and also commutative slash command but probably give them better names I'm not sure do a lot of thinking into this and also switch to a higher model or use an AI system that there's a higher model to do this that way you are leading the absolute best

## Clarifications from user during planning

1. **Mode names chosen:** CONSULT (default) / AUTO (bypass).
2. **Approval scope:** Remember within session — approved architectural choices logged to a session scratchpad; Claude only re-consults when a new axis appears.
3. **Consultation is additive, not gatekeeping:** Claude should present RAG-required standards (validation, security, logging) as already-handled, and invite the user to ADD constraints on top. Example the user gave: Claude says "using ORM for SQL injection protection"; user adds "also cap size, also ASCII-only". Consultation is NOT asking whether to validate — it's asking what extra constraints to layer on.
4. **RAG always followed:** the mode never bypasses RAG knowledge loading or existing standards enforcement.
