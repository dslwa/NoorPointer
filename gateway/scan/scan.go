package scan

import (
	"slices"
	"strings"

	"github.com/dslwa/NoorPointer/gateway/config"
)

type Finding struct {
	Control, Kind, Action string
}

func actionFor(p *config.Policy, r rule) string {
	var c *config.Control
	switch r.control {
	case "secrets":
		c = p.Controls.Secrets
	case "pii_regex":
		if pii := p.Controls.PIIRegex; pii != nil && slices.Contains(pii.Types, r.kind) {
			c = &pii.Control
		}
	}
	if c == nil || !c.Enabled {
		return ""
	}
	if p.Defaults.Mode == "monitor" {
		return "monitor"
	}
	return c.Action
}

// Rules run on a normalized copy so invisible characters and look-alike
// digits cannot hide data, but masks are cut from the original text, so
// everything outside a match is returned byte for byte.
//
// A mask can complete a neighbour's match (a phone masked inside a base64
// blob cuts off an encoded key), so masking repeats while a mask was glued
// to a byte that some rule reads as part of a match.
// ponytail: capped at 3 passes, deeper chains are crafted input, not data;
// the cap keeps a chain of glued tokens from costing one pass per token.
func Text(p *config.Policy, text string, found *[]Finding) string {
	for range 3 {
		var glued bool
		if text, glued = pass(p, text, found); !glued {
			break
		}
	}
	return text
}

func pass(p *config.Policy, text string, found *[]Finding) (string, bool) {
	norm, offs := normalize(text)
	glued := false
	for _, r := range rules {
		action := actionFor(p, r)
		if action == "" || (r.pre != nil && !r.pre(norm)) {
			continue
		}
		out, g := r.scan(text, norm, offs, action, found)
		if out != text {
			text, glued = out, glued || g
			norm, offs = normalize(text)
		}
	}
	return text, glued
}

func (r rule) scan(text, norm string, offs []int, action string, found *[]Finding) (string, bool) {
	at := func(i int) int {
		if offs == nil {
			return i
		}
		return offs[i]
	}
	var b strings.Builder
	last, pos, glued := 0, 0, false
	for pos < len(norm) {
		start, reEnd := r.locate(norm, pos)
		if start < 0 {
			break
		}
		end := r.accept(norm, start, reEnd)
		if end < 0 {
			pos = r.next(norm, start, reEnd)
			continue
		}
		*found = append(*found, Finding{r.control, r.kind, action})
		if action == "redact" {
			if last == 0 {
				b.Grow(len(text))
			}
			b.WriteString(text[last:at(start)])
			b.WriteString("[REDACTED:")
			b.WriteString(r.kind)
			b.WriteString("]")
			last = at(end)
			glued = glued || start > 0 && class[norm[start-1]]&clsSep == 0 || end < len(norm) && class[norm[end]]&clsSep == 0
		}
		pos = end
	}
	if last == 0 {
		return text, false
	}
	b.WriteString(text[last:])
	return b.String(), glued
}

func (r rule) locate(s string, pos int) (int, int) {
	if r.find != nil {
		return r.find(s, pos)
	}
	loc := r.re.FindStringIndex(s[pos:])
	if loc == nil {
		return -1, -1
	}
	return pos + loc[0], pos + loc[1]
}

func (r rule) accept(text string, start, end int) int {
	// A digit before a letter is a fine edge: "600123456PL61..." still has an IBAN.
	// A "+" is not: "+420 601 234 567" must not start a match at "420".
	if r.digitEdges && start > 0 && (isDigit(text[start-1]) || text[start-1] == '+') && !isLetter(text[start]) {
		return -1
	}
	// PII inside a long base64 run is chance, not data: a random 1 MB image
	// held ~10 mod-97-valid "IBANs", and masking them corrupts the image.
	if r.control == "pii_regex" && inBlob(text, start) {
		return -1
	}
	for e := end; e > start; e-- {
		edgeOK := !r.digitEdges || e == len(text) || !isDigit(text[e]) || isLetter(text[e-1])
		if edgeOK && (r.valid == nil || r.valid(text[start:e]) || r.inContext(text, start)) {
			return e
		}
		if !r.backoff {
			return -1
		}
	}
	return -1
}

// inBlob measures the base64 run around start only, so the answer does
// not depend on where a candidate's match happens to end.
func inBlob(text string, start int) bool {
	const blob = 80
	l, r := start, start
	for l > 0 && r-l < blob && class[text[l-1]]&clsB64 != 0 {
		l--
	}
	for r < len(text) && r-l < blob && class[text[r]]&clsB64 != 0 {
		r++
	}
	return r-l >= blob
}

// The window is cut after the last digit or "]", so "[REDACTED:pesel] 1..."
// reads the same as the "95081212347 1..." it came from and rescanning
// redacted output finds nothing new.
func (r rule) inContext(text string, start int) bool {
	w := text[max(0, start-20):start]
	w = strings.ToLower(w[strings.LastIndexAny(w, "0123456789]")+1:])
	return slices.ContainsFunc(r.context, func(c string) bool { return strings.Contains(w, c) })
}

// Digit rules retry from the next digit group, so "1 4111 1111 1111 1111" still finds the card;
// other rules skip the whole candidate, otherwise a long token would be
// re-checked at every offset (quadratic time).
func (r rule) next(text string, start, end int) int {
	if !r.digitEdges {
		return end
	}
	i := start + 1
	for i < len(text) && isDigit(text[i]) {
		i++
	}
	return i
}
