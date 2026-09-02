#!/usr/bin/env bash
# Runs every tests/test_*.sh and aggregates the result.
cd "$(dirname "$0")" || exit 1

total_run=0
total_failed=0
total_skipped=0

for t in test_*.sh; do
  [ -e "$t" ] || continue
  echo "== $t"
  # Each suite prints "SUITE_RESULT <run> <failed> <skipped>" as its final line.
  out="$(bash "$t")"
  echo "$out" | grep -v '^SUITE_RESULT'
  line="$(echo "$out" | grep '^SUITE_RESULT' | tail -1)"
  total_run=$((total_run + $(echo "$line" | awk '{print $2}')))
  total_failed=$((total_failed + $(echo "$line" | awk '{print $3}')))
  total_skipped=$((total_skipped + $(echo "$line" | awk '{print $4+0}')))
done

echo
echo "TOTAL: $total_run assertions, $total_failed failed, $total_skipped skipped"
if [ "$total_skipped" -gt 0 ]; then
  echo "NOTE: skipped assertions are platform-limited here and ARE enforced in CI (ubuntu-latest)."
fi
[ "$total_failed" -eq 0 ]
