# WOLS conformance vectors

`test_vectors.py` runs every case in `vectors/` through the public `wols` API.
`MUST` cases must pass. A failing `SHOULD` case is reported as `xfail`.

## Source

The files in `vectors/` are copied unmodified from
[wemush/open-standard](https://github.com/wemush/open-standard/tree/main/conformance):

| Field | Value |
| ----- | ----- |
| Tag | `1.3.0-rc.1` |
| Commit | `a96405ef951d6010b47ea8ae962b006e5b62d00c` |
| Path | `conformance/vectors/{embedded,primordia,generation,encrypted}.json` |

SHA-256 checksums:

```text
a86d8cecf6b43af41fd19d9686d26697d99f162939167bf0fd187fc8610270b1  embedded.json
c54f9f7943733bab042a16398a4fe2a45daad0590777507243f681317784c8b1  encrypted.json
9e4ffca202dc674fefe8a25c5aed4a3377295e3cec71ddc788dada7912d7d2de  generation.json
0f103727fa3e8fd1f8ef037df6f60a1a8e83f48f5085a919e3b1d7b2c8978ff1  primordia.json
```

## How operations map to the API

| Operation | Call |
| --------- | ---- |
| `validate` | `validate_specimen(input)`. `errorField` and `warningField` are matched against `ValidationError.path`. |
| `create` | `create_specimen(**input)`. The warning is a `WolsWarning`. |
| `derive` | `wols.crypto.derive_key(passphrase, salt, iterations)` |
| `decrypt` | `wols.crypto.decrypt_specimen_bytes(url, secret)` (exact plaintext) and `decrypt_specimen(url, secret)`. A failure's `reason` must equal the `WolsEncryptionError.code`, upper-cased with `_` (for example, `id-mismatch` becomes `ID_MISMATCH`). |

## Refreshing

```bash
TAG=1.3.0  # or another tag or commit of wemush/open-standard
git clone https://github.com/wemush/open-standard.git /tmp/open-standard
for f in embedded primordia generation encrypted; do
  git -C /tmp/open-standard show "$TAG:conformance/vectors/$f.json" \
    > "tests/conformance/vectors/$f.json"
done
git -C /tmp/open-standard rev-parse "$TAG^{commit}"   # record in the table above
shasum -a 256 tests/conformance/vectors/*.json         # record above
uv run pytest tests/conformance -v
```

Then update the tag, commit, and checksums above. If upstream adds a vector
file, add its name to `VECTOR_FILES` in `test_vectors.py`.
