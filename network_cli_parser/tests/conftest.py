import sys
from pathlib import Path

# Allow test files to import from network_cli_parser/ directly
sys.path.insert(0, str(Path(__file__).parent.parent))
