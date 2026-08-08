# Plan: close two silent detection gaps in `analyze_pkgbuild_safety`

**Status:** proposed
**Date:** 2026-08-08
**Branch context:** `harden/security`
**Component:** `src/arch_ops_server/aur.py` → `analyze_pkgbuild_safety` (line 923), reached via
`audit_package_security(action='pkgbuild_analysis')`

## Context

Two rules in the PKGBUILD analyser look like they cover a risk but never report it. Both
fail silently: the code reads as though the case is handled, the scan returns clean, and a
reviewer sees an absence of findings rather than an absence of checking. That is the worst
failure mode for an auditing tool, because a clean result is what a reviewer acts on.

Both were found while integrating this server into the `update-arch-system` skill, by
running the server and a second independent scanner over the same real package
(`aur/brother-dcp-l2530dw`) and comparing results.

## Gap 1: weak hash algorithms are never flagged

### The defect

`aur.py:1165-1173`:

```python
for i, line in enumerate(lines, 1):
    if re.match(r"^\s*(md5|sha1|sha224|sha256|sha384|sha512|b2)sums", line):
        if "SKIP" in line:
            warnings.append({...})
```

The regex captures the algorithm name in group 1 and then discards it. The only branch
reports `SKIP`. A recipe pinning a real MD5 digest passes with no integrity finding at all:

```bash
md5sums=('a8f84171ee1796fc4899579d92df0e24')   # currently reports nothing
```

### Why it matters

MD5 and SHA-1 are collision-broken. Anyone able to influence which artifact the source URL
serves — a compromised host or mirror, or a maintainer swapping the file — can supply
different bytes carrying the same digest. The checksum then certifies nothing about
content, only that a transfer completed.

It still catches accidental corruption and naive substitution, so this is a `WARNING`
alongside the other provenance findings, not a `red_flag`.

This gap could not be caught by cross-checking against another tool, because the scanner
bundled with the `update-arch-system` skill had the identical blind spot — it matched the
algorithm names only when followed by `SKIP`. That side is fixed (`my-skills` commit
`96854bc`), which is what leaves this side outstanding.

### The fix

Capture the algorithm and branch on it, in the existing loop:

```python
# Collision-broken algorithms: a matching digest no longer implies matching content.
WEAK_HASH_ALGORITHMS = {"md5", "sha1"}

for i, line in enumerate(lines, 1):
    match = re.match(r"^\s*(md5|sha1|sha224|sha256|sha384|sha512|b2)sums", line)
    if not match:
        continue
    if "SKIP" in line:
        warnings.append({
            "line": i,
            "content": line.strip()[:100],
            "issue": "Checksum set to SKIP: this source is not verified at build time",
            "severity": "WARNING",
        })
    elif match.group(1) in WEAK_HASH_ALGORITHMS:
        warnings.append({
            "line": i,
            "content": line.strip()[:100],
            "issue": (
                f"{match.group(1)} is collision-broken and cannot establish source "
                "integrity; prefer sha256 or stronger"
            ),
            "severity": "WARNING",
        })
```

`elif` rather than a second `if` is deliberate: `md5sums=('SKIP')` verifies nothing at all,
so the algorithm is moot and only the SKIP finding should appear. This matches the
behaviour the skill-side scanner was given, keeping the two tools comparable.

Because the algorithm name sits on the declaration line, this also handles multi-line
arrays (`md5sums=(` with digests on following lines), which the line-based `SKIP` check
cannot. Do not "fix" that asymmetry here; the SKIP multi-line case is a separate defect.

### Tests

In `tests/test_security.py`, following the existing async `audit_package_security` style:

- `md5sums` with a real digest → a warning whose `issue` names md5
- `sha1sums` with a real digest → likewise
- `sha256sums`, `sha512sums`, `b2sums` → no weak-algorithm warning
- `md5sums=('SKIP')` → the SKIP warning only, asserting the weak-algorithm text is absent
- multi-line `md5sums=(` declaration → flagged

## Gap 2: `.AppImage` detection is dead code

### The defect

`aur.py:1147-1155`:

```python
binary_extensions = ['.bin', '.exe', '.AppImage', '.deb', '.rpm', '.jar', '.apk']
for ext in binary_extensions:
    if ext in pkgbuild_content.lower():
```

The haystack is lowercased but the needle is not. `'.AppImage' in '....appimage'` is always
`False`, so `.AppImage` can never match. Verified directly:

```
.AppImage    matches: False      # against source=("https://example.com/app-1.0.AppImage")
```

The lowercase entries work — `.rpm` fires correctly on `aur/brother-dcp-l2530dw` — so this
affects exactly one extension, and it is the one that matters most: a prebuilt AppImage is
the archetypal opaque binary in an AUR recipe.

### The fix

Lowercase the needle at comparison time, so the list stays readable in its conventional
casing:

```python
content_lower = pkgbuild_content.lower()
for ext in binary_extensions:
    if ext.lower() in content_lower:
```

Guard the class of bug rather than the instance: add an assertion or test that every entry
in `binary_extensions` is detectable, so a future entry with capitals cannot reintroduce it.

### Tests

- A source ending in `.AppImage` produces a binary-file warning
- Each entry in `binary_extensions` is detected when present in a source URL, parameterised
  over the list itself so new entries are covered automatically

## Verification

1. `uv run pytest tests/test_security.py` — new cases pass, existing pass unchanged.
2. `uv run pytest` — full suite green; `risk_score` shifts by +5 per new warning, so check
   no existing test asserts an exact score that these findings perturb.
3. Real-world regression, the package that exposed both gaps:

   ```bash
   git clone --depth 1 https://aur.archlinux.org/brother-dcp-l2530dw.git
   ```

   `pkgbuild_analysis` on its PKGBUILD must now report the md5 finding alongside the
   existing `.rpm` binary warning and the `download.brother.com` vs `support.brother.com`
   host-mismatch info.
4. Cross-check against the independent scanner in the `update-arch-system` skill
   (`scripts/scan-aur-recipe.sh`). After both fixes the two tools should agree on md5 and on
   AppImage, while still differing where they legitimately differ — the skill's scanner
   reads `.SRCINFO` and `.install`, which this server never sees.

## Out of scope

- `.SRCINFO` analysis. `pkgbuild_analysis` takes PKGBUILD text only, and widening its input
  is a separate design decision.
- The multi-line `SKIP` limitation described above.
- Any change to `recommendation` or `risk_score` weighting. Both new findings are ordinary
  `WARNING`s and should score like the rest.
- The `limitations` string already states that a clean result is not an assurance of safety;
  it needs no revision for these fixes.
