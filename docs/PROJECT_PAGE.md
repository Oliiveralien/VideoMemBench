# Project page

The static website lives in [`project-page/`](../project-page/). It includes the
video-frame hero, reversible scroll animations explaining the two dependency
types, four video conversations, the 128-frame leaderboard, 64/32-frame
comparisons, evaluation definitions, and citation information.

## Local preview

From the repository root, run:

```bash
python scripts/preview_project_page.py --port 8765
```

Open <http://127.0.0.1:8765/>. The preview server supports byte-range requests for
seeking within the case videos. Use HTTP rather than opening `index.html`
directly: the case data and animated SVGs load through `fetch()`.

No Node.js build or Python package installation is required for this preview.

## GitHub Pages

The deployment workflow is
[`Deploy project page`](../.github/workflows/pages.yml). It uploads only the
`project-page/` directory.

Before the first deployment, a repository administrator must select **Settings →
Pages → Build and deployment → Source → GitHub Actions**. GitHub Pages must be
available for the repository's visibility and account plan.

Then select **Actions → Deploy project page → Run workflow → main**. The
successful deployment provides the website URL in the workflow run. Add that
confirmed URL to the README and repository About field after deployment.

Deployment is manual, so uploading the source does not attempt to publish a site
before Pages is configured. Run the workflow again after subsequent website
updates.

## Files to edit

| Content | File |
| --- | --- |
| Page text, authors, links, and initial result tables | `project-page/index.html` |
| Hero layout and frame mosaic | `project-page/hero.css` |
| Body typography, tables, evaluation, and footer | `project-page/content.css` |
| Dependency illustrations and scroll animation | `project-page/assets/*-memory.svg`, `project-page/memory-motion.*` |
| Interactive video cases | `project-page/case-study.*`, `project-page/assets/case-study/` |
| Main results | `project-page/assets/results.json` |
| Frame-count comparisons | `project-page/assets/frame-results.json`, `project-page/frame-results.*` |

When updating results, keep the JSON, initial HTML tables, and README tables in
sync. The displayed scores are taken from the manuscript; do not derive missing
frame budgets from other results.

Keep the media provenance and icon license files alongside the assets. The page's
dataset notice refers to annotation terms; source videos retain their original
rights and terms. The evaluation repository's terms remain in
[`LICENSE`](../LICENSE).
