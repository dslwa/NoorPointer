package scan

import (
	"testing"

	"github.com/dslwa/NoorPointer/gateway/config"
)

func redactAllPolicy() *config.Policy {
	return &config.Policy{
		Defaults: config.Defaults{Mode: "enforce"},
		Controls: config.Controls{
			Secrets: &config.Control{Enabled: true, Action: "redact"},
			PIIRegex: &config.PatternControl{
				Control: config.Control{Enabled: true, Action: "redact"},
				Types:   []string{"email", "pesel", "iban", "card", "phone"},
			},
		},
	}
}

func TestScanTextRedacts(t *testing.T) {
	tests := []struct {
		name, in, want string
	}{
		{"aws key", "key AKIAIOSFODNN7EXAMPLE here", "key [REDACTED:aws_key] here"},
		{"github token", "token ghp_123456789012345678901234567890123456", "token [REDACTED:github_token]"},
		{"openai key", "sk-proj-abcdefghijklmnopqrstuvwx", "[REDACTED:openai_key]"},
		{"jwt", "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl", "Bearer [REDACTED:jwt]"},
		{"private key", "-----BEGIN RSA PRIVATE KEY-----", "[REDACTED:private_key]"},
		{"iban pl", "konto PL61 1090 1014 0000 0712 1981 2874.", "konto [REDACTED:iban]."},
		{"iban compact", "DE89370400440532013000", "[REDACTED:iban]"},
		{"card spaced", "card 4111 1111 1111 1111 ok", "card [REDACTED:card] ok"},
		{"card dashed", "5500-0000-0000-0004", "[REDACTED:card]"},
		{"email", "mail jan.kowalski@example.com now", "mail [REDACTED:email] now"},
		{"email with digits", "jan.123456789@firma.pl", "[REDACTED:email]"},
		{"pesel", "PESEL 95081212345.", "PESEL [REDACTED:pesel]."},
		{"phone", "tel 600 123 456", "tel [REDACTED:phone]"},
		{"phone with prefix", "+48 600-123-456", "[REDACTED:phone]"},
		{"landline", "tel. 22 123 45 67", "tel. [REDACTED:phone]"},
		{"phone with dots", "600.123.456", "[REDACTED:phone]"},
		{"phone with 0048", "0048 600 123 456", "[REDACTED:phone]"},
		{"foreign prefix not split", "+420 601 234 567", "+420 [REDACTED:phone]"},
		{"9-digit order number stays", "order 123456789", "order 123456789"},
		{"9 digits after tel", "tel: 123456789", "tel: [REDACTED:phone]"},
		{"iban-like chunk of base64 stays", "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4" + "PL61109010140000071219812874" + "2mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg", "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4PL611090101400000712198128742mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg"},
		{"clean text", "What is the capital of Poland?", "What is the capital of Poland?"},
		{"code", "def add(a, b): return a + b", "def add(a, b): return a + b"},
		{"luhn invalid digits stay", "order 4111 1111 1111 1112", "order 4111 1111 1111 1112"},

		{"pesel with checksum", "id 44051401359", "id [REDACTED:pesel]"},
		{"11 digits without checksum stay", "id 12345678901", "id 12345678901"},
		{"made-up pesel after the word", "mój pesel: 12345678901", "mój pesel: [REDACTED:pesel]"},
		{"redacted pesel is not context", "95081212347 12345678901", "[REDACTED:pesel] 12345678901"},
		{"pesel glued", "PESEL95081212345", "PESEL[REDACTED:pesel]"},
		{"phone glued", "tel600123456", "tel[REDACTED:phone]"},
		{"card glued", "card4111111111111111", "card[REDACTED:card]"},
		{"iban glued", "IBANPL61109010140000071219812874", "IBAN[REDACTED:iban]"},
		{"12 digits are not a pesel", "id 123456789012", "id 123456789012"},
		{"pesel next to another number", "95081212347 1", "[REDACTED:pesel] 1"},
		{"compact phone with prefix", "+48600123456", "[REDACTED:phone]"},
		{"phone prefix glued to a digit", "1+48 600 123 456", "1+48 [REDACTED:phone]"},

		{"iban after digits", "600123456PL61109010140000071219812874", "[REDACTED:phone][REDACTED:iban]"},
		{"long s is not an iban letter", "AE0000p0ſh00G000000ſh", "AE0000p0ſh00G000000ſh"},
		{"iban lowercase", "pl61 1090 1014 0000 0712 1981 2874", "[REDACTED:iban]"},
		{"iban then word", "PL61 1090 1014 0000 0712 1981 2874 from bank", "[REDACTED:iban] from bank"},
		{"iban bad checksum stays", "AB12 THIS TEXT HERE", "AB12 THIS TEXT HERE"},

		{"card with dots", "4111.1111.1111.1111", "[REDACTED:card]"},
		{"card then year", "4111 1111 1111 1111 2024", "[REDACTED:card] 2024"},
		{"digit before card", "1 4111 1111 1111 1111", "1 [REDACTED:card]"},

		{"glued aws keys", "AKIAIOSFODNN7EXAMPLEAKIAIOSFODNN7EXAMPLE", "[REDACTED:aws_key][REDACTED:aws_key]"},
		{"github token then underscore", "ghp_123456789012345678901234567890123456_x", "[REDACTED:github_token]_x"},
		{"github fine-grained", "github_pat_11ABCDEFG0123456789_abcdefghijklmnop", "[REDACTED:github_token]"},
		{"anthropic key", "sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "[REDACTED:anthropic_key]"},
		{"google api key", "AIzaSyA1234567890abcdefghijklmnopqrstuv", "[REDACTED:google_api_key]"},
		{"slack token", "xox" + "b-123456789012-abcdefghijklmnop", "[REDACTED:slack_token]"},
		{"stripe key", "sk_" + "live_51H8abcdefghijklmnopqrstuvwxyz", "[REDACTED:stripe_key]"},
		{"base64 secret", "Z2hwXzEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Ng==", "[REDACTED:encoded_secret]"},
		{"hex secret", "6768705f313233343536373839303132333435363738393031323334353637383930313233343536", "[REDACTED:encoded_secret]"},
		{"plain long token stays", "aGVsbG8gd29ybGQsIHRoaXMgaXMgZmluZQ==", "aGVsbG8gd29ybGQsIHRoaXMgaXMgZmluZQ=="},

		{"full-width digits", "９５０８１２１２３４７", "[REDACTED:pesel]"},
		{"arabic-indic digits", "٩٥٠٨١٢١٢٣٤٧", "[REDACTED:pesel]"},
		{"zero-width inside pesel", "950812\u200b12347", "[REDACTED:pesel]"},
		{"full-width secret", "ｇｈｐ＿123456789012345678901234567890123456", "[REDACTED:github_token]"},
		{"email at dot", "jan (at) example (dot) com", "[REDACTED:email]"},
		{"email brackets", "jan[at]firma[dot]pl", "[REDACTED:email]"},
		{"clean emoji kept", "family 👨\u200d👩\u200d👧", "family 👨\u200d👩\u200d👧"},
		{"emoji kept next to redaction", "👨\u200d👩\u200d👧 jan@example.com", "👨\u200d👩\u200d👧 [REDACTED:email]"},
		{"full-width punctuation kept", "你好，jan@example.com？", "你好，[REDACTED:email]？"},
		{"zwnj kept", "می\u200cخواهم 95081212347", "می\u200cخواهم [REDACTED:pesel]"},
		{"amex", "3782 822463 10005", "[REDACTED:card]"},
		{"version string stays", "version 1.2.3 build 2024-10-03 at 10:00", "version 1.2.3 build 2024-10-03 at 10:00"},
	}
	p := redactAllPolicy()
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var found []Finding
			if got := Text(p, tt.in, &found); got != tt.want {
				t.Errorf("got %q, want %q", got, tt.want)
			}
			if (len(found) > 0) != (tt.in != tt.want) {
				t.Errorf("findings %v do not match redaction", found)
			}
		})
	}
}

