package scan

import (
	"strings"
	"unicode"
	"unicode/utf8"
)

// Most non-ASCII text (Polish, emoji) has nothing to change: check first,
// so it skips building the offset table, 8 bytes per input byte.
func normalize(s string) (string, []int) {
	if !needsNormalize(s) {
		return s, nil
	}
	var b strings.Builder
	offs := make([]int, 0, len(s)+1)
	for i, r := range s {
		switch {
		case unicode.Is(unicode.Cf, r):
			continue
		case r >= 0xFF01 && r <= 0xFF5E:
			r -= 0xFEE0
		case r > unicode.MaxASCII && unicode.IsDigit(r):
			r = '0' + digitValue(r)
		}
		n, _ := b.WriteRune(r)
		for range n {
			offs = append(offs, i)
		}
	}
	return b.String(), append(offs, len(s))
}

func needsNormalize(s string) bool {
	for i := 0; i < len(s); {
		if s[i] < utf8.RuneSelf {
			i++
			continue
		}
		r, n := utf8.DecodeRuneInString(s[i:])
		// Below U+0600 only the soft hyphen changes: Polish and other Latin
		// letters skip the Unicode table lookups.
		if r < 0x600 && r != 0xAD && r != utf8.RuneError {
			i += n
			continue
		}
		if r == utf8.RuneError || unicode.Is(unicode.Cf, r) || r >= 0xFF01 && r <= 0xFF5E || unicode.IsDigit(r) {
			return true
		}
		i += n
	}
	return false
}

// digitValue relies on Unicode encoding decimal digits as runs of 0..9.
func digitValue(r rune) rune {
	k := rune(0)
	for unicode.IsDigit(r - k - 1) {
		k++
	}
	return k % 10
}
