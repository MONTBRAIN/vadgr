"""Tests for deterministic scaffold generation.

The scaffold generator creates the standard project structure for every
generated workflow. This is the part that MUST be deterministic -- code
always produces the same output for the same input.
"""

import os
import shutil
import tempfile

import pytest

from forge.scripts.src.scaffold import (
    generate_scaffold, add_script, create_venv, install_dependencies, ScaffoldConfig,
)


@pytest.fixture
def output_dir():
    """Create a temp directory and clean it up after test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def simple_config():
    """Minimal config for a simple workflow."""
    return ScaffoldConfig(
        workflow_name="code-reviewer",
        workflow_description="Reviews code for quality and style issues.",
        folder_name="code-reviewer",
        steps=[
            {"number": 1, "name": "Analyze Code", "command": "analyze-code"},
        ],
        agents=[
            {"number": 2, "name": "Code_Analyst"},
        ],
        computer_use=False,
    )


@pytest.fixture
def multi_step_config():
    """Config for a multi-step workflow with computer use."""
    return ScaffoldConfig(
        workflow_name="website-auditor",
        workflow_description="Audits websites for accessibility and performance.",
        folder_name="website-auditor",
        steps=[
            {"number": 1, "name": "Crawl Site", "command": "crawl-site"},
            {"number": 2, "name": "Analyze Pages", "command": "analyze-pages"},
            {"number": 3, "name": "Generate Report", "command": "generate-report"},
        ],
        agents=[
            {"number": 2, "name": "Web_Crawler"},
            {"number": 3, "name": "Accessibility_Analyst"},
            {"number": 4, "name": "Report_Writer"},
        ],
        computer_use=True,
    )


@pytest.fixture
def uuid_config():
    """Config where folder_name is a UUID (from API with id field)."""
    return ScaffoldConfig(
        workflow_name="product-name-generator",
        workflow_description="Generates creative product names.",
        folder_name="8d7b4f8d-b735-4304-84e7-6919b50f1a43",
        steps=[
            {"number": 1, "name": "Brainstorm", "command": "brainstorm"},
            {"number": 2, "name": "Verify", "command": "verify"},
        ],
        agents=[
            {"number": 2, "name": "Naming_Strategist"},
        ],
        computer_use=False,
    )


# --- Directory structure tests ---


class TestDirectoryStructure:
    """The scaffold MUST create these directories every time."""

    def test_creates_root_directory(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        root = os.path.join(output_dir, simple_config.folder_name)
        assert os.path.isdir(root)

    def test_creates_claude_commands_dir(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, ".claude", "commands")
        assert os.path.isdir(path)

    def test_creates_agent_prompts_dir(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "agent", "Prompts")
        assert os.path.isdir(path)

    def test_creates_agent_scripts_src(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "agent", "scripts", "src")
        assert os.path.isdir(path)

    def test_creates_agent_scripts_tests(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "agent", "scripts", "tests")
        assert os.path.isdir(path)

    def test_creates_agent_utils_code(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "agent", "utils", "code")
        assert os.path.isdir(path)

    def test_creates_agent_utils_docs(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "agent", "utils", "docs")
        assert os.path.isdir(path)

    def test_creates_agent_steps_dir(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "agent", "steps")
        assert os.path.isdir(path)

    def test_creates_output_dir(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "output")
        assert os.path.isdir(path)

    def test_creates_computer_use_dir_when_enabled(self, output_dir, multi_step_config):
        generate_scaffold(multi_step_config, output_dir)
        path = os.path.join(output_dir, multi_step_config.folder_name, "computer_use")
        assert os.path.isdir(path)

    def test_no_computer_use_dir_when_disabled(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "computer_use")
        assert not os.path.exists(path)


# --- Required files tests ---


class TestRequiredFiles:
    """Every scaffold MUST contain these files."""

    def test_readme_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "README.md")
        assert os.path.isfile(path)

    def test_claude_md_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "CLAUDE.md")
        assert os.path.isfile(path)

    def test_fix_command_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, ".claude", "commands", "fix.md")
        assert os.path.isfile(path)

    def test_workflow_fixer_prompt_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, "agent", "Prompts", "00_Workflow_Fixer.md"
        )
        assert os.path.isfile(path)

    def test_senior_prompt_engineer_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, "agent", "Prompts", "01_Senior_Prompt_Engineer.md"
        )
        assert os.path.isfile(path)

    def test_scripts_readme_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, "agent", "scripts", "README.md"
        )
        assert os.path.isfile(path)

    def test_requirements_txt_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, "agent", "scripts", "requirements.txt"
        )
        assert os.path.isfile(path)

    def test_gitkeep_in_empty_dirs(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        root = os.path.join(output_dir, simple_config.folder_name)
        for subdir in [
            "agent/steps",
            "agent/utils/code",
            "agent/utils/docs",
            "agent/scripts/tests",
            "output",
        ]:
            gitkeep = os.path.join(root, subdir, ".gitkeep")
            assert os.path.isfile(gitkeep), f"Missing .gitkeep in {subdir}"

    def test_export_scripts_copied(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        src_dir = os.path.join(
            output_dir, simple_config.folder_name, "agent", "scripts", "src"
        )
        for script in ("gen_document.py", "gen_xlsx.py"):
            path = os.path.join(src_dir, script)
            assert os.path.isfile(path), f"Missing export script: {script}"

    def test_requirements_has_export_deps(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, "agent", "scripts", "requirements.txt"
        )
        content = open(path).read()
        assert "reportlab" in content
        assert "python-docx" in content
        assert "openpyxl" in content

    def test_computer_use_config_when_enabled(self, output_dir, multi_step_config):
        generate_scaffold(multi_step_config, output_dir)
        path = os.path.join(
            output_dir, multi_step_config.folder_name, "computer_use", "config.yaml"
        )
        assert os.path.isfile(path)

    def test_venv_created_automatically(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        venv_dir = os.path.join(
            output_dir, simple_config.folder_name, "agent", "scripts", ".venv"
        )
        assert os.path.isdir(venv_dir)
        assert os.path.isfile(os.path.join(venv_dir, "bin", "python"))
        assert os.path.isfile(os.path.join(venv_dir, "bin", "pip"))


# --- Command files tests ---


class TestCommandFiles:
    """One command per step + start + fix."""

    def test_start_command_exists(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, ".claude", "commands",
            f"start-{simple_config.workflow_name}.md",
        )
        assert os.path.isfile(path)

    def test_step_commands_exist(self, output_dir, multi_step_config):
        generate_scaffold(multi_step_config, output_dir)
        cmd_dir = os.path.join(
            output_dir, multi_step_config.folder_name, ".claude", "commands"
        )
        for step in multi_step_config.steps:
            path = os.path.join(cmd_dir, f"{step['command']}.md")
            assert os.path.isfile(path), f"Missing command: {step['command']}.md"

    def test_computer_use_commands_when_enabled(self, output_dir, multi_step_config):
        generate_scaffold(multi_step_config, output_dir)
        cmd_dir = os.path.join(
            output_dir, multi_step_config.folder_name, ".claude", "commands"
        )
        for cmd in ["execute-workflow.md", "pause-execution.md", "resume-execution.md"]:
            assert os.path.isfile(os.path.join(cmd_dir, cmd)), f"Missing: {cmd}"

    def test_no_computer_use_commands_when_disabled(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        cmd_dir = os.path.join(
            output_dir, simple_config.folder_name, ".claude", "commands"
        )
        assert not os.path.exists(os.path.join(cmd_dir, "execute-workflow.md"))


# --- File content tests ---


class TestFileContents:
    """Generated files must have correct content -- no leftover placeholders."""

    def test_readme_contains_workflow_name(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "README.md")
        content = open(path).read()
        assert simple_config.workflow_name in content

    def test_readme_contains_description(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "README.md")
        content = open(path).read()
        assert simple_config.workflow_description in content

    def test_readme_no_leftover_placeholders(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "README.md")
        content = open(path).read()
        assert "{{" not in content

    def test_claude_md_no_leftover_placeholders(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "CLAUDE.md")
        content = open(path).read()
        # The naming conventions section intentionally contains {{UPPER_SNAKE_CASE}}
        # as documentation. Strip that known instance before checking.
        check = content.replace("{{UPPER_SNAKE_CASE}}", "")
        assert "{{" not in check

    def test_claude_md_contains_structure_tree(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(output_dir, simple_config.folder_name, "CLAUDE.md")
        content = open(path).read()
        assert "Prompts/" in content
        assert "steps/" in content
        assert "scripts/" in content
        assert "commands/" in content
        assert "output/" in content

    def test_start_command_references_agentic_md(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, ".claude", "commands",
            f"start-{simple_config.workflow_name}.md",
        )
        content = open(path).read()
        assert "agentic.md" in content

    def test_step_command_references_step_file(self, output_dir, multi_step_config):
        generate_scaffold(multi_step_config, output_dir)
        path = os.path.join(
            output_dir, multi_step_config.folder_name, ".claude", "commands",
            "crawl-site.md",
        )
        content = open(path).read()
        assert "agent/steps/step_01_crawl-site.md" in content

    def test_step_command_references_step(self, output_dir, multi_step_config):
        generate_scaffold(multi_step_config, output_dir)
        path = os.path.join(
            output_dir, multi_step_config.folder_name, ".claude", "commands",
            "crawl-site.md",
        )
        content = open(path).read()
        assert "Step 1" in content or "Crawl Site" in content

    def test_fix_command_content(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, ".claude", "commands", "fix.md"
        )
        content = open(path).read()
        assert "00_Workflow_Fixer.md" in content
        assert "agentic.md" in content

    def test_workflow_fixer_is_copied_from_template(self, output_dir, simple_config):
        generate_scaffold(simple_config, output_dir)
        path = os.path.join(
            output_dir, simple_config.folder_name, "agent", "Prompts", "00_Workflow_Fixer.md"
        )
        content = open(path).read()
        assert "Workflow Fixer" in content
        assert "Diagnostician" in content


# --- Determinism tests ---


class TestDeterminism:
    """Same input MUST produce identical output every time."""

    def test_two_runs_produce_identical_files(self, simple_config):
        dir1 = tempfile.mkdtemp()
        dir2 = tempfile.mkdtemp()
        try:
            generate_scaffold(simple_config, dir1)
            generate_scaffold(simple_config, dir2)

            root1 = os.path.join(dir1, simple_config.folder_name)
            root2 = os.path.join(dir2, simple_config.folder_name)

            # Exclude .venv/ -- venv files contain absolute paths that differ
            files1 = set()
            for dirpath, dirnames, filenames in os.walk(root1):
                dirnames[:] = [d for d in dirnames if d != ".venv"]
                for f in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, f), root1)
                    files1.add(rel)

            files2 = set()
            for dirpath, dirnames, filenames in os.walk(root2):
                dirnames[:] = [d for d in dirnames if d != ".venv"]
                for f in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, f), root2)
                    files2.add(rel)

            assert files1 == files2, f"Different file sets: {files1.symmetric_difference(files2)}"

            for rel in files1:
                content1 = open(os.path.join(root1, rel)).read()
                content2 = open(os.path.join(root2, rel)).read()
                assert content1 == content2, f"Different content in {rel}"
        finally:
            shutil.rmtree(dir1, ignore_errors=True)
            shutil.rmtree(dir2, ignore_errors=True)

    def test_deterministic_with_multi_step(self, multi_step_config):
        dir1 = tempfile.mkdtemp()
        dir2 = tempfile.mkdtemp()
        try:
            generate_scaffold(multi_step_config, dir1)
            generate_scaffold(multi_step_config, dir2)

            root1 = os.path.join(dir1, multi_step_config.folder_name)
            root2 = os.path.join(dir2, multi_step_config.folder_name)

            # Exclude .venv/ -- venv files contain absolute paths that differ
            def collect_files(root):
                result = []
                for dp, dirnames, fns in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d != ".venv"]
                    for f in fns:
                        result.append(os.path.relpath(os.path.join(dp, f), root))
                return sorted(result)

            files1 = collect_files(root1)
            files2 = collect_files(root2)
            assert files1 == files2

            for rel in files1:
                assert open(os.path.join(root1, rel)).read() == open(os.path.join(root2, rel)).read()
        finally:
            shutil.rmtree(dir1, ignore_errors=True)
            shutil.rmtree(dir2, ignore_errors=True)


# --- UUID folder name tests ---


class TestUUIDFolderName:
    """When id is provided, folder_name is the UUID, not the workflow name."""

    def test_uses_uuid_as_folder(self, output_dir, uuid_config):
        generate_scaffold(uuid_config, output_dir)
        root = os.path.join(output_dir, uuid_config.folder_name)
        assert os.path.isdir(root)
        # The workflow name should still appear in README content
        readme = open(os.path.join(root, "README.md")).read()
        assert uuid_config.workflow_name in readme


# --- Edge cases ---


class TestEdgeCases:
    """Handle unusual but valid inputs."""

    def test_single_step_workflow(self, output_dir):
        config = ScaffoldConfig(
            workflow_name="simple-task",
            workflow_description="A simple one-step task.",
            folder_name="simple-task",
            steps=[{"number": 1, "name": "Do The Thing", "command": "do-the-thing"}],
            agents=[{"number": 2, "name": "Task_Agent"}],
            computer_use=False,
        )
        generate_scaffold(config, output_dir)
        root = os.path.join(output_dir, "simple-task")
        assert os.path.isdir(root)
        assert os.path.isfile(os.path.join(root, "README.md"))

    def test_many_steps_workflow(self, output_dir):
        steps = [
            {"number": i, "name": f"Step {i}", "command": f"step-{i}"}
            for i in range(1, 8)
        ]
        agents = [
            {"number": i + 1, "name": f"Agent_{i}"}
            for i in range(1, 5)
        ]
        config = ScaffoldConfig(
            workflow_name="big-workflow",
            workflow_description="A complex multi-step workflow.",
            folder_name="big-workflow",
            steps=steps,
            agents=agents,
            computer_use=False,
        )
        generate_scaffold(config, output_dir)
        cmd_dir = os.path.join(output_dir, "big-workflow", ".claude", "commands")
        # 7 step commands + start + fix = 9
        md_files = [f for f in os.listdir(cmd_dir) if f.endswith(".md")]
        assert len(md_files) == 9


# --- add_format_script tests ---


class TestAddScript:
    """add_script places LLM-generated scripts into an agent's folder."""

    def test_creates_script_file(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "gen_html.py", "# gen_html code", "# test code")
        path = os.path.join(root, "agent", "scripts", "src", "gen_html.py")
        assert os.path.isfile(path)

    def test_creates_test_file(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "gen_html.py", "# gen_html code", "# test code")
        path = os.path.join(root, "agent", "scripts", "tests", "test_gen_html.py")
        assert os.path.isfile(path)

    def test_script_has_correct_content(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        script = "def generate_html(path, doc): pass"
        add_script(root, "gen_html.py", script, "# tests")
        path = os.path.join(root, "agent", "scripts", "src", "gen_html.py")
        assert open(path).read() == script

    def test_test_has_correct_content(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        test = "def test_html(): assert True"
        add_script(root, "gen_html.py", "# code", test)
        path = os.path.join(root, "agent", "scripts", "tests", "test_gen_html.py")
        assert open(path).read() == test

    def test_no_test_file_when_none(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "helper.py", "# helper code")
        src = os.path.join(root, "agent", "scripts", "src", "helper.py")
        assert os.path.isfile(src)
        test = os.path.join(root, "agent", "scripts", "tests", "test_helper.py")
        assert not os.path.exists(test)

    def test_adds_dependencies_to_requirements(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "gen_html.py", "# code", "# test", dependencies=["jinja2"])
        req_path = os.path.join(root, "agent", "scripts", "requirements.txt")
        content = open(req_path).read()
        assert "jinja2" in content

    def test_does_not_duplicate_dependencies(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "gen_html.py", "# code", "# test", dependencies=["reportlab"])
        req_path = os.path.join(root, "agent", "scripts", "requirements.txt")
        content = open(req_path).read()
        assert content.count("reportlab") == 1

    def test_multiple_dependencies(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "gen_pptx.py", "# code", "# test",
                   dependencies=["python-pptx", "Pillow"])
        req_path = os.path.join(root, "agent", "scripts", "requirements.txt")
        content = open(req_path).read()
        assert "python-pptx" in content
        assert "Pillow" in content

    def test_no_dependencies(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        req_path = os.path.join(root, "agent", "scripts", "requirements.txt")
        before = open(req_path).read()
        add_script(root, "fetch_data.py", "# code", "# test")
        after = open(req_path).read()
        assert before == after

    def test_creates_directories_if_missing(self, output_dir):
        root = os.path.join(output_dir, "bare-agent")
        os.makedirs(root)
        add_script(root, "gen_html.py", "# code", "# test")
        assert os.path.isfile(os.path.join(root, "agent", "scripts", "src", "gen_html.py"))
        assert os.path.isfile(os.path.join(root, "agent", "scripts", "tests", "test_gen_html.py"))

    def test_any_script_name(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        add_script(root, "fetch_api.py", "# fetcher", "# test fetcher")
        assert os.path.isfile(os.path.join(root, "agent", "scripts", "src", "fetch_api.py"))
        assert os.path.isfile(os.path.join(root, "agent", "scripts", "tests", "test_fetch_api.py"))


# --- Venv and dependency management ---


class TestCreateVenv:
    """create_venv creates a .venv and installs requirements."""

    def test_creates_venv_directory(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        create_venv(root)
        venv_dir = os.path.join(root, "agent", "scripts", ".venv")
        assert os.path.isdir(venv_dir)

    def test_venv_has_python(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        create_venv(root)
        python = os.path.join(root, "agent", "scripts", ".venv", "bin", "python")
        assert os.path.isfile(python)

    def test_venv_has_pip(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        create_venv(root)
        pip = os.path.join(root, "agent", "scripts", ".venv", "bin", "pip")
        assert os.path.isfile(pip)

    def test_installs_requirements(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        create_venv(root)
        # reportlab is in the default requirements.txt
        pip = os.path.join(root, "agent", "scripts", ".venv", "bin", "pip")
        import subprocess
        result = subprocess.run(
            [pip, "show", "reportlab"], capture_output=True, text=True
        )
        assert result.returncode == 0

    def test_creates_dirs_if_missing(self, output_dir):
        root = os.path.join(output_dir, "bare-agent")
        os.makedirs(root)
        scripts_dir = os.path.join(root, "agent", "scripts")
        os.makedirs(scripts_dir)
        # Write a minimal requirements.txt
        with open(os.path.join(scripts_dir, "requirements.txt"), "w") as f:
            f.write("")
        create_venv(root)
        assert os.path.isdir(os.path.join(scripts_dir, ".venv"))


class TestInstallDependencies:
    """install_dependencies installs from requirements.txt into existing venv."""

    def test_installs_new_dependency(self, output_dir, simple_config):
        root = generate_scaffold(simple_config, output_dir)
        create_venv(root)
        # Add a new dep and install
        req_path = os.path.join(root, "agent", "scripts", "requirements.txt")
        with open(req_path, "a") as f:
            f.write("pyyaml\n")
        install_dependencies(root)
        pip = os.path.join(root, "agent", "scripts", ".venv", "bin", "pip")
        import subprocess
        result = subprocess.run(
            [pip, "show", "pyyaml"], capture_output=True, text=True
        )
        assert result.returncode == 0

    def test_no_error_on_empty_requirements(self, output_dir):
        root = os.path.join(output_dir, "empty-agent")
        scripts_dir = os.path.join(root, "agent", "scripts")
        os.makedirs(scripts_dir)
        with open(os.path.join(scripts_dir, "requirements.txt"), "w") as f:
            f.write("")
        create_venv(root)
        install_dependencies(root)  # should not raise


class TestCLI:
    """CLI interface for scaffold operations."""

    def test_generate_from_json_string(self, output_dir):
        import json
        import subprocess
        config = json.dumps({
            "workflow_name": "cli-test",
            "workflow_description": "Test CLI scaffold.",
            "folder_name": "cli-test",
            "steps": [{"number": 1, "name": "Analyze", "command": "analyze"}],
            "agents": [{"number": 2, "name": "Analyzer"}],
            "computer_use": False,
        })
        result = subprocess.run(
            ["python3", "-m", "forge.scripts.src.scaffold", "generate",
             "--config", config, "--base-dir", output_dir],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert "root" in out
        root = out["root"]
        assert os.path.isdir(root)
        assert os.path.isfile(os.path.join(root, "README.md"))
        assert os.path.isfile(os.path.join(root, "CLAUDE.md"))
        assert os.path.isdir(os.path.join(root, "agent", "Prompts"))
        assert os.path.isdir(os.path.join(root, "agent", "steps"))
        assert os.path.isdir(os.path.join(root, "output"))

    def test_generate_from_json_file(self, output_dir):
        import json
        import subprocess
        config = {
            "workflow_name": "cli-file-test",
            "workflow_description": "Test CLI from file.",
            "folder_name": "cli-file-test",
            "steps": [{"number": 1, "name": "Run", "command": "run"}],
            "agents": [{"number": 2, "name": "Runner"}],
            "computer_use": False,
        }
        config_path = os.path.join(output_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
        result = subprocess.run(
            ["python3", "-m", "forge.scripts.src.scaffold", "generate",
             "--config", config_path, "--base-dir", output_dir],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert os.path.isdir(out["root"])
        assert os.path.isfile(os.path.join(out["root"], "README.md"))

    def test_add_script_via_cli(self, output_dir, simple_config):
        import json
        import subprocess
        root = generate_scaffold(simple_config, output_dir)
        # Write a temp script file
        script_path = os.path.join(output_dir, "my_script.py")
        with open(script_path, "w") as f:
            f.write("def hello(): return 'hi'\n")
        test_path = os.path.join(output_dir, "test_my_script.py")
        with open(test_path, "w") as f:
            f.write("def test_hello(): assert hello() == 'hi'\n")
        result = subprocess.run(
            ["python3", "-m", "forge.scripts.src.scaffold", "add-script",
             "--root", root, "--name", "my_script.py",
             "--script", script_path, "--test", test_path,
             "--deps", "requests,aiohttp"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["status"] == "ok"
        assert os.path.isfile(os.path.join(root, "agent", "scripts", "src", "my_script.py"))
        assert os.path.isfile(os.path.join(root, "agent", "scripts", "tests", "test_my_script.py"))
        req = open(os.path.join(root, "agent", "scripts", "requirements.txt")).read()
        assert "requests" in req
        assert "aiohttp" in req

    def test_generate_missing_config_fails(self):
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "forge.scripts.src.scaffold", "generate"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_no_command_fails(self):
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "forge.scripts.src.scaffold"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
