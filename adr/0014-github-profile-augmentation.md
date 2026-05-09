# ADR-0014: GitHub Profile Augmentation

**Date:** 2026-05-09
**Status:** Active
**Context:** Comparison of jthorvaldur GitHub presence against ruvnet (one of the highest-volume public GitHub users) to identify augmentation opportunities.

---

## Background

ruvnet (rUv) is a high-output GitHub user with 7,650 followers, 174 public repos, 338 gists, 82 Rust crates, and 109K+ aggregate stars. His profile is explicitly designed as a "prior art defense" — maximum surface area across agentic AI. Two mega-repos (RuView at 52K stars, ruflo at 48K) drive most visibility.

jthorvaldur has a 61-repo ecosystem with real depth (2M+ vectors, CME gateway, production trading platform, legal corpus) but only 11 public repos, 12 followers, zero stars, and — until today — no profile README.

## Comparative Analysis

### ruvnet profile strengths
- **500-line profile README** — categorized project catalog with hero image, 80+ projects in 12 categories, emoji tags for scanning
- **CI/CD badges everywhere** — 20 workflows on ruflo alone; automated releases (1,480+), status badges, quality gates
- **Clear thematic brand** — "Agentic AI" is the unified identity across all repos
- **GitHub as primary publishing medium** — gists for small work, repos for everything, profile page replaces personal website
- **Contribution volume** — bot-assisted development (`claude` user as contributor), GitHub Actions automation drives commit counts
- **Published packages** — 82 Rust crates on crates.io adds credibility outside GitHub
- **Org separation** — `agenticsorg` org separates platform repos from personal experiments

### ruvnet profile weaknesses
- **Breadth over depth** — many repos are thin; the volume strategy optimizes for coverage not substance
- **Bot-driven metrics** — `claude` bot (585 commits) and `github-actions[bot]` (529 commits) inflate contributor counts
- **Two repos = 92% of stars** — fragile visibility structure
- **No academic credentials** — "Unicorn Breeder" bio vs. actual expertise signaling
- **Clone-source identity** — optimized for being forked, not for demonstrating deep technical work

### jthorvaldur strengths (underexposed)
- **Real credentials** — Ph.D. Dartmouth, ORCID, Google Scholar, quant PM trajectory
- **Production infrastructure** — CME order gateway (Go), FIX protocol, trading platform suite
- **Genuine data scale** — 2M+ vectors, 1.7M legal document corpus, 244K email/PDF vectors
- **Governance innovation** — policy-orchestrator as multi-repo control plane is novel
- **Security-first deployment** — AES-256-GCM encrypted Pages, PBKDF2 100K iterations, 3 password zones
- **Quality deployed sites** — BulldogDerm (evidence-checked, interactive viz), morpheme.page (15 visualizations)

### jthorvaldur weaknesses (addressed)
- **No profile README** — FIXED: created `jthorvaldur/jthorvaldur` with categorized project table
- **Missing repo metadata** — FIXED: added topics/descriptions to sovereign-legal, dna-rights, coherence-research
- **Odd public repo selection** — 4 of 11 repos were legal/sovereign; needs rebalancing with quant/AI repos
- **Zero stars/forks** — repos appear newly public; no external community engagement yet
- **No CI badges** — no visible build status on any repo
- **No releases** — no tagged versions on any repo
- **Forks without differentiation** — puffin has 299 commits but no visible value-add over upstream

## Decisions

### Completed (2026-05-09)

1. **Created profile README** — `jthorvaldur/jthorvaldur` with:
   - SVG banner (dark theme, conformal-inspired design)
   - Categorized project tables: Quant Finance, AI/Agents, Legal, Infrastructure, Math Art
   - Tech stack summary
   - Deployed sites index
   - Links to credentials (ORCID, Google Scholar, conformalmaps.com)

2. **Updated repo metadata** — Added descriptions and topics to:
   - `sovereign-legal` — 6 topics (legal-analysis, jurisdiction, python, sovereignty, court-authority, legal-framework)
   - `dna-rights` — 6 topics (natural-rights, jurisdiction, python, legal-framework, parentage, biological-rights)
   - `coherence-research` — 6 topics (coherence, instability-detection, python, dynamical-systems, physics, metrics)
   - `jthorvaldur` — description + profile/readme topics

### Recommended next steps

#### High priority

3. **Make 2-3 strategic repos public** — Candidates:
   - `cortex` — AI agent coordination (demonstrates AI infrastructure depth)
   - `alpha_research` or `ts_embed` — quant signal work (demonstrates finance expertise)
   - `vector-lab` — vector DB work (demonstrates data infrastructure)
   - Re-evaluate: making even one quant repo public would shift the profile's character from legal-heavy to finance/AI-heavy

