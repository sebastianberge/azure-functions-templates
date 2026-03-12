import os
import re
from pathlib import Path

ISSUE_BODY = os.environ["ISSUE_BODY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]

def extract_field(label: str, body: str) -> str:
    """
    Parses GitHub issue form markdown sections like:

    ### Modulnavn
    billing-api

    ### Språk
    python
    """
    pattern = rf"###\s*{re.escape(label)}\s*\n(.*?)(?=\n### |\Z)"
    match = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"Fant ikke felt: {label}")
    value = match.group(1).strip()
    return value

module_name = extract_field("Modulnavn", ISSUE_BODY)
language = extract_field("Språk", ISSUE_BODY)
owner = extract_field("Eier/team", ISSUE_BODY)

try:
    description = extract_field("Beskrivelse", ISSUE_BODY)
except ValueError:
    description = ""

if not re.fullmatch(r"[a-z0-9-]+", module_name):
    raise ValueError(
        f"Ugyldig modulnavn '{module_name}'. Bruk kun små bokstaver, tall og bindestrek."
    )

module_dir = Path("modules") / module_name
module_dir.mkdir(parents=True, exist_ok=True)

readme = f"""# {module_name}

Owner: {owner}
Language: {language}

## Description
{description or "TBD"}

## Development
Generated from GitHub issue #{ISSUE_NUMBER}.
"""

(module_dir / "README.md").write_text(readme, encoding="utf-8")

if language == "python":
    (module_dir / "main.py").write_text(
        'def main():\n'
        '    print("Hello from {0}")\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'.format(module_name),
        encoding="utf-8",
    )
    (module_dir / "requirements.txt").write_text("", encoding="utf-8")

elif language == "node":
    (module_dir / "package.json").write_text(
        """{
  "name": "%s",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "start": "node index.js"
  }
}
""" % module_name,
        encoding="utf-8",
    )
    (module_dir / "index.js").write_text(
        f'console.log("Hello from {module_name}");\n',
        encoding="utf-8",
    )

elif language == "dotnet":
    src_dir = module_dir / "src"
    src_dir.mkdir(exist_ok=True)
    (module_dir / "Directory.Build.props").write_text(
        """<Project>
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )
    (src_dir / "Program.cs").write_text(
        """Console.WriteLine("Hello from generated module");
""",
        encoding="utf-8",
    )
else:
    raise ValueError(f"Ukjent språk: {language}")

branch_name = f"scaffold/issue-{ISSUE_NUMBER}-{module_name}"
Path(".generated_branch_name").write_text(branch_name, encoding="utf-8")
print(f"Generated scaffold for {module_name} in {module_dir}")
print(f"Branch name: {branch_name}")