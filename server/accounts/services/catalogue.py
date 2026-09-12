"""Build a reviewable catalogue from saved sources; never writes to the database."""

import copy
import hashlib
import re
import unicodedata


def name_key(value):
    value = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    return re.sub(
        r"[^a-z0-9]+", " ", "".join(c for c in value if not unicodedata.combining(c))
    ).strip()


def unique_strings(items):
    return sorted(
        {" ".join(item.split()) for item in items if item.strip()},
        key=lambda s: (s.casefold(), s),
    )


def is_school(name):
    return bool(
        re.search(
            r"\b(university|college|academy|institute|high school|highschool|upper secondary|truong|dai hoc|cao dang|hoc vien|thpt|pho thong)\b",
            name_key(name),
        )
    )


def build_catalogue(base, moet, swot, overrides, revision):
    records = copy.deepcopy(base)
    report = {
        "unresolved": [],
        "moet_added": 0,
        "moet_matched": 0,
        "swot_added": 0,
        "swot_matched": 0,
    }
    for row in records:
        for field in ("label", "code", "shortName", "eng", "type", "location"):
            row[field] = " ".join(row.get(field, "").split())
        row["value"] = str(row["value"])
        row.setdefault("aliases", [])
        row.setdefault("domains", [])
        row.setdefault("provenance", [{"source": "legacy", "value": row["value"]}])
        for source in row["provenance"]:
            if source["source"] == "legacy":
                source.setdefault("label", row["label"])
                source.setdefault("eng", row["eng"])
        # Preserve historical locations for search, not as claims about current
        # administrative boundaries. Current locations can be curated explicitly.
        if row["location"] and any(p["source"] == "legacy" for p in row["provenance"]):
            row["aliases"].append(row["location"])
            for source in row["provenance"]:
                if source["source"] == "legacy":
                    source.setdefault("location", row["location"])
            row["location"] = ""
    by_value = {r["value"]: r for r in records}
    if len(by_value) != len(records):
        raise ValueError("Duplicate catalogue values")
    for value, reason in overrides.get("retired", {}).items():
        row = by_value[value]
        row["review_status"] = "REJECTED"
        row["retirement_reason"] = reason
    for value, changes in overrides.get("records", {}).items():
        row = by_value[value]
        row["aliases"].append(row["label"])
        row["aliases"].extend(changes.get("aliases", []))
        row.update({key: value for key, value in changes.items() if key != "aliases"})

    def active():
        return [r for r in records if r.get("review_status") != "REJECTED"]

    def trusted_names(row):
        # SWOT names enrich search, but cannot become evidence for matching more
        # SWOT identities on a later build (generic names can spread otherwise).
        names = [row["label"], row["eng"]]
        for source in row["provenance"]:
            if source["source"] in ("legacy", "moet"):
                names.extend([source.get("label", ""), source.get("eng", "")])
        names.extend(
            overrides.get("records", {}).get(row["value"], {}).get("aliases", [])
        )
        return {name_key(name) for name in names if name}

    def add_row(identity, label):
        value = hashlib.sha256(identity.encode()).hexdigest()[:32]
        if value in by_value:
            raise ValueError(f"Unresolved identity collision: {identity}")
        row = {
            "value": value,
            "label": label,
            "code": "",
            "shortName": "",
            "eng": "",
            "type": "",
            "location": "",
            "aliases": [],
            "domains": [],
            "provenance": [],
        }
        records.append(row)
        by_value[value] = row
        return row

    def provenance(row, source):
        # Replace the same source identity on refresh instead of accumulating copies.
        identity = "domain" if source["source"] == "swot" else "id"
        row["provenance"] = [
            p
            for p in row["provenance"]
            if not (
                p.get("source") == source["source"]
                and p.get(identity) == source[identity]
            )
        ]
        row["provenance"].append(source)

    seen_moet = set()
    for item in moet:
        code, label, upstream_id = (
            item["MA"].strip(),
            item["TEN_DON_VI"].strip(),
            item["Id"],
        )
        if upstream_id in seen_moet:
            raise ValueError(f"Duplicate MOET ID: {upstream_id}")
        seen_moet.add(upstream_id)
        row = None
        if target := overrides.get("moet", {}).get(code):
            row = by_value[target]
        else:
            matches = [
                r
                for r in records
                if any(
                    p.get("source") == "moet" and p.get("id") == upstream_id
                    for p in r["provenance"]
                )
            ]
            if not matches:
                matches = [
                    r for r in active() if r["code"].casefold() == code.casefold()
                ]
            if not matches:
                matches = [r for r in active() if name_key(label) in trusted_names(r)]
            if len(matches) == 1:
                row = matches[0]
            elif len(matches) > 1:
                raise ValueError(
                    f"MOET code {code} matches multiple existing records; add an explicit mapping"
                )
        if row is None:
            row = add_row(f"moet:{upstream_id}", label)
            report["moet_added"] += 1
        else:
            report["moet_matched"] += 1
            row["aliases"].append(row["label"])
            if row["code"] and row["code"] != code:
                row["aliases"].append(row["code"])
        row["label"], row["code"] = label, code
        provenance(
            row, {"source": "moet", "id": upstream_id, "code": code, "label": label}
        )

    for value, label in overrides.get("labels", {}).items():
        row = by_value[value]
        row["aliases"].append(row["label"])
        row["label"] = label

    matching_names = {row["value"]: trusted_names(row) for row in records}
    additions = set(overrides.get("add_domains", []))
    for item in sorted(swot, key=lambda r: (r["domain"] not in additions, r["domain"])):
        domain = item["domain"]
        names = unique_strings(
            n
            for n in item["names"]
            if not n.lower().startswith(("website:", "http:", "https:"))
        )
        names = [n for n in names if n != ".group"]
        target = overrides.get("swot", {}).get(domain)
        skipped = ".group" in item["names"] or domain in overrides.get(
            "skip_domains", {}
        )
        # Explicit corrections move ownership instead of leaving the old school
        # searchable by a domain which now belongs to another institution.
        if target or skipped:
            for previous in records:
                owned = domain in previous["domains"] or any(
                    p.get("source") == "swot" and p.get("domain") == domain
                    for p in previous["provenance"]
                )
                if owned and (skipped or previous["value"] != target):
                    previous["domains"] = [
                        d for d in previous["domains"] if d != domain
                    ]
                    previous["provenance"] = [
                        p
                        for p in previous["provenance"]
                        if not (p.get("source") == "swot" and p.get("domain") == domain)
                    ]
                    previous["aliases"] = [
                        a for a in previous["aliases"] if a not in names and a != domain
                    ]
        if skipped:
            report["unresolved"].append(
                {
                    "source": "swot",
                    "domain": domain,
                    "names": names,
                    "reason": overrides.get("skip_domains", {}).get(
                        domain, "Shared domain; not a single institution"
                    ),
                }
            )
            continue
        if not target and (not names or not any(is_school(n) for n in names)):
            report["unresolved"].append(
                {
                    "source": "swot",
                    "domain": domain,
                    "names": names,
                    "reason": "Institution name/scope needs review",
                }
            )
            continue
        if target:
            matches = [by_value[target]]
        else:
            matches = [r for r in records if domain in r["domains"]]
            if not matches:
                keys = {name_key(n) for n in names}
                matches = [
                    r for r in active() if keys.intersection(matching_names[r["value"]])
                ]
        if len(matches) > 1:
            report["unresolved"].append(
                {
                    "source": "swot",
                    "domain": domain,
                    "names": names,
                    "candidates": [r["value"] for r in matches],
                    "reason": "Ambiguous name; no automatic merge",
                }
            )
            continue
        if matches:
            row = matches[0]
            report["swot_matched"] += 1
        else:
            if domain not in overrides.get("add_domains", []):
                report["unresolved"].append(
                    {
                        "source": "swot",
                        "domain": domain,
                        "names": names,
                        "reason": "Unmatched school; confirm identity and scope before adding",
                    }
                )
                continue
            school_names = [n for n in names if is_school(n)]
            vietnamese = [
                n
                for n in school_names
                if re.search(
                    r"\b(truong|dai hoc|cao dang|hoc vien|thpt|pho thong)\b",
                    name_key(n),
                )
            ]
            row = add_row(f"swot:{domain}", (vietnamese or school_names)[0])
            english = [n for n in school_names if n not in vietnamese]
            row["eng"] = english[0] if english else ""
            if any(
                re.search(
                    r"\b(high school|highschool|upper secondary|thpt|pho thong)\b",
                    name_key(n),
                )
                for n in names
            ):
                row["type"] = "THPT"
            elif any(
                re.search(
                    r"\b(university|college|academy|dai hoc|cao dang|hoc vien)\b",
                    name_key(n),
                )
                for n in names
            ):
                row["type"] = "Higher education"
            else:
                row["review_status"] = "PENDING"
            report["swot_added"] += 1
            matching_names[row["value"]] = trusted_names(row)
        row["aliases"].extend(n for n in names if is_school(n))
        row["domains"].append(domain)
        provenance(row, {"source": "swot", "domain": domain, "revision": revision})
    for row in records:
        row["aliases"] = unique_strings(a for a in row["aliases"] if a != row["label"])
        row["domains"] = unique_strings(row["domains"])
        row["provenance"].sort(
            key=lambda p: (
                p["source"],
                p.get("id", p.get("domain", p.get("value", ""))),
            )
        )
    return sorted(records, key=lambda r: r["value"]), report
