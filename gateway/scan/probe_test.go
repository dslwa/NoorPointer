package scan

import "testing"

func TestProbe(t *testing.T) {
	for _, s := range []string{
		"Call me at +48 123 456 789 tomorrow.",
		"tel 600 123 456",
	} {
		var f []Finding
		t.Logf("%q -> %q %v", s, Text(redactAllPolicy(), s, &f), f)
	}
}
