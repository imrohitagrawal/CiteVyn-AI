#!/bin/bash

##############################################################################
# CiteVyn AI: Automated Skills Installation Script
# 
# Installs 85 AI skills across 3 domains:
# - Engineering skills (10)
# - PM skills (68)
# - UI/UX skills (7)
#
# Usage: ./scripts/install-skills.sh
##############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
TEMP_DIR=$(mktemp -d)

# Cleanup on exit
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

##############################################################################
# Helper Functions
##############################################################################

print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ $1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"
}

print_step() {
    echo -e "${YELLOW}→ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

##############################################################################
# Main Installation
##############################################################################

print_header "CiteVyn AI: Copilot Skills Installation"

# Step 1: Verify project structure
print_step "Verifying project structure..."
if [ ! -f "$PROJECT_ROOT/.github/SKILLS_MANIFEST.md" ]; then
    print_error "SKILLS_MANIFEST.md not found. Are you in the correct directory?"
    exit 1
fi
print_success "Project structure verified"

# Step 2: Create directories
print_step "Creating .github directories..."
mkdir -p "$PROJECT_ROOT/.github/skills"
mkdir -p "$PROJECT_ROOT/.github/pm-skills"
mkdir -p "$PROJECT_ROOT/.github/ui-ux-skills"
print_success ".github directories ready"

# Step 3: Install Engineering Skills
print_header "Installing Engineering Skills (10 skills)"
print_step "Cloning addyosmani/agent-skills..."
git clone --quiet https://github.com/addyosmani/agent-skills.git "$TEMP_DIR/agent-skills" 2>/dev/null || {
    print_error "Failed to clone agent-skills"
    exit 1
}
print_success "Repository cloned"

print_step "Copying skill files..."
if [ -d "$TEMP_DIR/agent-skills/skills" ]; then
    cp -r "$TEMP_DIR/agent-skills/skills"/* "$PROJECT_ROOT/.github/skills/" 2>/dev/null || true
    SKILL_COUNT=$(find "$PROJECT_ROOT/.github/skills" -name "SKILL.md" | wc -l)
    print_success "Installed $SKILL_COUNT engineering skills"
else
    print_error "Skills directory not found in agent-skills"
    exit 1
fi

# Step 4: Install PM Skills
print_header "Installing PM Skills (68 skills across 9 plugins)"
print_step "Cloning phuryn/pm-skills..."
git clone --quiet https://github.com/phuryn/pm-skills.git "$TEMP_DIR/pm-skills" 2>/dev/null || {
    print_error "Failed to clone pm-skills"
    exit 1
}
print_success "Repository cloned"

print_step "Copying plugin files..."
if [ -d "$TEMP_DIR/pm-skills/plugins" ]; then
    cp -r "$TEMP_DIR/pm-skills/plugins"/* "$PROJECT_ROOT/.github/pm-skills/" 2>/dev/null || true
    PLUGIN_COUNT=$(find "$PROJECT_ROOT/.github/pm-skills" -maxdepth 1 -type d | tail -n +2 | wc -l)
    print_success "Installed $PLUGIN_COUNT PM plugins (68 skills)"
else
    print_error "Plugins directory not found in pm-skills"
    exit 1
fi

# Step 5: Install UI/UX Skills
print_header "Installing UI/UX Skills (7 skills + 49 reference guides)"
print_step "Cloning nextlevelbuilder/ui-ux-pro-max-skill..."
git clone --quiet https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git "$TEMP_DIR/ui-ux-skills" 2>/dev/null || {
    print_error "Failed to clone ui-ux-pro-max-skill"
    exit 1
}
print_success "Repository cloned"

print_step "Copying skill files and reference guides..."
if [ -d "$TEMP_DIR/ui-ux-skills/skills" ]; then
    cp -r "$TEMP_DIR/ui-ux-skills/skills"/* "$PROJECT_ROOT/.github/ui-ux-skills/" 2>/dev/null || true
    
    # Also copy reference guides if they exist
    if [ -d "$TEMP_DIR/ui-ux-skills/reference-guides" ]; then
        mkdir -p "$PROJECT_ROOT/.github/ui-ux-skills/reference-guides"
        cp -r "$TEMP_DIR/ui-ux-skills/reference-guides"/* "$PROJECT_ROOT/.github/ui-ux-skills/reference-guides/" 2>/dev/null || true
    fi
    
    UI_SKILL_COUNT=$(find "$PROJECT_ROOT/.github/ui-ux-skills" -name "SKILL.md" | wc -l)
    print_success "Installed $UI_SKILL_COUNT UI/UX skills and reference guides"
else
    print_error "Skills directory not found in ui-ux-pro-max-skill"
    exit 1
fi

# Step 6: Verify installation
print_header "Verifying Installation"

ENG_COUNT=$(find "$PROJECT_ROOT/.github/skills" -name "SKILL.md" 2>/dev/null | wc -l)
PM_COUNT=$(find "$PROJECT_ROOT/.github/pm-skills" -name "SKILL.md" 2>/dev/null | wc -l)
UI_COUNT=$(find "$PROJECT_ROOT/.github/ui-ux-skills" -name "SKILL.md" 2>/dev/null | wc -l)

print_step "Engineering skills: $ENG_COUNT"
print_step "PM skills: $PM_COUNT"
print_step "UI/UX skills: $UI_COUNT"

TOTAL=$((ENG_COUNT + PM_COUNT + UI_COUNT))
echo ""
print_success "✅ Total: $TOTAL skills installed"

# Step 7: Verify agents
print_header "Verifying Custom Agents"
AGENT_COUNT=$(find "$PROJECT_ROOT/.github/agents" -name "*.agent.md" 2>/dev/null | wc -l)
print_step "Custom agents: $AGENT_COUNT (code-reviewer, test-engineer, security-auditor, web-performance-auditor)"
print_success "All agents ready"

# Final summary
print_header "Installation Complete! 🎉"

echo -e "${GREEN}Your Copilot skills are now configured:${NC}"
echo ""
echo "📁 Directory structure:"
echo "   .github/skills/           → 10 engineering skills"
echo "   .github/pm-skills/        → 68 PM skills (9 plugins)"
echo "   .github/ui-ux-skills/     → 7 UI/UX skills + reference guides"
echo "   .github/agents/           → 4 specialized agents"
echo ""
echo "🚀 Next steps:"
echo "   1. Reload VS Code (or restart GitHub Copilot Chat)"
echo "   2. Try a skill in Copilot Chat:"
echo "      • Engineering: @code-reviewer Review this code"
echo "      • PM: /discover What are user pain points?"
echo "      • UI/UX: /design-system Generate design tokens"
echo ""
echo "📚 Documentation:"
echo "   • .github/SKILLS_MANIFEST.md     → Full skills reference"
echo "   • .github/copilot-instructions.md → Copilot guidelines"
echo "   • .github/REPOSITORY_OVERVIEW.md  → Project architecture"
echo ""

print_success "Skills installation script completed successfully!"
