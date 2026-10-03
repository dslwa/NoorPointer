package scan

import (
	"strings"
	"testing"
)

func benchScan(b *testing.B, text string) {
	p := redactAllPolicy()
	b.SetBytes(int64(len(text)))
	for b.Loop() {
		var found []Finding
		Text(p, text, &found)
	}
}

func BenchmarkScanPrompt(b *testing.B) {
	benchScan(b, "Explain how neural networks minimize loss functions using backpropagation.")
}

func BenchmarkScanPII(b *testing.B) {
	benchScan(b, "My PESEL is 95081212345, mail jan@example.com, card 4111 1111 1111 1111.")
}

func BenchmarkScan1MBText(b *testing.B) {
	benchScan(b, strings.Repeat("Lorem ipsum dolor sit amet, consectetur adipiscing elit. ", 17000))
}

func BenchmarkScan1MBDigits(b *testing.B) {
	benchScan(b, strings.Repeat("1234 5678 ", 100000))
}

func BenchmarkScan1MBSpacedDigits(b *testing.B) {
	benchScan(b, strings.Repeat("1 ", 500000))
}

func BenchmarkScan1MBIBANLike(b *testing.B) {
	benchScan(b, strings.Repeat("AB12 ", 200000))
}
