# Institution catalogue sources

The picker combines the local catalogue, MOET names/codes, SWOT domains/alternate
names, and reviewed community submissions. It is not a complete national directory
or an accreditation registry.

## Pinned inputs

- `legacy.json`: original 540-entry `server/university.json`, retained to preserve
  identifiers and reproduce this import. Its provenance/freshness is unknown.
- `moet.json`: projection of all 405 records returned by MOET on 2026-09-12.
  Stores only ID, code, and institution name, not contact details. Read using
  `POST https://tuyensinh.moet.gov.vn/ts/ThongTinTruong/GetData`, with form fields
  `indexPage=1`, `pageSize=100`, `type=1`, `sortQuery=` and empty
  `searchModel[Type]`, `searchModel[Code]`, `searchModel[Name]`. Request every page
  through `TotalPage`; verify `Count` and distinct IDs. `RenderSupportType` returns
  only the initial 20 records. `pageSize=-1` does not return all records.
  The list includes parent universities, research institutes, and campuses;
  these are not 405 independent universities.
- `swot.json`: `.vn` domain/name projection of JetBrains/swot revision
  `344e71ac76fcbd6dd4b42a78bb794ed4b14c8faa`, retrieved 2026-09-12. Contact/URL
  lines are omitted. This covers 385 domain files, not 385 unique schools.
  Vietnamese institutions with only non-`.vn` domains are not covered by this
  projection. See https://github.com/JetBrains/swot and `SWOT-LICENSE.txt` (MIT).
- `overrides.json`: explicit mappings for ambiguous codes/domains, additions, and
  retirement reasons. A retirement hides a duplicate or out-of-scope record
  without deleting it or breaking existing profile links.

MOET names/codes are preferred. Existing abbreviations remain available, older
names/codes become aliases, and SWOT contributes names/domains. Generic or
conflicting names and shared `.group` domains require review. Unmatched SWOT
records are only added when explicitly included in `add_domains`; otherwise
`review.json` retains them as candidates. No fuzzy matching merges records.

Legacy province names are retained as aliases and in provenance, not displayed
as current locations. No automatic 63-to-34 province conversion or inferred
school rename is performed. A verified current location can be supplied in
`records` overrides. Legacy-only schools remain available from the previous
catalogue; the report identifies them as not newly verified by MOET.

## Build and import

From `server/`, using the project's Python environment:

```sh
python manage.py build_institution_catalogue
python manage.py migrate
python manage.py import_institutions --dry-run
python manage.py import_institutions
```

The build is offline, validates the complete output, writes `university.json`
and `data/institutions/review.json`, and never writes the database. Inspect the
report and diff before importing refreshed sources. Import validates before any
writes and uses one transaction. It reports created, updated, and unchanged rows;
repeating it preserves IDs. Dry runs do not save rows or consume sequence values.

For a future source refresh, preserve identifiers added since this snapshot:

```sh
python manage.py build_institution_catalogue --base university.json --output /tmp/institutions-next.json --report /tmp/institutions-review.json
python manage.py import_institutions --path /tmp/institutions-next.json --dry-run
```

Keep the reviewed output as the next `university.json`. New identities derive
from the MOET upstream ID or the first approved SWOT domain, never a province
code or label. Once created, their catalogue `value` and database ID remain stable.
Rows missing from a later file are not deleted automatically. Imported metadata
never automatically re-approves a staff-rejected or pending record. An explicit
source retirement does hide an existing record.

## Community review

Registration/profile forms allow a missing institution to be entered as text.
The backend normalizes/reuses the label and saves it as `CUSTOM/PENDING`; this
does not block registration. In Django Admin, filter by `source=CUSTOM` and
`review_status=PENDING`, verify the name, then change `review_status` to `VERIFIED`.
The same row becomes searchable and selectable by everyone; user links remain
intact. Reject invalid entries with `REJECTED`. Pending/rejected entries stay out
of public search, but users can keep an existing affiliation when editing other
profile fields.

Approval means accepted for the picker, not accredited, nor proof of attendance.
Imports leave custom entries untouched. Merging custom synonyms remains a staff
curation task; approval alone does not guess or merge identities.

## Future dataset contributions

A public workflow for proposing dataset additions and corrections is planned
separately from registration's "school not found" input. Registration creates an
application institution record; it does not submit a dataset contribution or
update the versioned JSON files. Dataset contributions will have their own source
evidence and maintainer review before publication.
