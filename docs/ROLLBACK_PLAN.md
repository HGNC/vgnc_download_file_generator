# Rollback Plan — VGNC Download Files Release

## Scope

This plan covers deployment of the `vgnc-download-file-generator` Cloud Run job image
and associated runtime configuration used by Airflow orchestration.

## Trigger Conditions (rollback immediately)

- Job failures exceed baseline by **2x** over two consecutive scheduled runs
- New data integrity issues detected in generated TSV/JSON outputs
- End-to-end runtime increases by **>50%** versus baseline median
- Critical/high security issue discovered in shipped artifact or dependency
- Production incident report from downstream consumers caused by this release

## Rollback Strategy

### Fastest path (preferred): revert runtime to previous known-good image

1. Identify the previous stable image digest/tag.
2. Update the Cloud Run Job to use that image.
3. Re-run one controlled species job (`VGNC_MODE=species`) as smoke test.
4. Resume normal schedule only after verification passes.

### Alternative path: revert code and redeploy

1. `git revert <bad_commit_sha>` (or reset release branch to prior good SHA).
2. Build and push image from reverted commit.
3. Update Cloud Run Job image reference.
4. Execute smoke run and verify outputs.

## Data and Storage Considerations

- The generator already removes partial GCS objects on failed writes.
- If bad full files were published, restore previous known-good objects from bucket
  version history (if object versioning enabled) or re-run generator from prior image.
- No schema migration rollback is required for this component (read-only data access).

## Verification After Rollback

- Cloud Run Job run status: success
- Logs: no new error patterns
- Generated object paths and counts match expected baselines
- Spot-check key files:
  - `json/all/all_vgnc_gene_set_All.json`
  - `tsv/all/all_vgnc_gene_set_All.tsv`
  - `ensembl/VGNC_to_Ensembl_mapping.txt`

## Communication

- Notify pipeline owners and downstream consumers in release channel.
- Include trigger condition, rollback action taken, and next follow-up ETA.

## Estimated Recovery Time

- Image rollback and smoke run: **5–15 minutes**
- Full confidence validation across all species mode: **30–90 minutes**