4. **Add CI workflows to public repos** — At minimum:
   - `policy-orchestrator`: run `devctl audit` and `devctl policy` on push
   - `bulldogs`: already has deploy workflow; add linting
   - `legal-tax-ops`: add Python lint + type check
   - Add badge rows to each repo README

5. **Create tagged releases** — At least for:
   - `policy-orchestrator` (v1.0 milestone: 61 repos registered, all commands working)
   - `vpin` (stable research tool)
   - `bulldogs` (live site, evidence-checked)

#### Medium priority

6. **Publish gists** — Non-sensitive scripts from `~/bin` and `devctl` subcommands. Gists appear in GitHub search and on profile.

7. **Augment Pages landing page** — Add a "GitHub Repos" section linking to public repos. Currently the Pages site and GitHub profile are disconnected.

8. **Consider GitHub org** — A `thorarinson-systems` or similar org for infrastructure repos signals platform-level work vs. personal experiments.

9. **Add contribution activity** — File issues or PRs on upstream projects (Qdrant, anthropic SDK, uv) to appear in the community graph.

#### Low priority / Ongoing

10. **README quality audit** — Run `devctl audit-readmes` across all public repos. Each needs:
    - One-paragraph description
    - Install/usage section
    - Badge row (CI, Python version, license)
    - Screenshot or demo link where applicable

11. **Star accumulation** — Write about work on relevant forums/communities. The bulldogs project alone could attract veterinary community attention. The vpin implementation is cited in academic papers.

12. **Differentiate forks** — puffin (299 commits over upstream) should have a "What's different" section in its README explaining the value-add.

## CI, Releases, and Gists as policy-orchestrator concerns

The ruvnet comparison surfaced that CI badges, tagged releases, and published gists are not cosmetic — they're process enforcement. This is exactly what policy-orchestrator exists to do. The gap isn't "we should add badges for looks," it's "our governance system should enforce the same standards externally that it enforces internally."

### Concrete policy-orchestrator extensions

1. **`devctl audit-ci`** — Check that every public repo has at least one GitHub Actions workflow. Flag repos with no CI as policy violations (WARN, not ERROR).

2. **`devctl audit-readmes`** — Check that every public repo has:
   - Description > 10 words
   - At least one badge (CI, license, Python version)
   - Install/usage section
   - Flag missing items as WARN

3. **`devctl audit-releases`** — Check that active public repos have at least one tagged release. Repos with 10+ commits and no release get a WARN.

4. **Release automation** — Add `release-please` or `semantic-release` to policy-orchestrator and key public repos. Auto-tag on merge to main. The control plane should dogfood this first.

5. **Gist publishing pipeline** — Non-sensitive scripts from `~/bin` and standalone `devctl` subcommands could be published as gists. Gists appear in GitHub search, on the profile, and demonstrate breadth without requiring full repos. A `devctl publish-gist` command could handle this.

6. **Public repo readiness gate** — Before any repo goes from private to public, require:
   - CI workflow present
   - README meets minimum quality bar
   - No secrets in git history (`devctl secrets` clean)
   - `.gitignore` covers `.env`, credentials
   - License file present
   - Description and topics set on GitHub

### Making repos public — the work ahead

Candidates for public visibility (each needs the readiness gate above):
- `cortex` — AI agent coordination (strongest AI signal)
- `vector-lab` — vector DB work (demonstrates data infrastructure)
- `alpha_research` or `ts_embed` — quant signal (shifts profile from legal-heavy to finance/AI)
- `llm-router` — LLM routing (practical, reusable tool)
- `positions` — already deployed publicly, repo could match

Each requires: secrets audit, README rewrite, CI workflow, license, and topic tagging. This is non-trivial per-repo work, but the readiness gate policy means it only needs to be defined once in policy-orchestrator.

## What NOT to do

- **Don't inflate volume.** ruvnet's strategy is explicitly "publish first, patent-block later." That's a specific legal strategy, not a universal best practice. Quality and depth are the differentiator here.
- **Don't make everything public.** Trading infrastructure, legal analysis, and client data repos must stay private. The strategy is selective curation.
- **Don't add branding gimmicks.** "Unicorn Breeder" works for ruvnet's brand; "Nonlinear systems physicist -> quant PM" is stronger for this profile.
- **Don't chase star count.** Two mega-repos with inflated stars (bot contributions, aggressive marketing) is a fragile visibility structure. Steady, credible growth from real community engagement is more durable.

## Metrics to track

- Profile views (GitHub Insights)
- Stars on public repos
- Fork count (especially vpin, policy-orchestrator)
- Follower growth
- Contribution graph density

---

**Why this belongs here:** Profile strategy is a cross-repo governance concern — it affects which repos are public, how they're documented, and what CI/CD they need.
**What system reads it:** Human review; informs `devctl audit` scope expansion.
**What happens if it changes:** Update profile README and repo visibility accordingly.
