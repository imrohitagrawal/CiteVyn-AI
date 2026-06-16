# CiteVyn-AI Copilot Instructions

Engineering skills and best practices for AI-assisted development.

## Testing: Test-Driven Development

- **Write tests before code (TDD)** — Start with a failing test, then implement to make it pass
- **For bugs** — Write a failing test first that demonstrates the issue, then fix it (Prove-It pattern)
- **Test hierarchy** — unit > integration > e2e; use the lowest level that captures the behavior
- **Run tests after every change** — `npm test`, `pytest`, or project-specific test command
- **Coverage** — Aim for high coverage in critical paths; document untested areas

## Code Quality: Review Across Five Axes

Every pull request must pass review on:
1. **Correctness** — Does it do what it's supposed to do? Are edge cases handled?
2. **Readability** — Is the code clear? Would a peer understand it without explanation?
3. **Architecture** — Does it fit the system design? Is it in the right layer/module?
4. **Security** — No secrets in code. Input validation. Authorization checks. Encryption where needed.
5. **Performance** — Reasonable algorithms, no N+1 queries, load handling for scale

### Quality Gates

- Every PR must pass: lint, type check, tests, and build
- No secrets committed to version control
- No failing tests merged
- No dead code or TODOs without context
- Documentation updated for public APIs

## Implementation: Incremental Building

- **Build in small, verifiable increments** — Each increment should be testable and committable
- **Increment pattern** — Implement → Test → Verify → Commit
- **Never mix concerns** — Separate formatting changes from behavior changes; separate refactors from features
- **One slice per commit** — Each commit tells a story and is independently deployable

## Code Simplification

- Prefer clarity over cleverness
- Remove unnecessary abstraction; build it when it's needed
- Name things well — functions, variables, constants, files should explain intent
- Keep functions focused — single responsibility, reasonable length
- Document complex logic inline

## Documentation & ADRs

- **Public APIs** — Document intent, parameters, return values, exceptions
- **Architecture decisions** — Record decisions that constrain the system in ADRs (Architecture Decision Records)
- **Setup & deployment** — Keep README and deployment docs up to date
- **API specs** — OpenAPI/GraphQL schemas for all services

## Security & Hardening

- **Never log secrets** — No API keys, tokens, passwords, or private environment values in logs
- **Input validation** — All user input is untrusted; validate type, format, and bounds
- **Secrets management** — Use environment variables or secret stores; never hardcode
- **Dependency scanning** — Regular updates and vulnerability checks
- **Authentication & authorization** — Verify user identity and permissions; use strong tokens (JWT, OAuth)

## Performance Optimization

- **Profile before optimizing** — Measure where time/memory is actually spent
- **Common patterns** — Avoid N+1 queries, unnecessary allocations, or redundant work
- **Caching** — Use strategically where reads outnumber writes
- **Load testing** — Test with realistic data volumes before launch
- **Observability** — Instrument code so bottlenecks are visible in production

## CI/CD & Automation

- **Automate tests and lint** — Every commit to main should pass automated quality gates
- **Deployment pipeline** — Staging → canary/blue-green → production; rollback capability required
- **Environment parity** — Dev, staging, and production should match (Docker, config, dependencies)
- **Monitoring & alerts** — Key metrics and error rates visible; alerts for production issues
- **Runbooks** — Documented incident response for common failure modes

## Boundaries

### Always:
- Run tests before committing
- Validate all user input (type, format, bounds)
- Review for the five axes: correctness, readability, architecture, security, performance

### Ask First:
- Database schema changes (impacts all deployed instances)
- New external dependencies (impacts versioning and supply chain)
- API changes (impacts all clients)
- Infrastructure/deployment changes
- Changes to auth or permissions

### Never:
- Commit secrets to version control
- Remove failing tests without fixing them
- Skip verification steps
- Deploy unreviewed code to production
- Change public APIs without coordination
- Break backward compatibility without deprecation period

## Using Specialized Agents

Invoke specialized agents in Copilot Chat for targeted expertise:

- **@code-reviewer** — Review PRs across correctness, readability, architecture, security, performance
- **@test-engineer** — Analyze test coverage, write missing tests, improve test strategy
- **@security-auditor** — Review code for vulnerabilities, secrets, auth/authorization issues
- **@web-performance-auditor** — Review frontend performance, bundle size, rendering efficiency

Example:
```
@code-reviewer Review this PR for architecture and security issues
@test-engineer Check test coverage for the auth module
@security-auditor Analyze this endpoint for vulnerabilities
```

