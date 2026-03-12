import os
import re
from pathlib import Path

ISSUE_BODY = os.environ["ISSUE_BODY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]

RUNTIME_SETTINGS = {
    "python": {
        "worker_runtime": "python",
        "linux_fx_version": "PYTHON|3.12",
    },
    "node": {
        "worker_runtime": "node",
        "linux_fx_version": "NODE|20-lts",
    },
    "dotnet": {
        "worker_runtime": "dotnet-isolated",
        "linux_fx_version": "DOTNET-ISOLATED|8.0",
    },
}


def set_github_output(name: str, value: str) -> None:
    github_output = os.getenv("GITHUB_OUTPUT")
    if not github_output:
        return

    with open(github_output, "a", encoding="utf-8") as output_file:
        output_file.write(f"{name}={value}\n")


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


def to_storage_account_name(module_name: str) -> str:
    base = re.sub(r"[^a-z0-9]", "", module_name)
    return f"{base[:22]}sa"[:24]


def build_readme(module_name: str, owner: str, language: str, description: str) -> str:
    return f"""# {module_name}

Owner: {owner}
Language: {language}

## Description
{description or "TBD"}

## Infrastructure
- `infra/main.bicep` scaffolds the Azure Function App and required platform resources.
- `infra/main.bicepparam` contains starter values for names, runtime, and tags.

## Development
Generated from GitHub issue #{ISSUE_NUMBER}.
"""


def build_main_bicep(
    module_name: str,
    storage_account_name: str,
    worker_runtime: str,
    linux_fx_version: str,
) -> str:
    return f"""@description('Name of the Azure Function app.')
param functionAppName string = '{module_name}-func'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Name of the storage account used by the function app.')
param storageAccountName string = '{storage_account_name}'

@description('Name of the Application Insights instance.')
param applicationInsightsName string = '{module_name}-appi'

@description('Name of the hosting plan.')
param hostingPlanName string = '{module_name}-plan'

@description('Runtime for the Azure Function worker.')
param workerRuntime string = '{worker_runtime}'

@description('Linux stack for the Azure Function app.')
param linuxFxVersion string = '{linux_fx_version}'

@description('Optional tags applied to all resources.')
param tags object = {{}}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {{
  name: storageAccountName
  location: location
  sku: {{
    name: 'Standard_LRS'
  }}
  kind: 'StorageV2'
  tags: tags
  properties: {{
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }}
}}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {{
  name: applicationInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {{
    Application_Type: 'web'
    IngestionMode: 'ApplicationInsights'
  }}
}}

resource hostingPlan 'Microsoft.Web/serverfarms@2023-12-01' = {{
  name: hostingPlanName
  location: location
  sku: {{
    name: 'Y1'
    tier: 'Dynamic'
  }}
  kind: 'functionapp'
  tags: tags
  properties: {{
    reserved: true
  }}
}}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {{
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {{
    type: 'SystemAssigned'
  }}
  tags: tags
  properties: {{
    serverFarmId: hostingPlan.id
    httpsOnly: true
    siteConfig: {{
      linuxFxVersion: linuxFxVersion
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {{
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{listKeys(storageAccount.id, '2023-05-01').keys[0].value}};EndpointSuffix=${{environment().suffixes.storage}}'
        }}
        {{
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }}
        {{
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: workerRuntime
        }}
        {{
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: applicationInsights.properties.ConnectionString
        }}
      ]
    }}
  }}
}}

output functionAppName string = functionApp.name
output functionAppResourceId string = functionApp.id
"""


def build_main_bicepparam(
    module_name: str,
    owner: str,
    storage_account_name: str,
    worker_runtime: str,
    linux_fx_version: str,
) -> str:
    return f"""using './main.bicep'

param functionAppName = '{module_name}-func'
param storageAccountName = '{storage_account_name}'
param applicationInsightsName = '{module_name}-appi'
param hostingPlanName = '{module_name}-plan'
param workerRuntime = '{worker_runtime}'
param linuxFxVersion = '{linux_fx_version}'
param tags = {{
  service: '{module_name}'
  owner: '{owner}'
}}
"""

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

if language not in RUNTIME_SETTINGS:
    raise ValueError(f"Ukjent språk: {language}")

module_dir = Path("modules") / module_name
module_dir.mkdir(parents=True, exist_ok=True)
infra_dir = module_dir / "infra"
infra_dir.mkdir(exist_ok=True)

runtime = RUNTIME_SETTINGS[language]
storage_account_name = to_storage_account_name(module_name)

(module_dir / "README.md").write_text(
    build_readme(module_name, owner, language, description),
    encoding="utf-8",
)
(infra_dir / "main.bicep").write_text(
    build_main_bicep(
        module_name,
        storage_account_name,
        runtime["worker_runtime"],
        runtime["linux_fx_version"],
    ),
    encoding="utf-8",
)
(infra_dir / "main.bicepparam").write_text(
    build_main_bicepparam(
        module_name,
        owner,
        storage_account_name,
        runtime["worker_runtime"],
        runtime["linux_fx_version"],
    ),
    encoding="utf-8",
)

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
branch_name = f"new-request/issue-{ISSUE_NUMBER}-{module_name}"
Path(".generated_branch_name").write_text(branch_name, encoding="utf-8")
set_github_output("branch_name", branch_name)
set_github_output("module_name", module_name)
set_github_output("language", language)
set_github_output("owner", owner)
print(f"Generated scaffold for {module_name} in {module_dir}")
print(f"Branch name: {branch_name}")
