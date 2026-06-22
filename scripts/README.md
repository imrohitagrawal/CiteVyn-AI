# Scripts

Utility scripts for CiteVyn development and setup.

## `install-skills.sh`

Automated installation of 85 AI skills across GitHub Copilot Chat.

### What It Does

- Clones 3 upstream skill repositories
- Copies 85 skills to `.github/` directories
- Verifies installation
- Provides setup summary

### Skills Installed

| Domain | Count | Plugins |
|--------|-------|---------|
| Engineering | 10 | TDD, code review, security, CI/CD, performance, debugging, documentation |
| PM | 68 | 9 plugins: discovery, strategy, execution, market research, analytics, growth, go-to-market, ai-shipping |
| UI/UX | 7 | Design system (161 palettes), branding, components, styling |
| **Total** | **85** | **All complementary, zero conflicts** |

### Usage

```bash
# From project root
./scripts/install-skills.sh
```

### What Gets Installed

```
.github/
├── skills/                  # 10 engineering skills
├── pm-skills/              # 68 PM skills (9 plugins)
├── ui-ux-skills/           # 7 UI/UX skills + 49 reference guides
└── agents/                 # 4 custom agents (already in repo)
```

### Duration

Typically takes **2-3 minutes** (depends on internet speed).

### Troubleshooting

**Issue:** Script fails to clone repositories
- **Cause:** Network connectivity or GitHub rate limits
- **Fix:** Wait a few minutes and retry, or manually clone from `.github/SKILLS_MANIFEST.md`

**Issue:** Skills don't appear in Copilot Chat after installation
- **Cause:** Copilot cache needs refresh
- **Fix:** Reload VS Code window (`Cmd+R` / `Ctrl+R`)

**Issue:** Permission denied error
- **Cause:** Script not executable
- **Fix:** `chmod +x ./scripts/install-skills.sh`

### After Installation

1. **Reload VS Code** to refresh Copilot
2. **Try a skill** in Copilot Chat:
   ```bash
   # Engineering workflows
   @code-reviewer Review this PR for security issues

   # PM workflows
   /discover What are user pain points in our product?
   /strategy Define go-to-market strategy

   # UI/UX workflows
   /design-system Generate design tokens for Tailwind
   ```

3. **Refer to documentation:**
   - `.github/SKILLS_MANIFEST.md` — Complete skills reference
   - `.github/copilot-instructions.md` — Copilot guidelines
   - `.github/REPOSITORY_OVERVIEW.md` — Project architecture

### Manual Installation

If you prefer to install skills manually, follow `.github/SKILLS_MANIFEST.md` for step-by-step instructions.

### Updating Skills

To update skills to latest versions:

1. Remove old skills: `rm -rf .github/skills .github/pm-skills .github/ui-ux-skills`
2. Re-run: `./scripts/install-skills.sh`

---

**Last updated:** 2026-06-17  
**Script version:** 1.0