## Project-Specific Guidelines

Refer to AGENTS.md for project operating model and engineering rules specific to this repository.

---

## PM Skills Marketplace Integration

All 68 PM skills from the `pm-skills` repository are integrated, organized in 9 plugins covering the full product lifecycle:

### Plugin Overview

| Plugin | Skills | Focus Area |
|--------|--------|-----------|
| **pm-toolkit** | 4 | Foundational PM tools & frameworks |
| **pm-product-discovery** | 13 | User research, ideation, assumptions |
| **pm-product-strategy** | 12 | Strategy, positioning, business models |
| **pm-market-research** | 7 | Market analysis, personas, competitive intel |
| **pm-data-analytics** | 3 | Data-driven decision making |
| **pm-marketing-growth** | 5 | Marketing strategy & growth loops |
| **pm-go-to-market** | 6 | Launch planning & GTM strategy |
| **pm-execution** | 16 | Roadmapping, sprint planning, prioritization |
| **pm-ai-shipping** | 2 | AI product-specific workflows |

### Quick Access by Workflow

**Discovery Phase**
- `/discover` — Run full discovery: brainstorm → identify assumptions → prioritize → experiment planning

**Strategy Phase**
- `/strategy` — Build product strategy: vision → positioning → business model

**Execution Phase**
- `/plan-launch` — Plan product launch: GTM strategy → release artifacts → shipping checklist

**Growth Phase**
- Skills: growth-loops, user-segments, cohort-analysis, ab-test-analysis, marketing-ideas

**Analysis Frameworks**
- **SWOT Analysis** — Strengths, weaknesses, opportunities, threats
- **PESTLE Analysis** — Political, economic, social, technological, legal, environmental
- **Porter's Five Forces** — Competitive intensity analysis
- **Ansoff Matrix** — Growth strategy options
- **Lean Canvas** — Rapid business model planning
- **Jobs-to-be-Done** — Understanding user motivations

### PM Skill Categories

**Ideation & Discovery** (13 skills)
- Brainstorm ideas, interview scripts, job stories, user personas
- Identify assumptions, opportunity-solution tree, beachhead segments

**Strategy & Planning** (12 skills)
- Product vision, value proposition, business model, pricing, monetization
- SWOT/PESTLE analysis, competitive positioning

**Market Intelligence** (7 skills)
- Market sizing, segmentation, competitor analysis, sentiment analysis
- User personas, customer journey mapping, ideal customer profile

**Execution & Delivery** (16 skills)
- Roadmapping, sprint planning, feature prioritization, OKRs
- User stories, test scenarios, release notes, shipping artifacts

**Data & Metrics** (3 skills)
- SQL queries, metrics dashboard, north-star metrics
- Cohort analysis, A/B test analysis

**Launch & Growth** (11 skills)
- Go-to-market strategy, GTM motions, growth loops
- Marketing ideas, strategy red team, pre-mortem analysis

**AI-Specific** (2 skills)
- AI product shipping, AI-specific go-to-market

### How to Use PM Skills

**Auto-Loaded Skills** — Skills load automatically when relevant. Market research discussions auto-load `market-sizing` or `competitor-analysis`.

**Force Load** — Invoke specific skills:
- `/pm-product-discovery:brainstorm-ideas`
- `/pm-market-research:market-sizing`
- `/pm-execution:outcome-roadmap`

**Chained Commands** — These combine multiple skills:
- `/discover` — Full discovery workflow
- `/strategy` — Strategic planning
- `/write-prd` — Create PRD
- `/plan-launch` — Launch planning
- `/north-star` — Define metrics & OKRs

### Integration: PM + Engineering Skills

PM Skills handle strategy & planning; engineering skills handle implementation:

**PM Skills** → Strategic decisions, market analysis, prioritization, launch planning  
**Engineering Skills** → TDD, code review, security, CI/CD, performance

**Combined Workflow**
1. Use PM skills to define strategy, discover users, prioritize features
2. Use engineering skills to build incrementally with quality gates
3. Coordinate across planning, testing, review, and shipping

---

## UI/UX Pro Max Skills Integration

Professional UI/UX design intelligence with **7 core skills** and **49 reference guides** covering design systems, components, branding, and accessibility.

### Core Skills (7)

