# Windows built-in OCR (Windows.Media.Ocr) over every png in a folder -> "<name>`t<text>" lines
# usage: powershell -File ocr_win.ps1 <folder> [-out file.tsv] [-first N]     (-out writes UTF-8; without it the lines go to stdout)
param([string]$dir, [string]$out = "", [int]$first = 0)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $eng) { Write-Error "no Windows OCR language pack installed"; exit 2 }
$files = Get-ChildItem $dir -Filter *.png | Sort-Object Name
if ($first -gt 0) { $files = $files | Select-Object -First $first }
$lines = $files | % {
  $f = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($_.FullName)) ([Windows.Storage.StorageFile])
  $s = Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $d = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $b = Await ($d.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $r = Await ($eng.RecognizeAsync($b)) ([Windows.Media.Ocr.OcrResult])
  "$($_.BaseName)`t$($r.Text)"
  $s.Dispose()
}
if ($out) { $lines | Out-File -Encoding utf8 $out } else { $lines }
