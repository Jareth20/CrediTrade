param(
    [ValidateSet("production", "preview", "development")]
    [string[]]$Environments = @("production", "preview")
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    throw "No existe .env. Ejecuta configurar_local.cmd o restaura el archivo privado incluido."
}

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "No se encontró npx. Instala Node.js LTS antes de configurar Vercel."
}

function Read-DotEnv {
    param([string]$Path)
    $result = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -le 0) {
            continue
        }
        $name = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$name] = $value
    }
    return $result
}

function Set-VercelVariable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Environment
    )

    $tempFile = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tempFile, $Value, [System.Text.UTF8Encoding]::new($false))
        $quotedTemp = '"' + $tempFile + '"'

        cmd.exe /d /s /c "npx vercel env update $Name $Environment < $quotedTemp" | Out-Host
        if ($LASTEXITCODE -ne 0) {
            cmd.exe /d /s /c "npx vercel env add $Name $Environment < $quotedTemp" | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw "No se pudo crear o actualizar $Name en $Environment."
            }
        }
    }
    finally {
        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
    }
}

$local = Read-DotEnv ".env"
$requiredLocal = @(
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "DATABASE_URL_UNPOOLED",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_TIMEOUT_MS"
)

foreach ($name in $requiredLocal) {
    if (-not $local.ContainsKey($name) -or [string]::IsNullOrWhiteSpace($local[$name])) {
        throw "Falta $name en .env."
    }
}

Write-Host "Vinculando la carpeta con un proyecto de Vercel..." -ForegroundColor Cyan
npx vercel link
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo vincular el proyecto con Vercel."
}

$productionValues = [ordered]@{
    "DJANGO_SECRET_KEY"              = $local["DJANGO_SECRET_KEY"]
    "DJANGO_DEBUG"                   = "False"
    "DJANGO_ALLOWED_HOSTS"           = ".vercel.app"
    "CSRF_TRUSTED_ORIGINS"           = "https://*.vercel.app"
    "DATABASE_URL"                   = $local["DATABASE_URL"]
    "DATABASE_URL_UNPOOLED"          = $local["DATABASE_URL_UNPOOLED"]
    "DJANGO_USE_UNPOOLED"            = "False"
    "GEMINI_API_KEY"                 = $local["GEMINI_API_KEY"]
    "GEMINI_MODEL"                   = $local["GEMINI_MODEL"]
    "GEMINI_TIMEOUT_MS"              = $local["GEMINI_TIMEOUT_MS"]
    "SECURE_SSL_REDIRECT"            = "True"
    "SECURE_HSTS_SECONDS"             = "3600"
    "SECURE_HSTS_INCLUDE_SUBDOMAINS" = "False"
    "SECURE_HSTS_PRELOAD"            = "False"
}

foreach ($environment in $Environments) {
    Write-Host "Configurando variables en $environment..." -ForegroundColor Cyan
    foreach ($entry in $productionValues.GetEnumerator()) {
        Set-VercelVariable -Name $entry.Key -Value $entry.Value -Environment $environment
    }
}

Write-Host "" 
Write-Host "Variables configuradas sin guardar secretos en el repositorio." -ForegroundColor Green
Write-Host "Después del primer despliegue, agrega o actualiza PUBLIC_BASE_URL con el dominio final." -ForegroundColor Yellow
Write-Host "Para desplegar producción: npx vercel --prod" -ForegroundColor Yellow
