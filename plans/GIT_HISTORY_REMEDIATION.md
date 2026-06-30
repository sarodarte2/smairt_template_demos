# Git History Remediation Before Public Release

This note documents data-exposure issues that live in the **Git history and
commit metadata**, not in the current working-tree files. Editing tracked files
(which the public-release cleanup already did) does **not** remove these,
because Git retains every past commit, author record, and reflog entry. They
must be addressed before, or as part of, making the repository public.

---

## What is exposed

### 1. Personal email in commit author metadata

Every commit is authored by:

```
Salvador Rodarte <sarodarte2@miners.utep.edu>
```

This personal university email is embedded in the author and committer fields of
all commits and will be visible to anyone who clones or browses the public repo.

### 2. Internal machine hostname leaked in remote metadata

The reflog / remote `set-head` records contain:

```
Rodarte <salvador.rodarte@PNNL-GG4LMCQ97N.(none)>
```

`PNNL-GG4LMCQ97N` is an **internal PNNL machine name**. Hostnames like this can
aid reconnaissance and should not be published.

### 3. Commit messages reference internal context

Some commit messages reference internal naming and process (for example
"Updated Demos for Publishing Purposes"). These are low risk but worth a quick
review while rewriting history.

> Note: The current working-tree files are clean after the public-release pass —
> PNNL API endpoints, Birthright/ai-incubator references, and author placeholder
> emails have been removed or genericized. The legitimate scientific identifiers
> (`PNNL_SM*`, `PNNL_D15_*`) in the HVP dataset are intentionally retained.

---

## Recommended remediation

Pick one of the options below. **Option A is simplest and safest** for a first
public release.

### Option A — Publish with fresh history (recommended)

Create a brand-new history with no past commits, authored under a neutral
identity. This guarantees no leaked emails, hostnames, or commit messages.

```bash
# From inside the repository, set a neutral identity FIRST
git config user.name  "SMAIRT Demos"
git config user.email "demos@example.com"

# Create a clean, single-commit history on a new orphan branch
git checkout --orphan public-release
git add -A
git commit -m "Initial public release of SMAIRT demo collection"

# Replace main with the clean branch
git branch -D main
git branch -m main

# Push to the PUBLIC remote with a fresh history
# (force-push only to the intended public repo, never to an internal mirror)
git push --force public main
```

### Option B — Rewrite author/committer identity across all history

Keeps the commit graph but rewrites every author/committer record. Requires
[`git filter-repo`](https://github.com/newren/git-filter-repo).

Create a `mailmap.txt`:

```
SMAIRT Demos <demos@example.com> Salvador Rodarte <sarodarte2@miners.utep.edu>
SMAIRT Demos <demos@example.com> Rodarte <salvador.rodarte@PNNL-GG4LMCQ97N.(none)>
```

Then run:

```bash
git filter-repo --mailmap mailmap.txt
```

This rewrites all commit SHAs. Re-add the public remote and force-push.

### Option C — Rewrite identities inline (no extra tooling)

```bash
git filter-branch --env-filter '
NEW_NAME="SMAIRT Demos"
NEW_EMAIL="demos@example.com"
export GIT_AUTHOR_NAME="$NEW_NAME"
export GIT_AUTHOR_EMAIL="$NEW_EMAIL"
export GIT_COMMITTER_NAME="$NEW_NAME"
export GIT_COMMITTER_EMAIL="$NEW_EMAIL"
' --tag-name-filter cat -- --branches --tags
```

`git filter-repo` (Option B) is preferred over `filter-branch`, which is slow
and deprecated.

---

## After rewriting (required cleanup)

1. **Set a persistent neutral identity** so future commits don't re-leak:
   ```bash
   git config user.name  "SMAIRT Demos"
   git config user.email "demos@example.com"
   ```
2. **Expire reflogs and garbage-collect** so old objects are not recoverable:
   ```bash
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   ```
3. **Verify** nothing sensitive remains:
   ```bash
   git log --all --format='%an <%ae> | %cn <%ce>' | sort -u
   git log --all --oneline | grep -iE 'pnnl|birthright|ai-incubator|miners\.utep'
   ```
   The first command should show only the neutral identity. The second should
   return nothing.
4. **Push to a clean public remote.** Do not force-push rewritten history over an
   existing internal/shared remote that others have already cloned.

---

## Checklist

- [ ] Neutral `user.name` / `user.email` configured
- [ ] History rewritten (Option A, B, or C)
- [ ] `sarodarte2@miners.utep.edu` no longer in any commit
- [ ] `PNNL-GG4LMCQ97N` hostname no longer in any commit/reflog
- [ ] Reflogs expired and `git gc --prune=now` run
- [ ] Verification greps return clean
- [ ] Pushed to the intended public remote only
