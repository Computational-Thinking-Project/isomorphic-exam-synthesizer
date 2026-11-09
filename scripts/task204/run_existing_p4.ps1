param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$evidence=(Resolve-Path -LiteralPath $EvidenceDirectory).Path
& docker run --rm --network container:supabase_kong_task204-supabase-local `
  --mount "type=bind,source=$repo,target=/repo,readonly" `
  --mount "type=bind,source=$evidence,target=/evidence" `
  --entrypoint python exam-tv1-local-backend /repo/scripts/task204/check_local_auth.py `
  /evidence/status.private.local.json /evidence/auth-result.json --api-url http://127.0.0.1:8000
if($LASTEXITCODE -ne 0){throw 'P4 API checks failed'}
& node (Join-Path $PSScriptRoot 'browser-p4.mjs') $evidence
if($LASTEXITCODE -ne 0){throw 'P4 browser checks failed'}
