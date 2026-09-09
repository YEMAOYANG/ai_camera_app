#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${OPENMAIC_SOURCE_DIR:-${RUNTIME_ROOT}/.runtime/OpenMAIC}"
REPOSITORY="https://github.com/THU-MAIC/OpenMAIC.git"
COMMIT="aa2bfb3c1d406c47100c6744d90e788abdf1f6d5"
LOCK_FILE="${RUNTIME_ROOT}/upstream.lock.json"

verify_patch_manifest() {
  local expected_count expected_latest expected_sha
  local actual_count actual_latest actual_sha patch_file
  [[ -f "${LOCK_FILE}" ]] || {
    echo "OpenMAIC upstream lock is missing." >&2
    return 1
  }
  expected_count="$(sed -n 's/^[[:space:]]*"count"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "${LOCK_FILE}")"
  expected_latest="$(sed -n 's/^[[:space:]]*"latest"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${LOCK_FILE}")"
  expected_sha="$(sed -n 's/^[[:space:]]*"latestSha256"[[:space:]]*:[[:space:]]*"\([a-f0-9]*\)".*/\1/p' "${LOCK_FILE}")"
  actual_count=0
  actual_latest=""
  for patch_file in "${RUNTIME_ROOT}"/patches/*.patch; do
    [[ -e "${patch_file}" ]] || continue
    actual_count=$((actual_count + 1))
    actual_latest="$(basename "${patch_file}")"
  done
  [[ "${expected_count}" =~ ^[0-9]+$ ]] || {
    echo "OpenMAIC patch manifest count is invalid." >&2
    return 1
  }
  [[ "${actual_count}" == "${expected_count}" ]] || {
    echo "OpenMAIC patch manifest count mismatch." >&2
    return 1
  }
  [[ "${actual_latest}" == "${expected_latest}" ]] || {
    echo "OpenMAIC latest patch name mismatch." >&2
    return 1
  }
  [[ "${expected_sha}" =~ ^[a-f0-9]{64}$ ]] || {
    echo "OpenMAIC latest patch checksum is invalid." >&2
    return 1
  }
  actual_sha="$(shasum -a 256 "${RUNTIME_ROOT}/patches/${actual_latest}" | awk '{print $1}')"
  [[ "${actual_sha}" == "${expected_sha}" ]] || {
    echo "OpenMAIC latest patch checksum mismatch." >&2
    return 1
  }
}

verify_patch_manifest

mkdir -p "$(dirname "${SOURCE_DIR}")"
if [[ ! -d "${SOURCE_DIR}/.git" ]]; then
  git clone --filter=blob:none "${REPOSITORY}" "${SOURCE_DIR}"
fi

# A verified checkout may be seeded from a reviewed local cache in development
# or copied into an offline production build context. Avoid making every start
# depend on GitHub when the pinned commit is already present locally.
if ! git -C "${SOURCE_DIR}" cat-file -e "${COMMIT}^{commit}" 2>/dev/null; then
  git -C "${SOURCE_DIR}" fetch --depth 1 origin "${COMMIT}"
fi
git -C "${SOURCE_DIR}" checkout --detach --quiet "${COMMIT}"

ACTUAL="$(git -C "${SOURCE_DIR}" rev-parse HEAD)"
if [[ "${ACTUAL}" != "${COMMIT}" ]]; then
  echo "OpenMAIC commit verification failed: ${ACTUAL}" >&2
  exit 1
fi
if ! grep -q "MIT License" "${SOURCE_DIR}/LICENSE"; then
  echo "OpenMAIC LICENSE verification failed" >&2
  exit 1
fi

# Patches later in the series can intentionally edit the same hunk as an
# earlier patch. Checking them one-by-one in forward order therefore cannot
# reliably recognize an already-complete patch set. Peel off only patches that
# reverse cleanly, newest first, then require a pristine reviewed checkout
# before replaying the complete series. Positional parameters keep this
# Bash-3.2-safe without relying on optional/empty arrays.
set --
for PATCH_FILE in "${RUNTIME_ROOT}"/patches/*.patch; do
  [[ -e "${PATCH_FILE}" ]] || continue
  set -- "${PATCH_FILE}" "$@"
done
for PATCH_FILE in "$@"; do
  if git -C "${SOURCE_DIR}" apply --reverse --check "${PATCH_FILE}" >/dev/null 2>&1; then
    git -C "${SOURCE_DIR}" apply --reverse "${PATCH_FILE}"
  fi
done

if ! git -C "${SOURCE_DIR}" diff --quiet || \
  ! git -C "${SOURCE_DIR}" diff --cached --quiet || \
  [[ -n "$(git -C "${SOURCE_DIR}" status --porcelain --untracked-files=normal)" ]]; then
  echo "OpenMAIC checkout contains changes outside the reviewed patch set; refusing to overwrite them." >&2
  exit 1
fi

for PATCH_FILE in "${RUNTIME_ROOT}"/patches/*.patch; do
  [[ -e "${PATCH_FILE}" ]] || continue
  git -C "${SOURCE_DIR}" apply --check "${PATCH_FILE}"
  git -C "${SOURCE_DIR}" apply "${PATCH_FILE}"
done

echo "OpenMAIC ${COMMIT} with reviewed Mira runtime patches is ready at ${SOURCE_DIR}"
