# Actual local application screenshots

These Playwright captures use the real local backend and explicitly synthetic
fixtures. They contain no private user datasets, credentials or customer results.
Both themes and representative desktop/mobile layouts are captured; the browser
tests check all six requested viewport widths.

| View | Screenshot |
|---|---|
| Product landing | [Dark desktop](landing-dark-1440.png), [dark mobile](landing-dark-390.png), [light](landing-light.png) |
| Authentication | [Login](login.png), [registration](register.png) |
| Project overview | [Dashboard](project-dashboard.png) |
| CSV workflow | [Upload](dataset-upload.png) |
| Dataset evidence | [Health](dataset-health.png), [leakage](leakage.png), [labels](labels.png) |
| Model evidence | [Valuation](valuation.png), [failure investigator](failure-investigator.png) |
| Subgroups and shifts | [Fairness](fairness.png), [drift](drift.png) |
| Improvement workflow | [Recommendations](recommendations.png), [experiments](experiments.png), [versions](versions.png) |
| Reports and privacy | [Reports](reports.png), [settings](settings-privacy.png) |
| Application themes/layout | [Light workspace](workspace-light.png), [mobile workspace](workspace-mobile.png) |

To regenerate from the repository root after building and starting the services:

```powershell
$env:DATAGENOME_SCREENSHOTS = "../docs/screenshots"
npm --prefix frontend run test:e2e
```

The relative output path is resolved from the frontend test working directory.
Inspect regenerated images before publishing, and use synthetic inputs only.
