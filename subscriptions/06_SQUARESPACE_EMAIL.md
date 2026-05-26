# Squarespace + Email Infrastructure Upgrade

**Current cost: $444/yr ($276 Squarespace Business + $168 Google Workspace)**
**Potential cost: $144-204/yr**
**Savings: $240-300/yr**

## Current Setup
- Squarespace Business plan: $276/yr (overkill for a portfolio site)
- Google Workspace via Squarespace: 2 users x $84 = $168/yr
- conformalmaps.com domain registered through Squarespace
- Visa ...1498, exp 12/2027
- Renewal dates: website Oct 17, Google Workspace Oct 2

## Investigation Needed
- **Who is the second Google Workspace user?** You're paying for 2 seats. If unused, drop to 1 ($84/yr saved immediately).

## Upgrade Path (Volkmar-style)

### Phase 1: Reduce Immediate Cost (before Oct 2 renewal)
1. Log into Squarespace admin
2. Identify the second Google Workspace user — remove if unused
3. Consider downgrading Squarespace from Business ($276/yr) to Personal ($144/yr)
   - Business features you likely don't need: e-commerce, advanced analytics, promotional pop-ups, CSS/JS injection
   - Personal includes: custom domain, SSL, unlimited bandwidth, basic analytics

### Phase 2: Email Migration (before Oct 2)

#### Option A: Stay on Google Workspace (simplest)
- Just drop to 1 user: $84/yr
- Keep conformalmaps.com email working as-is
- Plus-addressing works: joel+case@conformalmaps.com, joel+tax@conformalmaps.com

#### Option B: Fastmail ($50/yr, recommended for Volkmar-style setup)
- Custom domain email with full plus-addressing
- joel@conformalmaps.com as primary
- joel+div@conformalmaps.com → auto-files to div_legal folder
- joel+hertz@conformalmaps.com → auto-files to hertz folder
- joel+tax@conformalmaps.com → auto-files to tax folder
- IMAP/SMTP access for programmatic sending
- CalDAV/CardDAV for contacts sync
- Masked email addresses (generate unique addresses per service)
- Privacy-focused (Australian company, no ad scanning)

#### Option C: ProtonMail ($48/yr bundled with ProtonVPN)
- End-to-end encrypted email
- Custom domain support
- Plus-addressing
- Bundles with VPN (see VPN plan)
- Downside: IMAP bridge required for third-party clients

#### Option D: Cloudflare Email Routing (free) + any provider
- Transfer domain to Cloudflare ($10.58/yr at cost)
- Use Cloudflare Email Routing to forward @conformalmaps.com to Gmail (free)
- Send via Gmail SMTP as conformalmaps.com (free with app passwords)
- Total email cost: $0
- Downside: relies on Gmail, less professional

### Phase 3: Domain Transfer (optional, saves ~$10/yr)
1. Transfer conformalmaps.com from Squarespace to Cloudflare Registrar
2. Cloudflare charges at-cost ($10-12/yr for .com)
3. Squarespace charges ~$20/yr
4. Point DNS to wherever you host (Squarespace, Cloudflare Pages, or GitHub Pages)

## Recommended Path
1. **Now**: Check who the 2nd Workspace user is
2. **Before Oct 2**: Drop to 1 Workspace user ($84 saved)
3. **Before Oct 17**: Downgrade Squarespace to Personal ($132 saved)
4. **When ready**: Evaluate Fastmail migration for Volkmar-style plus-addressing
5. **Eventually**: Transfer domain to Cloudflare for at-cost renewal

## Cost Comparison

| Setup | Annual Cost |
|-------|-----------|
| Current (Business + 2x GWS + domain) | $464/yr |
| Personal + 1x GWS + domain | $248/yr |
| Personal + Fastmail + Cloudflare domain | $204/yr |
| Cloudflare Pages + Fastmail + Cloudflare domain | $60/yr |
