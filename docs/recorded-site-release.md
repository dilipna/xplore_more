# Recorded-site release procedure

This procedure is prepared, not executed. Obtain approval for the exact commit
before publishing source, running remote CI or creating a Vercel project. Never
deploy the connected backend or apply GCP Terraform as part of this website release.

1. Confirm the approved local commit and a clean working tree. Preserve its source
   ZIP, full-history Git bundle, web-only ZIP, capture manifest and validation logs.
2. Update the existing `improve/reviewable-problem-briefs` branch and PR #1 with
   the approved commit using a normal fast-forward push. If the remote has moved,
   stop and reconcile; never force-push over another session. Do not merge main.
3. Wait for every required CI job on that exact SHA, including the web production
   HTTP smoke test and Python recovery receipts. A previous revision's green run
   is insufficient. A correction requires fresh exact-commit approval.
4. Reconfirm team `asmq333` and Hobby plan. The read-only inventory checked for this
   release has five projects and no XploreMore project. Create a separate project
   named `xploremore` only if explicitly approved and still absent. Do not reuse or
   modify ProToPro, OpsVerse, WC26 or another existing project. If creation requires
   a paid upgrade, stop; there is no spending authorization.
5. Use the official Vercel CLI with the existing isolated login directory
   `work/protopro-vercel-session`. Do not print/read its credentials or copy them
   into release artifacts. Use the exact approved web-only source at project root,
   with Next.js, Node 24 and the pinned pnpm lockfile. Keep default recorded mode;
   no API key, model provider, database, Redis or Git auto-deploy connection is needed.
6. Stage a preview deployment first. Check homepage, source details, keyword search,
   map links/layers, ranking, topic persistence and actual draft/capture downloads.
   Verify `/api/capture` keeps the preview origin and its bytes match the manifest.
   Inspect the deployed environment's console and phone layout. A local pass does
   not establish a preview pass.
7. Promote that exact successful preview only within the approved scope. Record
   its assigned URL and deployment identity. Do not claim ownership of the generic
   `xploremore.vercel.app` hostname before Vercel actually assigns it. Confirm the
   promoted domain serves the same capture and website. Retain this first version
   as the rollback target for future updates.

The final release evidence must distinguish local checks, remote CI, preview QA
and public promotion. The website is a recorded product demonstration; full live
ingestion and hybrid retrieval remain documented local capabilities.
