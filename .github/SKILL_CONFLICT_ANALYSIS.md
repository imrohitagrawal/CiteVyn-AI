# Skill Conflict Analysis

## Summary
**No critical conflicts detected.** ✅

All 85+ skills across 3 repositories are complementary and designed to work together across the product development lifecycle.

---

## Skill Distribution

| Repository | Skills | Domain | Purpose |
|------------|--------|--------|---------|
| **addyosmani/agent-skills** | 10 | Engineering | Development workflows, quality gates |
| **phuryn/pm-skills** | 68 | Product | Strategy, discovery, execution, launch |
| **nextlevelbuilder/ui-ux-pro-max-skill** | 7 | Design | Design systems, components, branding |
| **TOTAL** | **85** | Cross-functional | Full product lifecycle |

---

## Analysis: Potential Overlaps

### 1. **Documentation & ADRs** (Eng vs. UI/UX)
- **Engineering**: Code architecture, technical decisions, API specifications
- **UI/UX**: Design tokens, component specifications, brand guidelines
- **Status**: ✅ **COMPLEMENTARY** — Different layers, no conflict
- **Usage**: Engineer writes ADR for code; Designer documents design system

### 2. **Planning & Task Breakdown** (Eng vs. PM)
- **Engineering**: Code-level decomposition, incremental development slices
- **PM**: Product roadmaps, OKRs, feature prioritization
- **Status**: ✅ **COMPLEMENTARY** — Different scopes
- **Usage**: PM defines features; Engineer breaks into code tasks

### 3. **Specification** (Eng vs. PM)
- **Engineering**: `spec-driven-development` → Technical specs, API contracts
- **PM**: `create-prd` → Product requirements, user stories, business rules
- **Status**: ✅ **COMPLEMENTARY** — Different abstraction levels
- **Usage**: PM writes PRD; Engineer writes technical spec from PRD

### 4. **Quality & Code Review** (Eng Only)
- **Engineering**: `code-review-and-quality` → 5-axis review (correctness, readability, architecture, security, performance)
- **PM**: No code review equivalent
- **UI/UX**: No code review equivalent
- **Status**: ✅ **NO CONFLICT** — Engineering-specific

### 5. **Security & Hardening** (Eng Only)
- **Engineering**: Input validation, secrets management, auth/authz
- **PM/UI/UX**: No security implementation skills
- **Status**: ✅ **NO CONFLICT** — Engineering-specific

### 6. **Performance Optimization** (Eng Only)
- **Engineering**: Profiling, load testing, efficiency
- **PM/UI/UX**: No performance optimization skills
- **Status**: ✅ **NO CONFLICT** — Engineering-specific

### 7. **CI/CD & Automation** (Eng Only)
- **Engineering**: Pipeline setup, deployment, test automation
- **PM/UI/UX**: No CI/CD equivalent
- **Status**: ✅ **NO CONFLICT** — Engineering-specific

### 8. **Design Systems** (UI/UX Primary, Eng Secondary)
- **UI/UX**: `design-system` → Design tokens, component specs, patterns
- **Engineering**: Part of `documentation-and-adrs` → Component documentation
- **Status**: ✅ **COMPLEMENTARY** — Designer creates system; Engineer implements
- **Usage**: UI/UX generates design tokens → Engineering uses for Tailwind/shadcn

### 9. **Branding & Visual Identity** (UI/UX Only)
- **UI/UX**: `brand` skill covers logo, color psychology, style guides
- **PM**: No branding equivalent (has `positioning-ideas` but different focus)
- **Status**: ✅ **NO CONFLICT** — UI/UX-specific

### 10. **Market Research & Personas** (PM Only)
- **PM**: `user-personas`, `market-sizing`, `competitor-analysis` (7 skills)
- **Engineering**: No equivalent
- **UI/UX**: No market research (uses PM personas as input)
- **Status**: ✅ **NO CONFLICT** — PM-specific

### 11. **Presentation Design** (UI/UX Primary)
- **UI/UX**: `slides` skill for presentation design
- **PM**: Has `slides` output but focused on content, not design
- **Status**: ✅ **COMPLEMENTARY** — Different aspects (design vs. content)

---

## Command Naming

### Engineering Commands
None (Skills auto-activate; no explicit slash commands)

### PM Commands
All unique: `/discover`, `/strategy`, `/write-prd`, `/plan-launch`, `/north-star`, etc.

### UI/UX Commands
None (Skills auto-activate based on conversation context)

**Status**: ✅ **NO COMMAND CONFLICTS**

---

## Skill Interaction Workflow

```
Product Lifecycle:
├── DISCOVER (PM)
│   └── Outputs: User personas, market research, opportunity tree
│
├── STRATEGY (PM)
│   └── Outputs: Product vision, positioning, business model
│   └── Feeds to UI/UX: Design system generator
│
├── DESIGN (UI/UX)
│   └── Inputs: Strategy, personas, target market
│   └── Outputs: Design system, brand guidelines, component specs
│   └── Feeds to Eng: Design tokens, Tailwind config, shadcn components
│
├── BUILD (Eng)
│   └── Inputs: PRD, design system, specifications
│   └── Activities: TDD, incremental implementation, code review
│   └── Uses: spec-driven-dev, planning-task-breakdown, security-hardening
│
├── EXECUTE (PM + Eng)
│   └── PM: Roadmap, sprint planning, prioritization
│   └── Eng: Testing, debugging, performance optimization, CI/CD
│
├── LAUNCH (PM + UI/UX + Eng)
│   └── PM: Go-to-market, launch planning, release notes
│   └── UI/UX: Final design polish, presentation slides
│   └── Eng: Deployment, monitoring, rollback capability
│
└── GROW (PM + Analytics)
    └── PM: Growth loops, metrics, feature prioritization
    └── Analytics: Cohort analysis, A/B testing
```

**Status**: ✅ **WORKFLOW IS COHERENT** — No conflicts, clear handoffs

---

## Risk Assessment

### LOW RISK ✅
- **No duplicate skill names** across all 3 repos
- **Clear domain separation**: Engineering, Product, Design
- **Complementary scopes**: Code-level, product-level, design-level
- **Intentional layering**: Each skill operates at appropriate abstraction level

### MEDIUM RISK ⚠️ (None identified)
- No timing conflicts
- No mutual exclusion issues
- No contradictory approaches

### HIGH RISK 🔴 (None identified)
- No breaking changes
- No mutual dependencies that create deadlocks

---

## Best Practices to Avoid Issues

1. **Use PM skills for strategic decisions** → Then use UI/UX for design → Then use Eng for implementation
2. **Reference design system in code review** → Eng code-review skill verifies design token usage
3. **Leverage PM personas in design** → UI/UX uses market research personas from PM skills
4. **Document handoffs** → Use Eng ADR skill to document design decisions
5. **Test design & PM outputs** → Eng testing skills validate that design + PM requirements are met
6. **Communicate across domains** → Use PM execution skills for cross-functional coordination

---

## Conclusion

**85+ complementary skills with zero conflicts.**

The three skill repositories form a complete product development system:
- **PM Skills**: Decide *what* to build and *why*
- **UI/UX Skills**: Design *how it looks* and *how it works*
- **Engineering Skills**: Implement *how it runs* and *why it's reliable*

Each domain has clear, non-overlapping responsibilities. When used together, they create a coherent, full-stack development workflow.
