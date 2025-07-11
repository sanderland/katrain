# KaTrain Project Management Guide

## Quick Start

### 1. Set Up GitHub Repository Structure

1. **Create Labels** (run from repo root):
   ```bash
   # If you have GitHub CLI installed:
   sh .github/scripts/setup-labels.md
   
   # Or create manually in Settings → Labels
   ```

2. **Create Milestones** in GitHub:
   - Go to Issues → Milestones → New milestone
   - Create these 5 milestones:
     1. "Analysis Complete" (Due: 1 week from start)
     2. "Build Environment Ready" (Due: 2 weeks from start)
     3. "KataGo Metal Binary" (Due: 5 weeks from start)
     4. "Working Application" (Due: 7 weeks from start)
     5. "Production Ready" (Due: 8 weeks from start)

3. **Create Project Board**:
   - Go to Projects → New project → Board view
   - Name: "KaTrain macOS Metal Compilation"
   - Add columns: Backlog, Ready, In Progress, In Review, Testing, Done

### 2. Create Initial Issues

Use the templates in `.github/issues/phase1-issues.md` to create the first batch of issues.

### 3. Working with Issues

1. **Creating New Issues**:
   - Use the appropriate template (bug, compilation task, documentation, research)
   - Assign to milestone
   - Add relevant labels
   - Link dependencies

2. **Moving Through the Board**:
   - **Backlog**: New issues land here
   - **Ready**: All dependencies resolved
   - **In Progress**: Assign to yourself and move here when starting
   - **In Review**: When PR is created
   - **Testing**: Implementation done, testing in progress
   - **Done**: Merged and complete

### 4. Pull Request Workflow

1. Create feature branch: `git checkout -b feature/issue-number-description`
2. Make changes and commit
3. Push and create PR using the template
4. Link to issue with "Closes #XX"
5. Request review
6. Merge when approved

### 5. Progress Tracking

- **Daily**: Update issue status on project board
- **Weekly**: Review milestone progress
- **Per Phase**: Create retrospective issue to document lessons learned

## Key Files

- **Roadmap**: `docs/COMPILATION_ROADMAP.md`
- **Issue Templates**: `.github/ISSUE_TEMPLATE/`
- **PR Template**: `.github/pull_request_template.md`
- **Label Setup**: `.github/scripts/setup-labels.md`

## Best Practices

1. **One issue, one PR** - Keep changes focused
2. **Update issues immediately** - Don't let the board get stale
3. **Document decisions** - Use issue comments for important decisions
4. **Link everything** - Cross-reference related issues and PRs
5. **Test before closing** - Ensure acceptance criteria are met

## Useful GitHub Commands

```bash
# Create issue from CLI
gh issue create --template compilation_task.md

# List issues for current milestone
gh issue list --milestone "Analysis Complete"

# Create PR linked to issue
gh pr create --base main --assignee @me --body "Closes #123"

# View project board status
gh project list
```