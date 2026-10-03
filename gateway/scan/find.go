package scan

import "strings"

// Go's regexp has no DFA: a pattern without a literal prefix runs the NFA
// over every byte of a 1 MB text. These rules are matched by hand instead,
// 10-50x faster; find_test.go holds each regex as the spec and fuzzes that
// both return the same spans.

// starts calls match only where a card or phone can start: a digit or "+",
// never the middle of a digit run, so the loop skips both.
func starts(match func(string, int) int) func(string, int) (int, int) {
	return func(s string, pos int) (int, int) {
		for i := pos; i < len(s); {
			if c := s[i]; !isDigit(c) && c != '+' {
				i++
				continue
			}
			if e := match(s, i); e >= 0 {
				return i, e
			}
			for i++; i < len(s) && isDigit(s[i]); i++ {
			}
		}
		return -1, -1
	}
}

var (
	findCard  = starts(matchCard)
	findPhone = starts(matchPhone)
)

// digits returns i plus the run of up to max digits at i.
func digits(s string, i, max int) int {
	j := i
	for j < len(s) && j-i < max && isDigit(s[j]) {
		j++
	}
	return j
}

// group matches one byte of seps (none when seps is empty), then min..max
// digits, greedy; it returns the end or -1, and passes -1 through.
func group(s string, i int, seps string, min, max int) int {
	if i < 0 {
		return -1
	}
	if seps != "" {
		if i >= len(s) || strings.IndexByte(seps, s[i]) < 0 {
			return -1
		}
		i++
	}
	if j := digits(s, i, max); j-i >= min {
		return j
	}
	return -1
}

// matchCard is the card regex anchored at i, alternatives in regex order.
func matchCard(s string, i int) int {
	if j := digits(s, i, 19); j-i >= 13 {
		return j
	}
	if e := group(s, group(s, group(s, group(s, i, "", 4, 4), " .-", 4, 4), " .-", 4, 4), " .-", 1, 4); e >= 0 {
		if f := group(s, e, " .-", 1, 3); f >= 0 {
			return f
		}
		return e
	}
	return group(s, group(s, group(s, i, "", 4, 4), " .-", 6, 6), " .-", 4, 5)
}

// matchPhone is the phone regex anchored at i: the optional +48/0048 prefix
// first, the bare number if the rest fails, as the regex backtracks.
func matchPhone(s string, i int) int {
	k := -1
	if strings.HasPrefix(s[i:], "+48") {
		k = i + 3
	} else if strings.HasPrefix(s[i:], "0048") {
		k = i + 4
	}
	if k >= 0 {
		if k < len(s) && (s[k] == ' ' || s[k] == '-') {
			k++
		}
		if e := phoneBody(s, k); e >= 0 {
			return e
		}
	}
	return phoneBody(s, i)
}

func phoneBody(s string, i int) int {
	opt := func(j int) int {
		if j >= 0 && j < len(s) && strings.IndexByte(" .-", s[j]) >= 0 && j+1 < len(s) && isDigit(s[j+1]) {
			return j + 1
		}
		return j
	}
	if e := group(s, opt(group(s, opt(group(s, i, "", 3, 3)), "", 3, 3)), "", 3, 3); e >= 0 {
		return e
	}
	return group(s, group(s, group(s, group(s, i, "", 2, 2), " .-", 3, 3), " .-", 2, 2), " .-", 2, 2)
}

// A longer run fails the digit edges anyway, so only exact 11s count.
func findPESEL(s string, pos int) (int, int) {
	for i := pos; i < len(s); {
		if !isDigit(s[i]) {
			i++
			continue
		}
		j := i
		for j < len(s) && isDigit(s[j]) {
			j++
		}
		if j-i == 11 && (i == 0 || !isDigit(s[i-1])) {
			return i, j
		}
		i = j
	}
	return -1, -1
}

// findIBAN checks the country first, then walks 4-char groups (a space may
// only open a group) to the country's exact length, so there is one end to
// validate instead of a backoff over every prefix. ASCII letters only: Go's
// (?i) would fold ſ and K (Kelvin) in, breaking the byte length check.
func findIBAN(s string, pos int) (int, int) {
	alnum := func(c byte) bool { return isDigit(c) || isLetter(c) }
	for i := pos; i+4 <= len(s); i++ {
		if !isLetter(s[i]) || !isLetter(s[i+1]) || !isDigit(s[i+2]) || !isDigit(s[i+3]) {
			continue
		}
		want := ibanLength(s[i], s[i+1])
		if want == 0 {
			continue
		}
		e, n := i+4, 4
		for e < len(s) && n < want {
			if s[e] == ' ' && n%4 == 0 && e+1 < len(s) && alnum(s[e+1]) {
				e++
			}
			if !alnum(s[e]) {
				break
			}
			n, e = n+1, e+1
		}
		if n == want {
			return i, e
		}
	}
	return -1, -1
}

// A base64 run of 24+ and up to two "=": the regex has no literal prefix,
// so Go would run its NFA over every byte of a pasted image.
func findB64(s string, pos int) (int, int) {
	for i := pos; i < len(s); {
		j := i
		for j < len(s) && class[s[j]]&clsB64 != 0 {
			j++
		}
		if j-i >= 24 {
			e := j
			for e < len(s) && e-j < 2 && s[e] == '=' {
				e++
			}
			return i, e
		}
		i = j + 1
	}
	return -1, -1
}

// findEmail jumps between "@" with IndexByte (SIMD) and grows the match
// both ways. The domain takes the last "." followed by 2+ letters, as the
// regex's greedy [A-Za-z0-9.-]+ does.
func findEmail(s string, pos int) (int, int) {
	for {
		k := strings.IndexByte(s[pos:], '@')
		if k < 0 {
			return -1, -1
		}
		k += pos
		i := k
		for i > pos && class[s[i-1]]&clsLocal != 0 {
			i--
		}
		j := k + 1
		for j < len(s) && class[s[j]]&clsDomain != 0 {
			j++
		}
		if i < k {
			for p := j - 3; p > k+1; p-- {
				if s[p] == '.' && isLetter(s[p+1]) && isLetter(s[p+2]) {
					e := p + 3
					for e < len(s) && isLetter(s[e]) {
						e++
					}
					return i, e
				}
			}
		}
		pos = k + 1
	}
}
