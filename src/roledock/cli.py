"""No paid model keys required for the offline demo."""
import argparse
from .runtime import RoleDock
from .security import DEMO_IDENTITIES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", default="新能源行业研究")
    parser.add_argument("--role", choices=["investor", "ir", "finance", "ops", "deal", "compliance", "admin"], default="investor")
    args = parser.parse_args()
    principal = next(p for p in DEMO_IDENTITIES.values() if p.role == args.role)
    result = RoleDock().execute(principal, args.question)
    print(f"status={result.status} expert={result.expert} tool={result.tool}")
    print(result.content)


if __name__ == "__main__":
    main()