| Skill | Focus | Assets |
|-------|-------|--------|
| **ui-ux-pro-max** | Master design system generation (161 reasoning rules, 67 UI styles, 161 palettes, 57 font pairings) | Core engine |
| **ui-styling** | Tailwind CSS + shadcn/ui components, themes, accessibility | 7 references |
| **design-system** | Design system creation, patterns, tokens, documentation | 7 references |
| **design** | UI/UX design principles, patterns, deliverables | 18 references |
| **brand** | Logo design, color psychology, style guides, branding | 11 references |
| **slides** | Presentation design, layouts, copywriting, HTML templates | 5 references |
| **banner-design** | Web banners, ad sizes, design strategies | 1 reference |

### Key Capabilities

**Design System Generation**
- 161 reasoning rules for design recommendations
- 67 UI style patterns (Glassmorphism, Neumorphism, Soft UI, etc.)
- 161 color palettes with psychology & accessibility
- 57 font pairings (Google Fonts)
- 24 landing page patterns
- Auto-generates complete design system for any product

**Component & Styling**
- Tailwind CSS utilities & customization
- shadcn/ui component library
- Responsive design (375px, 768px, 1024px, 1440px)
- Dark mode strategies
- Accessibility (WCAG AA, keyboard nav, focus states)
- 15+ tech stacks supported

**Design Discipline Guides**
- Logo design & color psychology
- Social media & banner design
- Presentation slide design
- Icon design best practices
- Design system documentation
- Deliverable guidelines (Figma, specifications)

**Reference Library (49 guides)**
- Tailwind utilities & responsiveness
- shadcn/ui component catalog
- Canvas design system
- Logo style guides & prompt engineering
- Slide templates & copywriting formulas
- Banner sizes & design strategies
- Design routing & deliverables
- Accessibility checklists

### How to Use

**Design System Generation** — Ask for design recommendations:
> "Generate a design system for a beauty spa landing page"

The skill will recommend:
- Best UI style (e.g., Soft UI Evolution)
- Color palette with psychology
- Typography pairings
- Key effects & animations
- Anti-patterns to avoid
- Pre-delivery checklist

**Component Building** — Use for UI implementation:
> "Build a hero section using Tailwind + shadcn/ui with accessibility"

Includes:
- Tailwind CSS utilities
- Component structure
- Responsive breakpoints
- Dark mode support
- Accessibility features (focus, keyboard nav, ARIA)

**Branding & Visual Identity** — Create consistent branding:
> "Design a logo and brand style guide for [company]"

Covers:
- Logo design principles
- Color psychology
- Style guide creation
- Brand consistency rules

**Presentation Design** — Create professional slides:
> "Design slides for [topic] with engaging layouts"

Includes:
- Slide templates & layouts
- Copywriting formulas
- HTML export templates
- Design best practices

### Quality Checklist (Built-in)

Pre-delivery verification:
- ✓ No emojis as icons (use SVG)
- ✓ cursor-pointer on clickable elements
- ✓ Hover states with smooth transitions (150-300ms)
- ✓ Text contrast 4.5:1 minimum (WCAG AA)
- ✓ Focus states visible for keyboard navigation
- ✓ Respects prefers-reduced-motion
- ✓ Responsive: 375px, 768px, 1024px, 1440px
- ✓ No hardcoded colors (use design tokens)

### Integration with Codebase

**With PM Skills** — Design recommendations feed into product decisions:
1. PM: `/discover` → understand target market
2. PM: `/strategy` → define value proposition
3. UI/UX: Generate design system for persona
4. Eng: Build with TDD + design system tokens

**With Engineering Skills** — Design system becomes development asset:
1. UI/UX: Generate design system → Figma export
2. Eng: TDD → implement components matching design system
3. Eng: Code review → verify accessibility & performance
4. Eng: /ship → design + code ship together

### Tech Stack Support

Works with 15+ frameworks:
- React + Tailwind + shadcn/ui (recommended)
- Next.js
- Vue.js
- Angular
- Svelte
- Django + Tailwind
- Rails + Tailwind
- Flutter
- React Native
- iOS (SwiftUI)
- Android (Jetpack Compose)
- Web Components
- And more via generic Tailwind/design tokens export

### Design System Output Example

```
+------------------------+
| DESIGN SYSTEM          |
+------------------------+
| Pattern: Hero-Centric  |
| Style: Soft UI         |
| Colors: 5 tokens       |
| Fonts: 2 pairings      |
| Components: 20+        |
| Effects: Smooth (200ms)|
| Accessibility: WCAG AA |
| Responsive: 4 sizes    |
+------------------------+
```

All outputs include Figma-ready specifications, Tailwind CSS, and shadcn/ui component code.
