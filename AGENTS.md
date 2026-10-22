# Agent Instructions (public distribution)

This repository is a read-only distribution of eSkillz public knowledge in
Open Knowledge Format (OKF) v0.2. `MANIFEST.yaml` describes it in
machine-readable form.

## Using the knowledge

1. Start at `knowledge/index.md` and open only the concepts you need.
2. Treat a concept as current only when `status: stable` and the present time
   is before `stale_after`. Treat `status: deprecated` as historical, and
   follow `superseded_by` when present.
3. Judge trust from `verified` (OKF v0.2 section 5.3): a `human:` actor means
   eSkillz staff reviewed the content; no `verified` entry means unverified.
4. Attribute specific claims through the footnotes in the body, which cite
   `sources[].id` entries in the frontmatter.
5. Preserve stated limitations and conditions. Do not infer pricing,
   contractual commitments, customer relationships, or capabilities that a
   concept does not state.
6. When concepts appear to conflict or a needed fact is missing, say so rather
   than guessing.

## Provenance

`publication.json` records the private source commit each publication was
built from, the publication time, and a SHA-256 hash of every concept file.
`knowledge/log.md` summarizes what changed.

## Rights

Copyright eSkillz. All rights reserved. No license is granted to copy,
modify, or redistribute this content.

## Maintaining this repository

Do not edit content here. Changes are made in eSkillz's private canonical
repository and published by pull request. Files edited here fail validation
and are overwritten by the next publication.