func TestBlockedKeyCountedOnce(t *testing.T) {
	p := redactAllPolicy()
	p.Controls.Secrets.Action = "block"
	var found []Finding
	Text(p, "sk-ant-api03-abcdefghijklmnopqrstuvwxyz", &found)
	if len(found) != 1 || found[0].Kind != "anthropic_key" {
		t.Errorf("got %v, want one anthropic_key", found)
	}
}

func TestActionFor(t *testing.T) {
	byKind := func(kind string) rule {
		for _, r := range rules {
			if r.kind == kind {
				return r
			}
		}
		t.Fatalf("no rule %q", kind)
		return rule{}
	}
	pesel, secret := byKind("pesel"), byKind("aws_key")

	tests := []struct {
		name   string
		mutate func(*config.Policy)
		r      rule
		want   string
	}{
		{"pii enabled", func(*config.Policy) {}, pesel, "redact"},
		{"type not listed", func(p *config.Policy) { p.Controls.PIIRegex.Types = []string{"email"} }, pesel, ""},
		{"pii disabled", func(p *config.Policy) { p.Controls.PIIRegex.Enabled = false }, pesel, ""},
		{"pii absent", func(p *config.Policy) { p.Controls.PIIRegex = nil }, pesel, ""},
		{"secrets absent", func(p *config.Policy) { p.Controls.Secrets = nil }, secret, ""},
		{"secrets block", func(p *config.Policy) { p.Controls.Secrets.Action = "block" }, secret, "block"},
		{"global monitor", func(p *config.Policy) { p.Defaults.Mode = "monitor" }, secret, "monitor"},
		{"unknown control", func(*config.Policy) {}, rule{control: "other"}, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			p := redactAllPolicy()
			tt.mutate(p)
			if got := actionFor(p, tt.r); got != tt.want {
				t.Errorf("got %q, want %q", got, tt.want)
			}
		})
	}
}

func TestLuhn(t *testing.T) {
	for in, want := range map[string]bool{
		"4111111111111111":    true,
		"4111 1111 1111 1111": true,
		"4111111111111112":    false,
		"79927398713":         true,
	} {
		if got := luhn(in); got != want {
			t.Errorf("luhn(%q) = %v, want %v", in, got, want)
		}
	}
}

// Explore with -fuzzminimizetime 0: minimizing stalls the workers, and
// default runs missed failures that a minute without it found.
func FuzzText(f *testing.F) {
	for _, seed := range []string{
		"PESEL95081212345", "pl61 1090 1014 0000 0712 1981 2874 from bank", "4111 1111 1111 1111 2024",
		"９５０８１２１２３４５", "jan (at) example (dot) com", "Z2hwXzEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Ng==",
		"95081212347 12345678901", "P", "PL", "1 4", "​", "",
	} {
		f.Add(seed)
	}
	p := redactAllPolicy()
	f.Fuzz(func(t *testing.T, in string) {
		var found []Finding
		out := Text(p, in, &found)
		var again []Finding
		if Text(p, out, &again); len(again) > 0 && len(found) > 0 {
			t.Errorf("redacted output %q still has findings %v", out, again)
		}
	})
}
