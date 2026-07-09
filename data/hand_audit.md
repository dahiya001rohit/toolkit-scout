# Hand-audit: 15 randomly sampled apps (seed=42)

For each app: open the evidence URL, check the 4 claims, mark each [ ] as x (correct) or leave blank + note.

## Plaid (Finance and Fintech)
- [ ] auth = api_key — https://plaid.com/docs/quickstart/
- [ ] access = self_serve — https://plaid.com/docs/quickstart/
- [ ] api = rest / broad — https://plaid.com/docs/
- [ ] verdict = ready (Public REST API with extensive documentation and API keys available for self‑service access)

## Pylon (Support and Helpdesk)
- [ ] auth = unknown — https://docs.usepylon.com/pylon-docs
- [ ] access = trial — https://www.usepylon.com/
- [ ] api = unknown / broad — https://docs.usepylon.com/pylon-docs
- [ ] verdict = partial (API documentation exists but public access details are unclear)

## Attio (CRM and Sales)
- [ ] auth = oauth2 — https://docs.attio.com/rest-api/overview
- [ ] access = self_serve — https://attio.com
- [ ] api = rest / broad — https://docs.attio.com/rest-api/overview
- [ ] verdict = ready (Attio provides a public REST API and an MCP for building custom integrations and automations.)

## Devin (AI, Research and Media-native)
- [ ] auth = unknown — no evidence
- [ ] access = self_serve — https://docs.devin.ai/get-started/devin-intro
- [ ] api = rest / broad — https://docs.devin.ai/api-reference/overview
- [ ] verdict = ready (Public REST API with extensive documentation enables integration into AI-agent toolkits.)

## Klaviyo (Marketing, Ads, Email and Social)
- [ ] auth = api_key — no evidence
- [ ] access = self_serve — https://developers.klaviyo.com/en
- [ ] api = rest / unknown — no evidence
- [ ] verdict = ready (API documentation is publicly available, allowing developers to create integrations.)

## Meta Ads (Marketing, Ads, Email and Social)
- [ ] auth = oauth2 — https://developers.facebook.com/documentation/ads-commerce/marketing-api
- [ ] access = self_serve — https://developers.facebook.com/
- [ ] api = rest / broad — https://developers.facebook.com/documentation/ads-commerce/marketing-api
- [ ] verdict = ready (The API provides extensive documentation and guides for creating, managing, and optimizing ads.)

## Aircall (Communications and Messaging)
- [ ] auth = oauth2 — https://developer.aircall.io
- [ ] access = self_serve — https://aircall.io
- [ ] api = rest / broad — https://developer.aircall.io
- [ ] verdict = ready (Aircall provides a well-documented Public API and supports webhooks for automating workflows.)

## Help Scout (Support and Helpdesk)
- [ ] auth = unknown — no evidence
- [ ] access = trial — no evidence
- [ ] api = rest / moderate — https://developer.helpscout.com
- [ ] verdict = partial (API is available but no information is provided about the scope of the API or the level of access it provides)

## Front (Support and Helpdesk)
- [ ] auth = oauth2 — https://dev.frontapp.com/docs/welcome
- [ ] access = trial — https://dev.frontapp.com/docs/welcome
- [ ] api = rest / broad — https://dev.frontapp.com/docs/welcome
- [ ] verdict = ready (Public API with documentation, OAuth authentication, and free developer environment enable immediate integration)

## Xero (Finance and Fintech)
- [ ] auth = oauth2 — https://developer.xero.com
- [ ] access = self_serve — https://www.xero.com/signup/developers/
- [ ] api = rest / broad — https://developer.xero.com
- [ ] verdict = ready (Xero provides a range of developer tools and resources, including APIs, SDKs, and documentation)

## Sentry (Developer, Infra and Data platforms)
- [ ] auth = token — https://docs.sentry.io/api/
- [ ] access = self_serve — https://docs.sentry.io/api/
- [ ] api = rest / unknown — no evidence
- [ ] verdict = ready (Public API with token authentication and MCP server support enables programmatic integration for AI agents.)

## Intercom (Support and Helpdesk)
- [ ] auth = unknown — no evidence
- [ ] access = trial — https://www.intercom.com/
- [ ] api = rest / broad — https://developers.intercom.com
- [ ] verdict = ready (Intercom has a developer platform with APIs and SDKs for building custom apps and integrations.)

## Monday.com (Productivity and Project Management)
- [ ] auth = oauth2 — https://developer.monday.com
- [ ] access = unknown — no evidence
- [ ] api = graphql / broad — https://developer.monday.com
- [ ] verdict = ready (Public GraphQL API is documented and accessible for building AI‑agent integrations.)

## Apify (Data, SEO and Scraping)
- [ ] auth = unknown — no evidence
- [ ] access = self_serve — no evidence
- [ ] api = unknown / unknown — no evidence
- [ ] verdict = ready (API references and SDKs exist but access methods and breadth are unspecified)

## Twenty (CRM and Sales)
- [ ] auth = unknown — no evidence
- [ ] access = unknown — no evidence
- [ ] api = unknown / unknown — no evidence
- [ ] verdict = ready (Insufficient information to determine buildability)
