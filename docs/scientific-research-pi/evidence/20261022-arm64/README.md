# ARM64 validation evidence, 2026-10-22

These files contain isolated test results and public image metadata, not credentials.
The network probes used the existing API base image; the model probe used the
acceptance derivative of the final worker image. Neither is a production rollout.

- linux-suite-87d68c0f.log: 146 tests, all passed, no skips.
- linux-os-87d68c0f.log: 7 additional actual Linux containment tests, all passed.
- model-probe-report.json: actual Pi + scientific gateway two-request bash roundtrip.
- api-overlay-test.json: actual read-only whole-package mount import test.
- network reports: baseline, same-node baseline and restricted facts, including unknowns.

Candidate worker digest: sha256:dbdf5c05fdf669b16ed065fbbe19f094244542e2a26639c880115ac284e6a04b.
API digest: sha256:89caf56457ee7f778ebe26337278ca3ede6bf6550d7f6339386473c18dcfbaa9.
Acceptance derivative digest: sha256:944b3a3add1778b803fed88475d8e1ff171ef93873cd40c1859512e6dd27facf.
