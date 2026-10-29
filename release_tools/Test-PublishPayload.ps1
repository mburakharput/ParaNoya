# Offline regression: execute only the two payload assignments, never the
# publisher, credentials, signing, or GitHub calls. Supports Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$errors = $null; $tokens = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'Publish-ParaNoya.ps1'), [ref]$tokens, [ref]$errors)
if ($errors) { throw ($errors | Out-String) }
$version = '1.2.5.6'; $tag = "ParaNoya-v$version"
foreach ($variable in @('notes', 'body')) {
    $statements = @($ast.FindAll({ param($node)
        $node -is [Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -ceq ('$' + $variable)
    }, $true))
    if ($statements.Count -ne 1) { throw "Expected one assignment: $variable" }
    Invoke-Expression $statements[0].Extent.Text
}
$decoded = $body | ConvertFrom-Json
$expected = [IO.File]::ReadAllText((Join-Path $project 'RELEASE-NOTES.md'), [Text.Encoding]::UTF8)
if ($decoded.body -isnot [string] -or $decoded.body -cne $expected) { throw 'Release body must be a plain JSON string' }
if ($decoded.tag_name -cne $tag -or $decoded.draft -isnot [bool] -or !$decoded.draft) { throw 'Release draft payload invalid' }
Write-Output 'Release payload regression: OK'
