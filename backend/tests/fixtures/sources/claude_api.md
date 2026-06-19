# Claude API Reference

## Rate limits

The Claude API enforces a default rate limit of 50 requests per minute.
The CLAUDE_API_RATE_LIMIT environment variable can override this for
self-serve customers.

## Authentication

Pass your Claude API key in the x-api-key header on every request. The
Claude SDK reads the key from the ANTHROPIC_API_KEY environment
variable if the header is absent.

## Models

The --model flag selects the Claude model used for a request. Supported
values include claude-opus-4-7 and claude-sonnet-4-6.
