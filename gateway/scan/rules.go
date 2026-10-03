package scan

import (
	"regexp"
	"slices"
	"strings"
)

type rule struct {
	control string
	kind    string
	re      *regexp.Regexp
	// find replaces re where a byte scan locates candidates faster.
	find  func(s string, pos int) (start, end int)
	pre   func(string) bool
	valid func(string) bool
	// digitEdges requires a non-digit (or text edge) around the match,
	// so "PESEL95081212345" is caught but 12 digits are not a PESEL.
	digitEdges bool
	// backoff retries shorter prefixes of a failed match, so a card
	// followed by a year is still found.
	backoff bool
	// context accepts a match that fails valid when one of these lowercase
	// words stands just before it, so "PESEL 95081212345" is caught even
	// with a made-up number.
	context []string
}

// Plain secret patterns start with a literal, which lets Go skip straight
// to candidates instead of running the regex over every byte. Keep one
// literal per rule: an alternation like (?:sk|rk)_live_ is ~1000x slower.
// No \b: it depends on the next character, which may itself be masked
// later, so two glued keys would leak the first one.
var secretRules = []rule{
	{control: "secrets", kind: "aws_key", re: regexp.MustCompile(`(?:AKIA|ASIA)[0-9A-Z]{16}`)},
	{control: "secrets", kind: "github_token", re: regexp.MustCompile(`gh[pousr]_[A-Za-z0-9]{36,}`)},
	{control: "secrets", kind: "github_token", re: regexp.MustCompile(`github_pat_[A-Za-z0-9_]{22,}`)},
	{control: "secrets", kind: "anthropic_key", re: regexp.MustCompile(`sk-ant-[A-Za-z0-9_-]{20,}`)},
	{control: "secrets", kind: "openai_key", re: regexp.MustCompile(`sk-(?:proj-)?[A-Za-z0-9_-]{20,}`),
		valid: func(m string) bool { return !strings.HasPrefix(m, "sk-ant-") }},
	{control: "secrets", kind: "google_api_key", re: regexp.MustCompile(`AIza[0-9A-Za-z_-]{35}`)},
	{control: "secrets", kind: "slack_token", re: regexp.MustCompile(`xox[abporsc]-[A-Za-z0-9-]{10,}`)},
	{control: "secrets", kind: "stripe_key", re: regexp.MustCompile(`sk_live_[A-Za-z0-9]{20,}`)},
	{control: "secrets", kind: "stripe_key", re: regexp.MustCompile(`rk_live_[A-Za-z0-9]{20,}`)},
	{control: "secrets", kind: "jwt", re: regexp.MustCompile(`eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`)},
	{control: "secrets", kind: "private_key", re: regexp.MustCompile(`-----BEGIN [A-Z ]*PRIVATE KEY-----`)},
}

// Order matters: secrets first, then wider PII patterns, so a card or IBAN
// is not half-masked as a phone number or PESEL.
var rules = append(slices.Clone(secretRules),
	rule{control: "secrets", kind: "encoded_secret", find: findB64,
		pre: hasLongToken, valid: hidesSecret},
	rule{control: "pii_regex", kind: "iban", find: findIBAN,
		pre: hasDigits, valid: ibanOK, digitEdges: true},
	// ponytail: only printed card layouts (contiguous, 4-4-4-4[-3], 4-6-5/4-6-4).
	// A free-form (?:\d[ .-]?){12,18}\d also takes "4 1 1 1 ..." but is retried
	// from every digit of "1 1 1 ...", ~2 s per MB.
	rule{control: "pii_regex", kind: "card", find: findCard,
		pre: hasDigits, valid: cardOK, digitEdges: true, backoff: true},
	rule{control: "pii_regex", kind: "email", find: findEmail,
		pre: hasAt},
	rule{control: "pii_regex", kind: "email", re: regexp.MustCompile(`(?i)[A-Za-z0-9._%+-]+\s*[\[(]at[\])]\s*[A-Za-z0-9-]+(?:\s*[\[(]dot[\])]\s*[A-Za-z0-9-]+)+`),
		pre: hasObfuscatedAt},
	// phone runs before pesel so "+48600123456" is not taken for a PESEL;
	// a bare 11-digit run fails the phone's digit edges and falls through.
	// ponytail: Polish numbers only, foreign ones go to Presidio over gRPC.
	rule{control: "pii_regex", kind: "phone", find: findPhone,
		pre: hasDigits, valid: phoneOK, digitEdges: true, context: []string{"tel", "phone", "komórk"}},
	rule{control: "pii_regex", kind: "pesel", find: findPESEL,
		pre: hasDigits, valid: peselOK, digitEdges: true, context: []string{"pesel"}},
)
