#!/bin/bash
set -e

export DATABASE_URL="sqlite+aiosqlite:///tmp/e2e-test.db"
export E2E_TEST_MODE="1"
export JWT_SECRET="e2e-test-secret"
export LOG_MODE="stdout"
export CORS_ORIGINS="http://localhost:5181"

rm -f /tmp/e2e-test.db

echo "🎭 Running E2E tests..."

npx playwright test "$@"

EXIT_CODE=$?

rm -f /tmp/e2e-test.db

exit $EXIT_CODE
