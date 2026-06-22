# Skills Integration Guide

## Overview

CiteVyn integrates 85 curated skills across three domains to enhance GitHub Copilot Chat workflows. Rather than committing third-party skills to this repository, we reference them from their upstream sources for easy maintenance and updates.

## Installed Skills

### 1. Engineering Skills (10 skills)
**Source:** [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)

Skills for code quality, testing, security, CI/CD, and performance:
- Test-driven development (TDD)
- Code review & quality gates
- Security & hardening
- CI/CD pipeline automation
- Performance optimization
- Debugging & error recovery
- Documentation & ADRs
- Incremental implementation
- Planning & task breakdown
- Spec-driven development

**Setup:** Clone repo and copy `skills/` → `.github/skills/`

### 2. PM Skills (68 skills across 9 plugins)
**Source:** [phuryn/pm-skills](https://github.com/phuryn/pm-skills)

Plugins for product discovery, strategy, execution, and go-to-market:
- pm-toolkit (11 skills)
- pm-product-discovery (8 skills)
- pm-product-strategy (10 skills)
- pm-market-research (8 skills)
- pm-data-analytics (7 skills)
- pm-marketing-growth (8 skills)
- pm-go-to-market (8 skills)
- pm-execution (5 skills)
- pm-ai-shipping (3 skills)

**Workflow commands:** 42 commands including `/discover`, `/strategy`, `/write-prd`, `/plan-launch`, `/north-star`, etc.

**Setup:** Clone repo and copy `plugins/` → `.github/pm-skills/`

### 3. UI/UX Skills (7 skills + 49 reference guides)
**Source:** [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)

Skills for design systems, branding, and component specifications:
- ui-ux-pro-max (design system generator with 161 color palettes, 67 styles)
- ui-styling (component styling)
- design-system (tokens, patterns, components)
- design (general design principles)
- brand (branding guidelines)
- slides (presentation design)
- banner-design (marketing assets)

**Reference guides:** 49 design system references (color palettes, typography, spacing, etc.)

**Setup:** Clone repo and copy `skills/` → `.github/ui-ux-skills/`

## Custom Integration Files

These files are committed to this repository:

| File | Purpose |
|------|---------|
| `.github/copilot-instructions.md` | Master Copilot Chat guidelines (116 + 250+ lines from 3 domains) |
| `.github/agents/*.agent.md` | 4 specialized agents (code-reviewer, test-engineer, security-auditor, web-performance-auditor) |
| `.github/REPOSITORY_OVERVIEW.md` | Complete project guide, architecture, slices, and next steps |
| `.github/SKILL_CONFLICT_ANALYSIS.md` | Analysis of all 85 skills for conflicts (result: ZERO) |

## Installation Instructions

### Clone all skill repositories:

```bash
# Engineering skills
git clone https://github.com/addyosmani/agent-skills.git /tmp/agent-skills
cp -r /tmp/agent-skills/skills .github/skills

# PM skills
git clone https://github.com/phuryn/pm-skills.git /tmp/pm-skills
cp -r /tmp/pm-skills/plugins .github/pm-skills

# UI/UX skills
git clone https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git /tmp/ui-ux-skills
cp -r /tmp/ui-ux-skills/skills .github/ui-ux-skills
```

### Verify integration:

```bash
# Check Copilot can find skills
ls -la .github/skills/
ls -la .github/pm-skills/
ls -la .github/ui-ux-skills/
ls -la .github/agents/
```

### Use in GitHub Copilot:

1. Open Copilot Chat in VS Code
2. Start typing or use `/` for workflow commands
3. Skills auto-load based on conversation context
4. For PM workflows, use commands like `/discover`, `/strategy`, `/write-prd`

## Architecture & Integration

**How skills are loaded:**
- `.github/skills/` — Engineering skills (auto-active)
- `.github/pm-skills/` — PM skills with workflow commands
- `.github/ui-ux-skills/` — UI/UX skills with design references
- `.github/agents/` — Specialized agents (.agent.md format)
- `.github/copilot-instructions.md` — Global guidelines

**Conflict analysis:**
All 85 skills have been analyzed for:
- ✅ Name collisions: 0 found
- ✅ Command conflicts: 0 found
- ✅ Functional overlap: Complementary (design ↔ code, PM ↔ engineering, strategy ↔ tactics)

See `SKILL_CONFLICT_ANALYSIS.md` for full details.

## Usage Examples

### Engineering Workflows:
```bash
# Code review
@code-reviewer Review this PR for security, performance, readability

# Test-driven development
@test-engineer Write tests for user authentication feature

# Spec-driven development
/spec Create product specification for Slice 2 (database + vector search)
```

### PM Workflows:
```bash
# Product discovery
/discover What are user pain points in citation-backed Q&A?

# Market analysis
/market-scan Analyze market for AI-powered documentation tools

# Strategy planning
/strategy Define go-to-market strategy for CiteVyn

# Launch planning
/plan-launch Create launch checklist for Slice 1 release
```

### UI/UX Workflows:
```bash
# Design system
/design-system Generate design system for citation interface

# Branding
/brand Define brand guidelines for CiteVyn

# Components
@web-performance-auditor Analyze design impact on Core Web Vitals
```

## Maintenance

### Updating skills:
When upstream repositories release updates:

1. Pull latest from upstream
2. Copy updated `skills/` directories to `.github/`
3. Run tests to verify integration
4. Commit only `.github/copilot-instructions.md` changes (if any)

### Adding new skills:
1. Clone upstream skill repository
2. Copy to appropriate `.github/` subdirectory
3. Update this manifest
4. Commit manifest changes only

### Removing skills:
1. Delete from `.github/skills/`, `.github/pm-skills/`, or `.github/ui-ux-skills/`
2. Update this manifest
3. Run tests
4. Commit manifest changes

## References

- **Copilot Skills Documentation:** [github.com/github/copilot-skills](https://github.com/github/copilot-skills)
- **Project Architecture:** See `docs/ARCHITECTURE.md`
- **Repository Overview:** See `.github/REPOSITORY_OVERVIEW.md`
- **Conflict Analysis:** See `.github/SKILL_CONFLICT_ANALYSIS.md`

## Next Steps

- **Slice 2 Planning:** Use PM `/discover` and `/strategy` commands to plan database + vector search
- **Design System:** Use UI/UX skills to generate Tailwind + shadcn design system
- **Engineering Quality:** Use TDD and security skills to maintain production standards

---

**Last updated:** 2026-06-17  
**Skills analyzed:** 85 (10 engineering + 68 PM + 7 UI/UX)  
**Conflicts found:** 0 ✅
