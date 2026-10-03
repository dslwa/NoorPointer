package scan

import (
	"regexp"
	"slices"
	"strings"
	"testing"
	"time"
)

const (
	b64Pattern   = `[A-Za-z0-9+/_-]{24,}={0,2}`
	emailPattern = `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`
	cardPattern  = `\d{13,19}|\d{4}(?:[ .-]\d{4}){2}[ .-]\d{1,4}(?:[ .-]\d{1,3})?|\d{4}[ .-]\d{6}[ .-]\d{4,5}`
	phonePattern = `(?:(?:\+|00)48[ -]?)?(?:\d{3}[ .-]?\d{3}[ .-]?\d{3}|\d{2}[ .-]\d{3}[ .-]\d{2}[ .-]\d{2})`
)

// refRule is r as a plain regex rule, the spec its find must reproduce.
func refRule(r rule) rule {
	r.find = nil
	switch r.kind {
	case "encoded_secret":
		r.re = regexp.MustCompile(b64Pattern)
	case "email":
		r.re = regexp.MustCompile(emailPattern)
	case "iban":
		r.re = regexp.MustCompile(`[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]{4}){2,7}(?: ?[A-Za-z0-9]{1,3})?`)
		r.backoff = true
	case "card":
		r.re = regexp.MustCompile(cardPattern)
	case "phone":
		r.re = regexp.MustCompile(phonePattern)
	case "pesel":
		r.re = regexp.MustCompile(`\d{11}`)
	}
	return r
}

func spans(r rule, s string) [][2]int {
	var out [][2]int
	for pos := 0; pos < len(s); {
		start, reEnd := r.locate(s, pos)
		if start < 0 {
			break
		}
		end := r.accept(s, start, reEnd)
		if end < 0 {
			pos = r.next(s, start, reEnd)
			continue
		}
		out = append(out, [2]int{start, end})
		pos = end
	}
	return out
}

func FuzzFindMatchesRegex(f *testing.F) {
	for _, s := range []string{
		"PESEL 95081212345", "95081212347 12345678901", "4111 1111 1111 1111 2024", "1 4111 1111 1111 1111",
		"+48 600 123 456", "+420 601 234 567", "tel. 22 123 45 67", "PL61 1090 1014 0000 0712 1981 2874 from bank",
		"600123456PL61109010140000071219812874", "GB82WEST12345698765432XYZ", "AB12 AB12 AB12", "",
		"a@b@c.com", "x.y@a.b.cd.e1", "@@a.bc", "jan@example.com.", "Z2hwXzEyMzQ1Njc4OTAxMjM0NTY3ODkw==A",
	} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, in string) {
		s, _ := normalize(in)
		for _, r := range rules {
			if r.find == nil {
				continue
			}
			if want, got := spans(refRule(r), s), spans(r, s); !slices.Equal(want, got) {
				t.Fatalf("%s on %q: regex %v, find %v", r.kind, s, want, got)
			}
		}
	})
}

func TestFindSpeedup(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}
	for _, in := range []string{
		strings.Repeat("User 42 asked about order 2024-10-03 at 10:00, total 129.99 PLN. tel 600 123 456, "+
			"PESEL 95081212347, PL61 1090 1014 0000 0712 1981 2874, 4111 1111 1111 1111 ", 6000),
		strings.Repeat("1234 5678 ", 100000),
		strings.Repeat("AB12 ", 200000),
		strings.Repeat("PL12 ", 200000),
		strings.Repeat("1 ", 500000),
	} {
		var ref, fast time.Duration
		for _, r := range rules {
			if r.find == nil {
				continue
			}
			st := time.Now()
			want := spans(refRule(r), in)
			ref += time.Since(st)
			st = time.Now()
			got := spans(r, in)
			fast += time.Since(st)
			if !slices.Equal(want, got) {
				t.Errorf("%s on %.20q...: spans differ", r.kind, in)
			}
		}
		t.Logf("%-22.20q regex %-6v find %v", in, ref.Round(time.Millisecond), fast.Round(time.Millisecond))
	}
}
