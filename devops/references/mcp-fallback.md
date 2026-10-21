# MCP fallback: no `az` login

Read this only when `devops.py` says ADO was not read (no `az`, no `AZURE_DEVOPS_EXT_PAT`). The git work
still runs in the scripts; only the ADO calls move to the Azure DevOps MCP tools. The guard still holds:
a release or sync PR needs an approved plan with the exact branch names, and a `/Release Notes` page
must be the rendered page, unchanged. No MCP server either: stop and tell the user to run `az login` or
connect the Azure DevOps MCP server.

Below, `devops.py` means `python "${CLAUDE_PLUGIN_ROOT}/scripts/devops.py"`.

## release-prep

The scan still plans one PR per Ready repo, with the work-item **candidates** unchecked.

1. Per ADO project in the scan, one call each (omit `repositoryId`, so one call covers every repo):
   `repo_list_pull_requests_by_repo_or_project project=<p> targetRefName=refs/heads/<source> status=Active`
   (each source casing the scan printed). Report each: a repo that was Up to date needs a release PR
   this run did not raise once it merges; a Ready repo picks it up only if it merges before the release
   PR completes. Then the same with `targetRefName=refs/heads/<target>`: a repo with an open release PR
   gets no second one.
2. Check the candidates in one batch: `wit_get_work_items_batch_by_ids` (or `wit_work_item
   action=get_batch`), fields `System.Id, System.Title, System.WorkItemType, System.State`. Work items
   can live in another project than the repo. Keep only the ids that come back.
3. Ask the plan's question (step 3 of the skill). After the Yes, `devops.py release show --version <v>
   --items` prints each planned PR. Create each with the PR tool, `sourceRefName`/`targetRefName`
   exactly as printed, the printed title and description, `workItems` = the checked ids (a subset of the
   plan's). Create them in parallel.
4. Read the links back (`repo_get_pull_request_by_id includeWorkItemRefs=true`) and link what is missing
   with `wit_link_work_item_to_pull_request` (both project GUIDs for a cross-project link: get them from
   `repo_get_repo_by_name_or_id`).

## sync-team-branches

1. Team-sync work item: search the project for a Feature titled like "Branch Synchronizations" (create
   it if none), then create a Tech Story `sync team branches (yyyy/mm/dd)` under it (or read the id the
   user gave and check its project). Then `devops.py sync techstory --project <p> --id <n> --no-check
   --title "<title>"`.
2. `devops.py sync plan` as usual (git only). After the Yes, `devops.py sync show --source <s>
   --destination <d>` prints each planned PR: create each with the PR tool exactly as printed, its
   `workItems` the one tech story id.
3. Read each PR's linked work items; remove every link but the tech story's (`wit_work_item_link_write`
   action remove, or unlink in ADO). Then `devops.py sync record --source <s> --destination <d> --repo
   <r> --pr <id> --url <url>` for each, so the report lists them.
4. No PR tool either: give the user the "Create a pull request" link from the push output, as a list.

## release-notes

1. `repo_list_pull_requests_by_repo_or_project project=<p> status=Active top=50` (no `repositoryId`).
   Keep target branches starting `refs/heads/release/`, newest first; a gap over 2 hours starts an older
   release: keep the newest group. A named PR: `repo_get_pull_request_by_id`; a commit:
   `repo_list_pull_requests_by_commits`.
2. Per PR, its linked work item ids; then the items in one batch with `System.Id, System.Title,
   System.WorkItemType, System.State, System.Parent, System.Tags, System.AssignedTo, System.AreaPath,
   System.TeamProject, Microsoft.VSTS.Common.Priority`; then their parents, again in batches, up to Epic.
3. Save it in this shape and run `devops.py notes ingest --file <file>`; carry on from *Detect*:

```json
{"org": "Org", "project": "Proj",
 "prs": [{"id": 2360, "repo": "Gateway", "project": "Proj", "title": "...", "source": "team/1.0.2",
          "target": "release/1.0.2", "created": "2026-07-17T10:00:00Z",
          "url": "https://dev.azure.com/Org/Proj/_git/Gateway/pullrequest/2360"}],
 "workItems": {"11279": {"id": 11279, "type": "Bug", "title": "...", "state": "Resolved", "parent": 11200,
                         "tags": ["UAT"], "assignee": "Ann Lee", "priority": 2, "project": "Proj",
                         "area": "Proj\\Gateway", "url": "https://dev.azure.com/Org/Proj/_workitems/edit/11279"}},
 "prWorkItems": {"2360": [11279]}}
```

4. Publish after the Yes with `wiki_list_wikis project=<p>` (the project wiki, `<Project>.wiki`; none:
   the user creates it), then `wiki_create_or_update_page` with the content of the run's `wiki.md` file
   exactly as rendered and the path render printed. Then the `/Release Notes` index: read it, put the
   run's `indexLine` (in its `meta.json`) first under `## Releases`, write it back. Link the entry from
   the `gitItemPath` the page write returned (a `-` in a page name is `%2D`).
