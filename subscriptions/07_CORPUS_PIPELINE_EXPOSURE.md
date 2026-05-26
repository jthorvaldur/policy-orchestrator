# corpus-pipeline — PUBLIC REPO WITH CASE DATA

**Status: SECURITY ISSUE — immediate action required**
**Risk: Legal case emails publicly accessible, being actively cloned**

## The Problem

The `corpus-pipeline` repo at github.com/jthorvaldur/corpus-pipeline is PUBLIC and contains:
- 22,546 markdown files in `sdata/md/`
- Full email content from legal case files
- Your name and email address (joel.thorarinson@gmail.com) throughout
- Source paths revealing `/root/legal_backup/clumps_structure/divorce_work/case_files/`
- At least 22,520 files containing sensitive terms (names, case-related keywords)
- Topics tagged: nlp, pipeline, python, text-processing (making it discoverable)

## Traffic (last 14 days)
- 672 total clones, 34 unique cloners on peak day
- Clone spike: May 22 (286 clones), May 23 (311 clones)
- Referrers: github.com (3 unique visitors browsing individual files)
- Individual sdata/md/ files are being browsed

## Immediate Actions

### Step 1: Make Private
```bash
gh repo edit jthorvaldur/corpus-pipeline --visibility private
```

### Step 2: Assess Damage
- The repo has been public since May 19 (creation date)
- 672 clones means the data has been downloaded by others
- Git history contains all commits with the data
- Anyone who cloned has a full copy — cannot be recalled

### Step 3: Consider git history cleanup
If you want to make the repo public again (for the pipeline code, not the data):
1. Remove sdata/ from git history entirely using git-filter-repo
2. Add sdata/ to .gitignore
3. Push force to rewrite history
4. Make public again

### Step 4: Check other public repos for similar issues
```bash
for repo in bulldogs coherence-research dna-rights f1_stats gaba_glutamate jthorvaldur legal-symmetries legal-tax-ops marriage-counselling morpheme-page policy-orchestrator sovereign-legal words_quantum_legal; do
  echo "--- $repo ---"
  gh api "repos/jthorvaldur/$repo" --jq '.size' 2>/dev/null
done
```
Large public repos may contain similar data leaks.

## Notes
- The pipeline code itself is fine to be public — it's the sdata/ contents that are the problem
- Consider whether any of the cloners could be opposing counsel or their agents
- The "nlp" and "pipeline" topics attracted NLP researchers/bots who then found the data
