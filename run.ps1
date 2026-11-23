# Start the chosen vector database, then run the solution in Docker on it. Windows PowerShell and pwsh.
#
#   .\run.ps1 --backend weaviate compare
#   .\run.ps1 --backend pgvector compare
#   .\run.ps1 --backend pgvector ask "What is the penalty in month 20?" --strategy markdown
#
# Without --backend, weaviate is used. Every argument is passed to run.py unchanged.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$backend = "weaviate"
$passThrough = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "--backend" -and ($i + 1) -lt $args.Count) {
        $backend = $args[$i + 1]
        $passThrough += $args[$i]
        $passThrough += $args[$i + 1]
        $i++
    } elseif ($args[$i] -like "--backend=*") {
        $backend = $args[$i].Substring(10)
        $passThrough += $args[$i]
    } else {
        $passThrough += $args[$i]
    }
}

switch ($backend) {
    "weaviate" { $service = "weaviate" }
    "pgvector" { $service = "postgres" }
    default    { Write-Error "Unknown backend '$backend'. Use weaviate or pgvector."; exit 2 }
}

if ($passThrough.Count -eq 0) {
    Write-Error "Give a command, for example: .\run.ps1 --backend $backend compare"
    exit 2
}

docker compose --profile $backend up -d --wait $service
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose run --rm --build -e "VECTOR_BACKEND=$backend" app python run.py @passThrough
exit $LASTEXITCODE
