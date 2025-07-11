# GitHub Labels Setup Script

Run these commands to create the project labels using GitHub CLI:

```bash
# Phase labels (blue shades)
gh label create "phase-1-analysis" --description "Analysis and documentation phase" --color "c5def5"
gh label create "phase-2-setup" --description "Environment setup phase" --color "a8d0e6"
gh label create "phase-3-katago" --description "KataGo compilation phase" --color "8bbce3"
gh label create "phase-4-build" --description "Application build phase" --color "6ea8dc"
gh label create "phase-5-testing" --description "Testing and optimization phase" --color "5195d6"

# Category labels (green shades)
gh label create "build-system" --description "Build system and compilation" --color "0e8a16"
gh label create "metal-support" --description "macOS Metal GPU support" --color "2ea043"
gh label create "dependencies" --description "Dependency management" --color "56d364"
gh label create "performance" --description "Performance optimization" --color "7ed491"

# Status labels (orange/red shades)
gh label create "blocking" --description "Blocking other work" --color "d73a4a"
gh label create "help-wanted" --description "Extra attention is needed" --color "f9a825"

# Keep existing default labels:
# - bug (for issues)
# - documentation (already exists)
# - enhancement (for improvements)
# - good first issue (for newcomers)
```

## Manual Setup (if not using GitHub CLI)

1. Go to Settings → Labels in your repository
2. Create each label with the specified color and description
3. You can keep useful default labels like "bug" and "documentation"