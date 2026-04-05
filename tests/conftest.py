import sys
import os

# Add the project root to sys.path so tests can import top-level modules
# without requiring an editable install or manual path manipulation in each file.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
