#!/usr/bin/env python3
"""Run the standalone Subject 5 Trigger analysis."""

from __future__ import annotations

import sys
from pathlib import Path

from subject2_trigger_analysis import main


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    user_args = sys.argv[1:]
    sys.argv = [
        sys.argv[0],
        "--subject-id",
        "5",
        "--input-dir",
        str(root / "5" / "Trigger"),
        "--output-dir",
        str(root / "analysis_outputs" / "subject5_trigger"),
        *user_args,
    ]
    main()
