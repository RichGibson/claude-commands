Stage, commit, and push changes in the current git repository.

Steps:

1. Run these in parallel to understand the current state:
   - `git status` — see what's changed and untracked
   - `git diff` — see unstaged changes
   - `git diff --cached` — see already-staged changes
   - `git log --oneline -5` — see recent commits for context

2. Decide what to stage. If $ARGUMENTS names specific files, stage only those. Otherwise stage all modified and relevant untracked files. Do NOT stage: `.env`, credential files, large binaries, or files that look like they contain secrets.

3. Draft a commit message using conventional commit format:
   ```
   <type>: short summary
   ```
   Types: `feat` (new feature), `fix` (bug fix), `refactor` (internal change), `docs` (documentation), `chore` (maintenance), `perf` (performance).

   Show the user the proposed commit message and the list of files to be staged. Ask: "Commit and push with this message? (yes / edit / cancel)"

4. Wait for confirmation before proceeding. If they say "edit", ask what they want the message to be. If "cancel", stop.

5. On confirmation:
   - `git add <files>`
   - `git commit -m "<message>\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"`
   - `git push`

6. Report the result: commit hash, branch pushed to, and remote URL.
