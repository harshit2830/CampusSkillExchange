"""Run the explainable AIP matching demonstration."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "04_Python"))
from skill_exchange.matching import main


if __name__ == "__main__":
    main()
