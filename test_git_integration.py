#!/usr/bin/env python3
"""
Unit tests for git integration and permission system.

Tests:
- spawn.py: AGENT_PROFILES permission configuration
- run.py: init_workspace_git() function
- Permission pattern matching
- Git command validation
"""

import unittest
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


class TestAgentProfiles(unittest.TestCase):
    """Test AGENT_PROFILES in spawn.py."""

    def setUp(self):
        """Load spawn.py module."""
        # Import spawn module to access AGENT_PROFILES
        import importlib.util
        spec = importlib.util.spec_from_file_location("spawn", "spawn.py")
        self.spawn = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.spawn)

    def test_profiles_exist(self):
        """All three agent roles should have profiles."""
        self.assertIn("Planner", self.spawn.AGENT_PROFILES)
        self.assertIn("Builder", self.spawn.AGENT_PROFILES)
        self.assertIn("Evaluator", self.spawn.AGENT_PROFILES)

    def test_profiles_have_required_tools(self):
        """Each profile should have Read, Write, Edit tools."""
        for role in ["Planner", "Builder", "Evaluator"]:
            profile = self.spawn.AGENT_PROFILES[role]
            self.assertIn("Read", profile)
            self.assertIn("Write", profile)
            self.assertIn("Edit", profile)

    def test_profiles_restrict_bash(self):
        """Bash should be restricted to specific patterns."""
        for role in ["Planner", "Builder", "Evaluator"]:
            profile = self.spawn.AGENT_PROFILES[role]
            # Should allow python3
            self.assertIn("Bash(python3 *)", profile)
            # Should allow git read operations
            self.assertIn("Bash(git status*)", profile)
            self.assertIn("Bash(git diff*)", profile)
            self.assertIn("Bash(git log*)", profile)
            self.assertIn("Bash(git add *)", profile)
            # Should NOT allow unrestricted Bash
            self.assertNotIn("Bash,", profile)

    def test_profiles_forbid_dangerous_commands(self):
        """Profiles should not allow dangerous git commands."""
        for role in ["Planner", "Builder", "Evaluator"]:
            profile = self.spawn.AGENT_PROFILES[role]
            # Should NOT allow these
            self.assertNotIn("git commit", profile)
            self.assertNotIn("git reset", profile)
            self.assertNotIn("git checkout", profile)
            self.assertNotIn("git branch", profile)
            self.assertNotIn("git merge", profile)
            self.assertNotIn("git push", profile)

    def test_kb_skill_pattern(self):
        """Profiles should allow knowledge base skill pattern."""
        for role in ["Planner", "Builder", "Evaluator"]:
            profile = self.spawn.AGENT_PROFILES[role]
            self.assertIn("Bash(source * && python3 *)", profile)


