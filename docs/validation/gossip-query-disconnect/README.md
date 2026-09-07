# Published validation evidence

This package contains machine-readable summaries from the completed isolated five-validator stock/fixed runs and selected Scala result lines. It contains no production keys, keystores, operator log exports, or public-network mutation.

- [Stock native result](stock-native.json): 17 checks passed; four injected query resets caused four escaped gossip-round failures.
- [Fixed native result](fixed-native.json): 17 checks passed; the same four-reset procedure caused zero escaped gossip-round failures.
- [Scala result extract](scala-results.txt): 570 passed, zero failed, two existing ignored tests; formatting and assembly passed.
- [Native protocol and interpretation](../../gossip-query-native-qualification.md).
- [Implementation, security tests and remaining limits](../../gossip-query-disconnect-recovery.md).

The JSON reports contain per-node timings, exact artifact identities, checked signer sets, error records from throwaway lab nodes, and hashes of retained raw logs. The full raw logs, keystores and test JAR are not included here. These are local validation results, not GitHub CI results or a formal security proof. Brief resets did not reproduce the multi-minute Mainnet slowdown in stock; no production reward-cadence improvement is claimed.

## Publication provenance

Command-line Git authentication was unavailable, so the existing GitHub connection published the commit series. GitHub assigned new commit IDs. Every published commit's complete Git tree was verified equal to its corresponding local tree. The final ten-commit series was fetched back and `git diff --exit-code` against local `18ebb677b5f255d4f6c2f1919aaf69a99b11df1c` passed. This additional commit publishes documentation/evidence only; it does not alter the tested code.

| Local research commit | Published commit | Identical Git tree |
| --- | --- | --- |
| `f31420fbaec90c261fd07ef3e70a41981d7ef299` | [`1c56258cb330cebbedc17502cdce0bc416ded55e`](https://github.com/Proph151Music/tessellation/commit/1c56258cb330cebbedc17502cdce0bc416ded55e) | `f54209ce000c1d7123117e0d04344f3a066e15d4` |
| `81b1757463992ddea992974323a5322288b3740c` | [`2fa965a9de95e3e18327b0f769bf5908f46bad40`](https://github.com/Proph151Music/tessellation/commit/2fa965a9de95e3e18327b0f769bf5908f46bad40) | `c90f101fc816735aa63875d38f3d20ee97cfdc69` |
| `758b72b6f2af2ed3d4e736287da5578e22768000` | [`33688cb43377b9a3e4f137323060e11b645ef317`](https://github.com/Proph151Music/tessellation/commit/33688cb43377b9a3e4f137323060e11b645ef317) | `3dc45ef1b2fd88ab8dcd517511238959abfa372d` |
| `d5974d88e87dcf6c872984d0137c3156616fefb6` | [`276bbeb1f3a2bbfcb7ab280efa62ea834140365a`](https://github.com/Proph151Music/tessellation/commit/276bbeb1f3a2bbfcb7ab280efa62ea834140365a) | `d3b43aed937c9e61e31c8c359ecb653eea623180` |
| `6c4022a0b9f3ffca2b3f966a0e0a91b4acc98db6` | [`ad44f55af3eb9472df456a9b80c162718722dc7a`](https://github.com/Proph151Music/tessellation/commit/ad44f55af3eb9472df456a9b80c162718722dc7a) | `ed81c43d161251fd981c5526c3e79ee8044de5fe` |
| `b7eb16ad695da2d083c1860570a7d6b6c34e06a3` | [`ec3590118b66d7603c8bafe3b2685e78d01fed4a`](https://github.com/Proph151Music/tessellation/commit/ec3590118b66d7603c8bafe3b2685e78d01fed4a) | `749309e65754b115f91f186b5ebc4a3dcb2c9272` |
| `99a9ee9b09dc2fee80b1253666d5b23fb86d8939` | [`e6b9ec672eb6776d1a9e84005b118503af8e23e0`](https://github.com/Proph151Music/tessellation/commit/e6b9ec672eb6776d1a9e84005b118503af8e23e0) | `078ddafdc3cb80baa6ce610f000ab63bc3f92863` |
| `bea938432411c82d8f6f3e6336674959e498bd9e` | [`417581fe64ac02a9b6f33bbaa77bdf648be97140`](https://github.com/Proph151Music/tessellation/commit/417581fe64ac02a9b6f33bbaa77bdf648be97140) | `ad41fb338a668133beba2cb39acda21ac360d232` |
| `2f07b3c4e67da5e9d8019bab73c3e7b8db357dbd` | [`fdfc50ca9da4b8112e9e1c1bd49da2c649438562`](https://github.com/Proph151Music/tessellation/commit/fdfc50ca9da4b8112e9e1c1bd49da2c649438562) | `95a4fdf99da683e533d30a978d0a4556b50170fb` |
| `18ebb677b5f255d4f6c2f1919aaf69a99b11df1c` | [`cc9e16fbf59c180f57475ad008b0ebe9bcff3ae4`](https://github.com/Proph151Music/tessellation/commit/cc9e16fbf59c180f57475ad008b0ebe9bcff3ae4) | `0d183957538e0654222218bcf9091f393dcdc57c` |

The native tested source is local `2f07b3c4e67da5e9d8019bab73c3e7b8db357dbd`, published with identical tree as `fdfc50ca9da4b8112e9e1c1bd49da2c649438562`. The local JAR SHA256 is `05e0560ba0f7b04cc17f29dea030c1b5dd5745317532c9fb57bd15cd8902de39`; this is not a signed public-release artifact.
