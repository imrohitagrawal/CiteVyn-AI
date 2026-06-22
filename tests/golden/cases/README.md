# Golden test cases for CiteVyn (slice-10 demo-readiness)
#
# Conventions
# -----------
# * Every file is one case.  ID and title live in the YAML front matter;
#   the body is the full case object.
# * `type`      -- `answer`   / `no_answer` / `unsupported` / `search` / `cache` / `multi_turn`
# * `area`      -- `claude_api` / `claude_code` / `codex` / `gemini_api` / `cross`
# * `assertions` -- the fields the golden runner MUST verify.
#   A missing assertion means "don't care".  Keys with a list mean "at
#   least one matches".
#
# These cases are designed to be stable against the demo seed corpus
# (`db/seed/seed_catalog.py`).  They should NOT be used with a
# production index because the expected `answer` texts are hard-coded
# to the demo retriever's exact-match behaviour.
