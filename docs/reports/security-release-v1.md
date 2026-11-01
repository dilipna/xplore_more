# Security correction after the first publication

October 23, 2026. Approved commit `1c6d829` was fast-forward published to existing
PR #1. Its CI run [39900932099](https://github.com/dilipna/xplore_more/actions/runs/39900932099)
passed Python, Go, web and both Terraform jobs. The source security scan and MCP
image scan failed. Remaining image jobs were cancelled by the matrix's existing
fail-fast behavior. No Vercel project, deployment or GCP resource was created;
main remains `fafd88258ea0dde4e4e1db5739424a150146248c`.

## Dependency correction

| Dependency | Published revision | Local correction |
|---|---|---|
| Next.js and its ESLint configuration | 16.3.8 | 16.4.1 |
| sharp (Next.js transitive dependency) | Prior locked dependency | 0.35.5 |
| certifi | 2026.7.22 | 2026.10.19 |
| Pillow | 12.3.0 | 13.0.0 |

The Next.js update addresses the reported image-optimization and cache advisories
and the server-action denial of service. See the upstream [image advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)
and [cache advisory](https://github.com/vercel/next.js/security/advisories/GHSA-673q-mjm6-r5xr).
The certificate update follows the upstream [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2).
Pillow's fixes are documented in its [13.0.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).
No scanner severity, exit code, ignore rule or build check was relaxed.

## Explicit Pillow compatibility exception

FastEmbed 0.8.0's metadata excludes Pillow 13. The current FastEmbed 0.9.0 metadata
also retains that exclusion, so upgrading FastEmbed alone would not resolve it.
The workspace declares a visible `pillow==13.0.0` uv override. This is an
application-maintained compatibility exception, not an upstream-supported version
combination. XploreMore uses FastEmbed's text-only CPU model; it exposes no image
embedding or image decoding workflow.

Before the override, `tools/check_embedding_compatibility.py --record` saved two
document embeddings and one retrieval-query embedding from the actual cached
BAAI/bge-small-en-v1.5 model. After the override, all three 384-dimensional vectors
were finite, normalized and exactly equal to that baseline (maximum absolute
difference 0.0). A separate Linux indexer-container run, with networking disabled,
produced the same vectors and loaded the baked model successfully. This measures
the application's selected text path; it does not certify FastEmbed image features
or every model. Revisit the exception when upstream supports the patched major.

## Local verification of the corrected revision

- All 176 backend tests pass, zero skips, in 44.92 seconds; one upstream dependency
  deprecation warning remains. Ruff/format and Pyright pass.
- All 19 web contracts, lint, TypeScript and the Next.js 16.4.1 production build
  pass. Production HTTP checks verify 12 HTML routes, 6 auxiliary routes, no
  recorded-mode upstream calls, authenticated connected proxy behavior, explicit
  HTTP 503 on upstream loss and the unchanged exact capture checksum.
- Web, MCP and indexer Docker builds pass. The web runtime serves health, homepage
  and the same capture bytes as UID 1000 in a read-only container.
- The same Trivy 0.70.0 high/critical, ignore-unfixed, exit-code-1 gate reports zero
  findings for the corrected clean source export and each of the three rebuilt
  runtime images. These local scans do not substitute for a fresh full remote CI.

The initial website's responsive/interactive browser evidence remains associated
with `1c6d829`. A patched-framework visual recheck was attempted but browser policy
rejected the saved tab's internal `data:` error-page URL. No fresh browser pass or
patched-version screenshot is claimed. The HTTP and container checks above are
independent server tests. A deployed preview must still pass browser verification
before promotion.

The correction is prepared locally. Its source publication, full CI and conditional
free website release need approval for its new exact commit under the user's
release rule. The earlier commit's authorization was used only for its publication
and CI; its failed gate did not authorize proceeding with hosting.
