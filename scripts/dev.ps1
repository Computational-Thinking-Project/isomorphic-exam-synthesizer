# Windows PowerShell 5.1+ / PowerShell 7 on Windows, Linux and macOS.
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'doctor', 'up', 'test', 'smoke', 'logs', 'down')]
    [string]$Action = 'up',
    [switch]$NoWatch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot '.env'

function Find-Docker {
    $command = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    # Existing terminals may still have the PATH from before Desktop was installed.
    $localApps = [Environment]::GetFolderPath('LocalApplicationData')
    foreach ($candidate in @(
        (Join-Path $localApps 'Programs/DockerDesktop/resources/bin/docker.exe'),
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'Docker CLI not found. Install Docker Desktop and reopen your terminal.'
}

function Invoke-Compose {
    param([string[]]$DockerArguments)
    & $script:DockerCli @script:ComposeOptions @DockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed (exit $LASTEXITCODE). Try: ./scripts/dev.ps1 logs"
    }
}

function Assert-Engine {
    # Bound the probe: a crashed Desktop must not leave onboarding hanging.
    $probe = New-Object System.Diagnostics.Process
    $probe.StartInfo.FileName = $script:DockerCli
    $probe.StartInfo.Arguments = 'info --format {{.OSType}}'
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    try {
        $null = $probe.Start()
        $outputTask = $probe.StandardOutput.ReadToEndAsync()
        $errorTask = $probe.StandardError.ReadToEndAsync()
        if (-not $probe.WaitForExit(20000)) {
            $probe.Kill()
            throw 'Docker Engine did not respond in 20 seconds. Open/restart Docker Desktop.'
        }
        if ($probe.ExitCode -ne 0) {
            throw 'Docker Engine is unavailable. Open Docker Desktop and wait until it is running.'
        }
        if ($outputTask.Result.Trim() -ne 'linux') {
            throw 'Switch Docker Desktop to Linux containers (WSL 2 on Windows).'
        }
        $null = $errorTask.Result
    }
    finally { $probe.Dispose() }
}

function Get-ServiceUri {
    param([string]$Service, [int]$Port)
    $address = & $script:DockerCli @script:ComposeOptions port $Service $Port
    if ($LASTEXITCODE -ne 0 -or -not $address) {
        throw "Service $Service is not running. Run ./scripts/dev.ps1 up first."
    }
    return 'http://' + ([string]$address).Trim()
}

function Test-Stack {
    $backend = Get-ServiceUri -Service backend -Port 8000
    $frontend = Get-ServiceUri -Service frontend -Port 3000
    $health = Invoke-RestMethod -Uri "$backend/health" -TimeoutSec 15
    if ($health.status -ne 'healthy') { throw 'Backend health check failed.' }
    $page = Invoke-WebRequest -Uri "$frontend/" -UseBasicParsing -TimeoutSec 15
    if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<html') {
        throw 'Frontend HTTP check failed.'
    }
    $proxy = Invoke-RestMethod -Uri "$frontend/api/health/metrics" -TimeoutSec 15
    if ($proxy.status -ne 'operational') { throw 'Frontend-to-backend proxy check failed.' }
    Write-Host 'PASS: backend health, frontend HTTP, and frontend API proxy.'
}

Push-Location $repoRoot
try {
    $script:DockerCli = Find-Docker
    # Credential helpers must be discoverable after an in-place Desktop upgrade.
    $env:PATH = (Split-Path -Parent $script:DockerCli) + [IO.Path]::PathSeparator + $env:PATH
    $composeVersion = & $script:DockerCli compose version --short
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is missing. Update Docker Desktop.' }
    $versionMatch = [regex]::Match([string]$composeVersion, '\d+\.\d+\.\d+')
    if (-not $versionMatch.Success -or [version]$versionMatch.Value -lt [version]'2.32.0') {
        throw 'Docker Compose 2.32.0 or later is required for initial_sync and the dev overlay.'
    }
    $script:ComposeOptions = @(
        'compose', '--project-directory', $repoRoot,
        '--env-file', $envFile,
        '-f', (Join-Path $repoRoot 'docker-compose.yml'),
        '-f', (Join-Path $repoRoot 'docker-compose.dev.yml')
    )

    if ($Action -eq 'setup') {
        if (-not (Test-Path -LiteralPath $envFile)) {
            Copy-Item -LiteralPath (Join-Path $repoRoot '.env.example') -Destination $envFile
            Write-Host 'Created .env. Local health/UI/mock tests do not require cloud keys.'
        }
        else { Write-Host 'Keeping your existing .env unchanged.' }
        Invoke-Compose -DockerArguments @('config', '--quiet')
        Write-Host 'Setup valid. Fill cloud credentials only when testing real Gemini/Supabase.'
        Write-Host 'Next: ./scripts/dev.ps1 doctor; ./scripts/dev.ps1 up'
    }
    else {
        if (-not (Test-Path -LiteralPath $envFile)) {
            throw 'Missing .env. Run ./scripts/dev.ps1 setup first.'
        }
        Invoke-Compose -DockerArguments @('config', '--quiet')
        Assert-Engine
        switch ($Action) {
            'doctor' { Write-Host "PASS: Linux Docker Engine, Compose $composeVersion, and configuration." }
            'up' {
                Invoke-Compose -DockerArguments @('up', '--build', '--detach', '--wait', '--wait-timeout', '120')
                Test-Stack
                $frontend = Get-ServiceUri -Service frontend -Port 3000
                $backend = Get-ServiceUri -Service backend -Port 8000
                Write-Host "Frontend: $frontend   API docs: $backend/docs"
                if (-not $NoWatch) {
                    Write-Host 'Watching source changes. Ctrl+C stops watching; use down to stop containers.'
                    Invoke-Compose -DockerArguments @('watch', '--no-up')
                }
            }
            'test' {
                Invoke-Compose -DockerArguments @('run', '--build', '--rm', '--no-deps', 'backend', 'python', '-m', 'pytest', 'tests', '-q')
                Invoke-Compose -DockerArguments @('run', '--rm', '--no-deps', 'backend', 'python', '-c', "from sympy.parsing.latex import parse_latex; assert str(parse_latex('x^2+1')) == 'x**2 + 1'; print('PASS: SymPy LaTeX parser')")
                Invoke-Compose -DockerArguments @('run', '--build', '--rm', '--no-deps', 'frontend', 'sh', '-c', 'npm run test && npm run lint && npm run build')
            }
            'smoke' { Test-Stack }
            'logs' { Invoke-Compose -DockerArguments @('logs', '--tail', '100') }
            'down' { Invoke-Compose -DockerArguments @('down', '--remove-orphans') }
        }
    }
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
finally { Pop-Location }
