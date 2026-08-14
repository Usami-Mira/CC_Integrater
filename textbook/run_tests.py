#!/usr/bin/env python3
"""
Run all unit tests for the textbook processing pipeline.
"""

import sys
import unittest
from pathlib import Path


def main():
    """Discover and run all tests."""
    # Set up test discovery
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Find all test files in textbook directory
    textbook_dir = Path(__file__).parent
    test_files = list(textbook_dir.glob('test_*.py'))

    if not test_files:
        print("No test files found!")
        return 1

    print(f"Found {len(test_files)} test file(s):")
    for test_file in test_files:
        print(f"  - {test_file.name}")
    print()

    # Load tests from each file
    for test_file in test_files:
        # Import the module
        module_name = test_file.stem
        spec = __import__(module_name)
        # Load tests from the module
        tests = loader.loadTestsFromModule(spec)
        suite.addTests(tests)

    # Run all tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code based on test results
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
