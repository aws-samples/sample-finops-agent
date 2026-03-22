---
name: fix-issue
description: Implement a GitHub issue by exploring the codebase, planning, and creating a PR
argument-hint: <issue-number> <issue-title> <issue-body>
disable-model-invocation: true
context: fork
---

You are an autonomous software engineer working on a GitHub issue.

## Issue Details
$ARGUMENTS

## Workflow

### Phase 1: Understand the Codebase
- Read CLAUDE.md and any project documentation
- Explore the directory structure and key files
- Understand existing patterns, conventions, and architecture
- Identify the files and modules relevant to this issue

### Phase 2: Plan the Implementation
- Design your approach based on what you learned about the codebase
- Consider edge cases and potential impacts on existing functionality
- Identify all files that need to be created or modified
- Write out your plan before making any changes

### Phase 3: Implement
- Make the changes following existing code patterns and conventions
- Write clean, well-structured code consistent with the project style
- Include tests if the project has a test suite
- Keep changes focused and minimal — only what's needed for the issue

### Phase 4: Verify & Commit
- Review your changes for correctness
- Run any available linters or tests
- Commit with a clear message referencing the issue
- Create a PR with a description of what was changed and why
