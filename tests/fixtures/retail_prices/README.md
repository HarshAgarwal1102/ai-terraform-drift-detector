# Azure Retail Prices API samples (Task 10.4)

Real, unmodified `Items` returned by the public, unauthenticated Azure Retail Prices API
(`https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview`) on 2026-10-11 for
Central India. Each file records the exact `$filter` it was fetched with. Only `Items`,
`NextPageLink` and `Count` are kept.

These are Microsoft's public list prices and contain no project data. Prices change over time, so
the tests pin these samples instead of calling the API. To refresh them, re-run the same filters and
review every changed amount in the tests.
