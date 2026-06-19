# Code Review Standard

Block shipping for:

- broken behavior
- missing tests for changed behavior
- auth/authz bypass
- data leakage
- unsafe logging of secrets or PII
- unbounded queries
- race conditions
- migration without rollback
- breaking API changes
- flaky tests
- missing observability for critical paths

Do not block shipping for:
- personal style preferences
- cosmetic refactoring
- renaming without clear value
- theoretical issues without a concrete failure mode

Every review finding must include:
1. severity
2. file/function
3. why it matters
4. suggested fix
5. whether it blocks release