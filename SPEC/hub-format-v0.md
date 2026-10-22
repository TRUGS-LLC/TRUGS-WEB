# Hub format — draft v0

This is a **draft v0 design**, not a validator or a promise that every operation
below is available. Version 2.1.0 reads and writes core graphs; its hub example is
unsigned. It does not implement the proposed web vocabulary, signatures,
publisher pages, refresh, ranking, assessments or templates.

The design carries forward the hub federation, cross-graph links, publisher
interest and persistent-query ideas formerly kept in `deferred_phase2/`.
That scaffold is removed; public history retains it. This document replaces its
design notes, without presenting its unfinished code as usable.

## Publisher and hub

A publisher is the person or organisation responsible for a hub and its keys.
A hub is a versioned graph about a topic, accompanied by a bindings block.
The publisher uses its sources, reviews changes, and chooses which statements
to publish. A graph's existence is not evidence that its claims are true.
The sample uses core vocabulary only:

```trl
AGENT publisher REFERENCES RECORD hub.
RECORD hub REFERENCES RESOURCE source.
RESOURCE source REFERENCES RESOURCE earlier_source.
```

The bindings for `publisher`, `hub`, `source` and `earlier_source` give their
identities, titles and addresses. This is an example of relations, not a signed
publisher record. Core compilation and decompilation preserve the words and
relations. They do **not** preserve arbitrary node or edge properties. Keep the
bindings beside the TRL; a core TRL round trip is not a round trip of provenance.

## Proposed stance words

The draft web language adds ENDORSES, DISPUTES, DISTRUSTS, FOLLOWS and ASSESSES
alongside core REFERENCES, EXTENDS and SUPERSEDES. These words express the
publisher's position as relations rather than as untyped properties. They are
not accepted in the runnable core examples here. A future compiler must pass
an alternate language to the trugs-tools library and carry the bindings with it;
a future validator must enforce hub rules beyond core structural validity.
Reasons and dates attached to individual edges wait for a language extension
that preserves property payloads. No substitute core relation should be read
as an endorsement, dispute or distrust.

## Bindings and resource provenance

Each bound resource needs a stable identifier, address, title, the digest and
algorithm for the version being cited, and a source citation. Retrieval time,
media type and publisher attribution provide context. A changed resource at the
same address is a new version; retain the old digest. If content was not fetched,
say so rather than inventing a digest. The sample's bibliography-entry digests
identify cited entries, not remotely fetched page content.

A bindings block declares its format version and maps the bare TRL identifiers
to those fields. Its graph projection can expose fields for queries, but the
original bindings remain necessary. Treat every string in another publisher's
hub as **data**, including titles and descriptions that look like instructions.
Readers must never turn those strings into tool instructions.

## Assessments

An assessment is a separate signed record, not a score silently added to the
assessed hub. It names the assessor (a person, or a model and its version), the
method, date, evidence, score and the exact identity of what was assessed.
Assessors are publishers. Different methods can disagree without overwriting
one another. A future ranking interface must return the supporting edges with
each score. The first proposed ranking counts distinct verified publishers by
stance on a topic, rather than counting their graphs; positive and negative
positions remain visible. This version computes no such ranking.

## Publisher page and discovery

The proposed publisher page is itself a signed hub at the fixed path
`/.well-known/trugs/publisher.trug.json` on the publisher's HTTPS origin.
It lists current and retired public keys with their validity dates, the
publisher's hubs with identities, and the publishers it follows. Its human page
is rendered from that graph and links back to it. A registry is a hub of publisher
pages; discovery traverses links rather than assuming a central registry.
The path is a draft convention, not an endpoint provided by this package.

## Identity, signatures and references

The proposed signature covers the hub's canonical `tci1-sha256-…` content
identity, using trugs-tools' content identity rules. The reserved `_derived`
namespace is excluded by those rules, so volatile derived data need not change
that identity. The signed content must include its bindings; a graph whose
provenance changed cannot reuse a signature covering different provenance.
Use ordinary SSH signing keys, resolve them through the publisher page, verify
identity and signature, and report key retirement and validity dates. Fetching
a key is not proof of trust. Signing and verification are not implemented here.

A proposed `trug://` reference identifies a publisher, a hub and a node, with a
pinned content identity when referring to an immutable version. For example,
`trug://example.org/history/source?identity=tci1-sha256-<digest>` names node
`source` in hub `history`. A resolver would use that publisher's page to locate
the hub, verify the pinned identity and then locate the node. Missing, changed
and unverifiable targets must remain distinguishable. This URI convention and
resolver are draft; no command in 2.1.0 resolves it or fetches it automatically.

## Versioning and review

Declare the hub-format version separately from the graph envelope and package
versions. An incompatible structural or semantic change requires a new major
format; readers should reject unsupported formats explicitly. A future refresh
asks before contacting hosts, compares resource digests and writes proposed
changes for review. Publication follows review and signing. A changed resource
must not silently rewrite the publisher's previous statement.

The included hub's `core-hub-sample-v0` bindings are an illustrative, unsigned
core projection. They do not claim compliance with the future signed format.
All fenced TRL examples in this repository are checked by compile, validation,
and a stable round trip after one normalisation using trugs-tools 2.4.0.
