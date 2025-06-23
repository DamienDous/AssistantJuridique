param (
	[string]$inputFolder = "C:\Users\damien_dous\dev\DB\cleaned_png_3000",
	[string]$outputFolder = "C:\Users\damien_dous\dev\DB\ocr_output",
	[int]$maxParallel = 8
)

$scriptPath = (Resolve-Path "./ocr_script.sh").Path
$allFiles = Get-ChildItem -Path $inputFolder -Filter *.png
Write-Host "📁 $($allFiles.Count) fichiers trouvés dans : $inputFolder" -ForegroundColor Cyan

$jobs = @()
foreach ($file in $allFiles) {
	$baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
	$finalPdf = Join-Path $outputFolder "${baseName}_final.pdf"

	if (Test-Path $finalPdf) {
		Write-Host "⏭️ Déjà traité : ${finalPdf}" -ForegroundColor DarkGray
		continue
	}

	Write-Host "🚀 Lancement OCR : $($file.Name)" -ForegroundColor Green

	$jobs += Start-Job -ScriptBlock {
		param($inFile, $inDir, $outDir, $script, $dockerImg)

		docker run --rm `
			-v "${inDir}:/data" `
			-v "${outDir}:/data/out" `
			-v "${script}:/script.sh" `
			-v "${PWD}/tools:/tools" `
			$dockerImg /script.sh "$(Split-Path -Leaf $inFile)"

	} -ArgumentList $file.FullName, $inputFolder, $outputFolder, $scriptPath, "ocrmypdf-local"

	while ($jobs.Count -ge $maxParallel) {
		$finished = $jobs | Wait-Job -Any
		$jobs = $jobs | Where-Object { $_.State -eq "Running" }
	}
}

# Attente finale
if ($jobs.Count -gt 0) {
	Write-Host "🕐 Attente de la fin des OCR en cours..." -ForegroundColor Cyan
	$jobs | Wait-Job | ForEach-Object { Receive-Job $_; Remove-Job $_ }
}

Write-Host "✅ Tous les fichiers ont été traités." -ForegroundColor Green
