"""Extract a gateway binary from its local Docker image and test it without changing the main stack."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="noorpointer-gateway:acceptance")
    parser.add_argument("--build", action="store_true", help="build the current Go sources before testing")
    parser.add_argument("--budgets", action="store_true", help="also run budget acceptance cases (require gateway accounting)")
    args, pytest_args = parser.parse_known_args()
    root = Path(__file__).resolve().parents[1]
    if args.build:
        subprocess.run(["docker", "build", "-t", args.image, str(root / "gateway")], check=True)
    image = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", args.image], text=True).strip()
    print("Gateway image:", image, flush=True)
    with tempfile.TemporaryDirectory(prefix="noorpointer-acceptance-") as temporary:
        container = subprocess.check_output(["docker", "create", args.image], text=True).strip()
        binary = Path(temporary) / "gateway"
        try:
            subprocess.run(["docker", "cp", f"{container}:/gateway", str(binary)], check=True)
        finally:
            subprocess.run(["docker", "rm", "-v", container], check=True, stdout=subprocess.DEVNULL)
        binary.chmod(0o700)
        files = [str(root / "tests/test_gateway_acceptance.py")]
        if args.budgets:
            files.append(str(root / "tests/test_gateway_budgets.py"))
        return subprocess.run([sys.executable, "-m", "pytest", *files,
                               "-v", *pytest_args], cwd=root,
                              env={**os.environ, "GATEWAY_BINARY": str(binary)}).returncode


if __name__ == "__main__":
    raise SystemExit(main())
