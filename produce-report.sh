#!/usr/bin/env bash

[[ "${TRACE}" ]] && set -x
set -eou pipefail
shopt -s nullglob

main() {
  echo "" >.credentials
  echo "${GITHUB_TOKEN}" >>.credentials

  poetry run ./get_branch_protections.py "${GITHUB_ORG}"

  poetry run ./report_branch_status.py "${GITHUB_ORG}.db.json" --header
}

main "$@"