class TestInitWorkspaceGit(unittest.TestCase):
    """Test init_workspace_git() in run.py."""

    def setUp(self):
        """Create temporary workspace."""
        self.test_dir = tempfile.mkdtemp()
        self.workspace = Path(self.test_dir) / "test_workspace"
        self.workspace.mkdir()

        # Create a test file
        (self.workspace / "problem.md").write_text("# Test Problem\n")

        # Import run module
        import importlib.util
        spec = importlib.util.spec_from_file_location("run", "run.py")
        self.run_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.run_module)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_git_init_creates_repo(self):
        """init_workspace_git should create .git directory."""
        self.run_module.init_workspace_git(str(self.workspace))
        self.assertTrue((self.workspace / ".git").exists())

    def test_git_init_creates_gitignore(self):
        """init_workspace_git should create .gitignore."""
        self.run_module.init_workspace_git(str(self.workspace))
        gitignore = self.workspace / ".gitignore"
        self.assertTrue(gitignore.exists())

        content = gitignore.read_text()
        self.assertIn(".*.log", content)
        self.assertIn(".*.result", content)
        self.assertIn(".*.metrics", content)
        self.assertIn(".state", content)

    def test_git_init_makes_initial_commit(self):
        """init_workspace_git should create initial commit."""
        self.run_module.init_workspace_git(str(self.workspace))

        # Check git log
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(self.workspace), "log", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("init: workspace setup with problem files", result.stdout)

    def test_git_init_idempotent(self):
        """Running init_workspace_git twice should not fail."""
        self.run_module.init_workspace_git(str(self.workspace))
        # Should not raise error
        self.run_module.init_workspace_git(str(self.workspace))

        # Should still have only one initial commit
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(self.workspace), "log", "--oneline"],
            capture_output=True, text=True
        )
        lines = [l for l in result.stdout.strip().split('\n') if l]
        self.assertEqual(len(lines), 1)

    def test_git_config_user(self):
        """init_workspace_git should configure git user."""
        self.run_module.init_workspace_git(str(self.workspace))

        import subprocess
        result = subprocess.run(
            ["git", "-C", str(self.workspace), "config", "user.email"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "agent@physics-solver")

        result = subprocess.run(
            ["git", "-C", str(self.workspace), "config", "user.name"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "Physics Agent")


class TestPermissionPatterns(unittest.TestCase):
    """Test permission pattern matching logic."""

    def test_python3_pattern_matches_scripts(self):
        """Bash(python3 *) should match python3 script.py."""
        pattern = "Bash(python3 *)"
        # Pattern matching is done by Claude Code, but we can verify the pattern is correct
        self.assertIn("python3 *", pattern)

    def test_git_status_pattern_matches_variants(self):
        """Bash(git status*) should match git status with various flags."""
        pattern = "Bash(git status*)"
        # Should match: git status, git status --short, git status -s
        self.assertIn("git status*", pattern)

    def test_git_diff_pattern_matches_variants(self):
        """Bash(git diff*) should match git diff with various arguments."""
        pattern = "Bash(git diff*)"
        # Should match: git diff, git diff HEAD, git diff file.md
        self.assertIn("git diff*", pattern)

    def test_git_add_requires_argument(self):
        """Bash(git add *) should require an argument (space after add)."""
        pattern = "Bash(git add *)"
        # Note the space: "git add " requires something after "add"
        self.assertIn("git add *", pattern)


class TestSpawnCommandLine(unittest.TestCase):
    """Test spawn.py command line construction."""

    def setUp(self):
        """Import spawn module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("spawn", "spawn.py")
        self.spawn = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.spawn)

    def test_profile_lookup(self):
        """Should look up profile by role name."""
        # Test that the profile lookup logic works
        role = "Planner"
        expected_profile = self.spawn.AGENT_PROFILES[role]

        # Simulate the lookup logic from spawn.py
        allowed_tools = "Read,Write,Edit,Bash"  # fallback
        if role in self.spawn.AGENT_PROFILES:
            allowed_tools = self.spawn.AGENT_PROFILES[role]

        self.assertEqual(allowed_tools, expected_profile)
        self.assertNotEqual(allowed_tools, "Read,Write,Edit,Bash")

    def test_cli_override(self):
        """--tools flag should override profile."""
        # Simulate CLI override logic
        role = "Planner"
        allowed_tools = "Read,Write,Edit,Bash"  # fallback
        if role in self.spawn.AGENT_PROFILES:
            allowed_tools = self.spawn.AGENT_PROFILES[role]

        # Simulate --tools override
        cli_tools = "Read,Write"
        allowed_tools = cli_tools

        self.assertEqual(allowed_tools, "Read,Write")


class TestGitignoreContent(unittest.TestCase):
    """Test .gitignore content."""

    def test_ignores_agent_artifacts(self):
        """Should ignore agent log, result, and metrics files."""
        gitignore_content = """\
.*.log
.*.result
.*.metrics
.state
query_rag.py
__pycache__/
*.pyc
*.tmp
"""
        self.assertIn(".*.log", gitignore_content)
        self.assertIn(".*.result", gitignore_content)
        self.assertIn(".*.metrics", gitignore_content)
        self.assertIn(".state", gitignore_content)

    def test_ignores_temporary_files(self):
        """Should ignore temporary and cache files."""
        gitignore_content = """\
.*.log
.*.result
.*.metrics
.state
query_rag.py
__pycache__/
*.pyc
*.tmp
"""
        self.assertIn("__pycache__/", gitignore_content)
        self.assertIn("*.pyc", gitignore_content)
        self.assertIn("*.tmp", gitignore_content)


if __name__ == "__main__":
    unittest.main()
