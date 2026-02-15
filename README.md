# 🌐 Global Infrastructure Intelligence Digest

**Center of Excellence: Policy, Finance & Delivery**

Automated daily intelligence briefing on global infrastructure policy, project finance, and delivery innovation. 85+ sources. Six domains. Zero cost.

**Live:** [politico94.github.io/global-infra-digest](https://politico94.github.io/global-infra-digest)

## Coverage

| Section | Scope |
|---------|-------|
| Multilateral & Development Finance | World Bank, ADB, AIIB, EIB, EBRD, AfDB, NDB, OECD, G20 |
| Major Economy Infrastructure Policy | US, EU, UK, India, China, Australia, Japan |
| Canada Infrastructure Watch | Infrastructure Canada, CIB, IO, PBO, FAO, C.D. Howe, CCPPP |
| P3s, Project Finance & Delivery | PPP Knowledge Lab, GIIA, procurement, alternative delivery |
| Climate Resilience & Sustainability | Climate bonds, IEA, IRENA, green finance, C40 |
| Emerging Tech & Smart Infrastructure | Digital twins, BIM, smart cities, construction tech |

## Architecture

```
GitHub Actions (cron 6:30 AM ET)
  → pipeline.py fetches 85+ RSS feeds & web sources
  → Keyword relevance scoring + deduplication
  → Rule-based categorization into 6 sections
  → Jinja2 renders professional HTML
  → Deploys to GitHub Pages
```

**No API keys. No subscriptions. $0/day.**

## Setup

1. Create repo `global-infra-digest` on GitHub
2. Upload all files
3. Create `.github/workflows/daily-digest.yml` manually via GitHub UI
4. Settings → Pages → Deploy from branch → `gh-pages` / `/ (root)`
5. Actions → Run workflow

## Disclaimer

Automated intelligence digest, not journalism. All items link to primary sources. Verify before acting.
