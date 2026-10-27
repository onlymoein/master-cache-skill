# Caching Security, Observability, Debugging & Verification (state as of Oct 2026)

Research note on method: in this sandbox, WebFetch could not reach external hosts (DNS/egress blocked). Findings come from WebSearch result summaries, which mostly point to primary sources (RFCs, vendor docs, NVD/GitHub/GitLab advisories, PortSwigger), plus well-known RFC text cited directly. Where only secondary or aggregator sources were available, this is flagged. Attack classes are described at the level a developer needs to recognize and verify them on their own systems. Weaponized payload lists are deliberately left out.

---

## Q1. Shared-cache attack classes: web cache poisoning, web cache deception, CPDoS, and recent framework CVEs

### Takeaway
Almost every shared-cache attack comes from a **discrepancy**: between what the cache keys on and what the origin uses to build the response (poisoning), between how the cache and the origin parse a URL (deception), or between which requests each one accepts (CPDoS / error caching). From 2024 to 2026 a steady run of framework-level CVEs (Next.js, React Router/Remix, Nuxt) shows that "the framework handles caching" is not a safe assumption for self-hosted apps behind a CDN. Patch levels and explicit cache keys and headers matter.

### Cited Findings

**Foundational research (what the skill should name and explain)**
- PortSwigger (James Kettle) set out the modern model of web cache poisoning in "Practical Web Cache Poisoning": find **unkeyed inputs** (for example headers such as `X-Forwarded-Host`) that change the response but are not part of the cache key, so a response built from attacker input gets stored and served to everyone. — [PortSwigger Research: Practical Web Cache Poisoning](https://portswigger.net/research/practical-web-cache-poisoning)
-