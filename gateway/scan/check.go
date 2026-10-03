package scan

import (
	"encoding/base64"
	"encoding/hex"
	"slices"
	"strings"
)

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

func isLetter(c byte) bool { return c|0x20 >= 'a' && c|0x20 <= 'z' }

// Byte classes for the hand-written finders: one table load per byte
// instead of a chain of range checks.
const (
	clsB64 = 1 << iota
	clsLocal
	clsDomain
	clsHex
	// clsSep: bytes no rule reads as part of a match, so a mask next to
	// one cannot complete a neighbour's match.
	clsSep
)

var class = func() (t [256]uint8) {
	for c := range 256 {
		b := byte(c)
		alnum := isDigit(b) || isLetter(b)
		if alnum || strings.IndexByte("+/_-", b) >= 0 {
			t[c] |= clsB64
		}
		if alnum || strings.IndexByte("._%+-", b) >= 0 {
			t[c] |= clsLocal
		}
		if alnum || b == '.' || b == '-' {
			t[c] |= clsDomain
		}
		if isDigit(b) || b|0x20 >= 'a' && b|0x20 <= 'f' {
			t[c] |= clsHex
		}
		if strings.IndexByte(" \t\r\n,;:!?\"'()[]{}<>", b) >= 0 {
			t[c] |= clsSep
		}
	}
	return t
}()

func hasAt(s string) bool { return strings.IndexByte(s, '@') >= 0 }

func hasObfuscatedAt(s string) bool {
	for _, at := range []string{"(at)", "[at]", "(AT)", "[AT]", "(At)", "[At]"} {
		if strings.Contains(s, at) {
			return true
		}
	}
	return false
}

// 9 digits is the shortest PII number (a phone).
func hasDigits(s string) bool {
	n := 0
	for i := 0; i < len(s); i++ {
		if isDigit(s[i]) {
			if n++; n >= 9 {
				return true
			}
		}
	}
	return false
}

// 24 base64 characters is the shortest encoded secret worth decoding.
func hasLongToken(s string) bool {
	run := 0
	for i := 0; i < len(s); i++ {
		if class[s[i]]&clsB64 != 0 {
			if run++; run >= 24 {
				return true
			}
		} else {
			run = 0
		}
	}
	return false
}

// The alphabet picks the one base64 variant that can decode m (a token
// with neither +/ nor -_ decodes the same in both), so a 1 MB image is
// decoded once, not four times; hex only when every byte is a hex digit.
func hidesSecret(m string) bool {
	leaks := func(b []byte, err error) bool {
		return err == nil && slices.ContainsFunc(secretRules, func(r rule) bool { return r.re.Match(b) })
	}
	enc := base64.StdEncoding
	if strings.IndexByte(m, '-') >= 0 || strings.IndexByte(m, '_') >= 0 {
		enc = base64.URLEncoding
	}
	if !strings.HasSuffix(m, "=") {
		enc = enc.WithPadding(base64.NoPadding)
	}
	if leaks(enc.DecodeString(m)) {
		return true
	}
	for i := 0; i < len(m); i++ {
		if class[m[i]]&clsHex == 0 {
			return false
		}
	}
	return leaks(hex.DecodeString(m))
}

func cardOK(m string) bool {
	digits := 0
	for i := 0; i < len(m); i++ {
		if isDigit(m[i]) {
			digits++
		}
	}
	return digits >= 13 && digits <= 19 && luhn(m)
}

// The exact length per country (ISO 13616) stops backoff from accepting a candidate that runs into
// the next word and passes mod-97 by chance (1 in 97).
var ibanLengths = func() map[string]int {
	m := map[string]int{}
	for _, f := range strings.Fields(`AD24 AE23 AL28 AT20 AZ28 BA20 BE16 BG22 BH22 BR29 CH21 CR22 CY28 CZ24
		DE22 DK18 DO28 EE20 EG29 ES24 FI18 FO18 FR27 GB22 GE22 GI23 GL18 GR27 GT28 HR21 HU28 IE22 IL23
		IQ23 IS26 IT27 JO30 KW30 KZ20 LB28 LC32 LI21 LT20 LU20 LV21 MC27 MD24 ME22 MK19 MR27 MT31 MU30
		NL18 NO15 PK24 PL28 PS29 PT25 QA29 RO24 RS22 SA24 SC31 SE24 SI19 SK24 SM27 ST25 SV28 TL23 TN24
		TR26 UA29 VA22 VG24 XK20`) {
		m[f[:2]] = int(f[2]-'0')*10 + int(f[3]-'0')
	}
	return m
}()

// ibanLength upper-cases into a stack array: the map lookup with
// string(cc[:]) does not allocate, strings.ToUpper would.
func ibanLength(a, b byte) int {
	cc := [2]byte{a &^ 0x20, b &^ 0x20}
	return ibanLengths[string(cc[:])]
}

// The length check runs before any allocation: backoff calls this for
// every prefix of a candidate.
func ibanOK(m string) bool {
	if len(m) < 15 || m[len(m)-1] == ' ' || len(m)-strings.Count(m, " ") != ibanLength(m[0], m[1]) {
		return false
	}
	rem := 0
	for _, part := range [2]string{m[4:], m[:4]} {
		for i := 0; i < len(part); i++ {
			switch c := part[i]; {
			case isDigit(c):
				rem = (rem*10 + int(c-'0')) % 97
			case isLetter(c):
				rem = (rem*100 + int(c&^0x20-'A'+10)) % 97
			}
		}
	}
	return rem == 1
}

// Without a country code, 3-3-3 numbers must start with a mobile prefix so
// 9-digit order numbers and IDs stay; a 2-3-2-2 layout is a landline.
var mobilePrefixes = strings.Fields("45 50 51 53 57 60 66 69 72 73 78 79 88")

func phoneOK(m string) bool {
	if strings.HasPrefix(m, "+48") || strings.HasPrefix(m, "0048") {
		return true
	}
	return !isDigit(m[2]) || slices.Contains(mobilePrefixes, m[:2])
}

func peselOK(m string) bool {
	sum := 0
	for i, w := range []int{1, 3, 7, 9, 1, 3, 7, 9, 1, 3} {
		sum += int(m[i]-'0') * w
	}
	return (10-sum%10)%10 == int(m[10]-'0')
}

func luhn(s string) bool {
	sum, double := 0, false
	for i := len(s) - 1; i >= 0; i-- {
		if !isDigit(s[i]) {
			continue
		}
		d := int(s[i] - '0')
		if double {
			if d *= 2; d > 9 {
				d -= 9
			}
		}
		sum += d
		double = !double
	}
	return sum%10 == 0
}
