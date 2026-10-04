# Activity Log fixtures (Task 9B.1)

`rg_tag_writes.json`: six REST-shaped Activity Log records (the shape `az monitor
activity-log list` returns), sanitized from a read-only query of the real resource
group `aitdd-dev-main-rg` on 2026-10-03/04 (see PROJECT_PLAN.md, Phase 9B, "Verified
Azure event shape"). The raw query output is not in the repository.

What the records show (the verified shape of a tag edit):

- three operations of `Microsoft.Resources/tags/write`, each two rows sharing one
  `correlationId`: `BeginRequest` / `Started` on
  `<rg-id>/providers/Microsoft.Resources/tags/default`, then `EndRequest` /
  `Succeeded` (subStatus `OK`) on `<rg-id>` itself;
- two operations from the Azure CLI (2026-10-03) and one from the Azure Portal
  (2026-10-04, the manual tag test of drift run 37197574080);
- `submissionTimestamp - eventTimestamp` between about 49 and 112 seconds;
- no property values: `properties` holds only `entity`, `eventCategory`,
  `hierarchy`, `message` (and `statusCode` on the Succeeded row).

Copied unchanged: event and submission timestamps (including Azure's seven
fractional digits), operation names, statuses and subStatuses, categories, levels,
event names, resource provider and type, the HTTP method, the resource group name
(public in `terraform/environments/dev/dev.tfvars`), the claims `idtyp` and `appid`
(the `appid` values are Microsoft's public first-party application IDs for the Azure
Portal and the Azure CLI).

Replaced: subscription and tenant IDs, event, correlation, operation and client
request IDs (synthetic `00000000-0000-4000-...` GUIDs), the caller and every name or
UPN claim (`user@example.invalid`, `Example User`), the object ID claim, IP addresses
(documentation ranges `203.0.113.0/24`, `198.51.100.0/24`, `2001:db8::/32` only) and
the `hierarchy` and request URI values. All other claims were dropped. The remaining
claims and the IPs are markers the tests require never to reach the evidence.
