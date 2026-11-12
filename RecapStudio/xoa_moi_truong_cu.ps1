# Xoa TAT CA moi truong cu cua Movie Recap AI / Recap Studio tren o C va o D.
# - Tim: thu muc cai app (co main.py), ban giai nen zip, file zip, VSR, du lieu AppData, model Whisper/AI, cache pip.
# - KHONG xoa video da xuat (Videos\MovieRecapAI, Videos\RecapStudio).
# - Liet ke + dung luong truoc, chi xoa khi ban go Y.
# Chay: chuot phai file -> "Run with PowerShell"
#   hoac: powershell -ExecutionPolicy Bypass -File .\xoa_moi_truong_cu.ps1
#   hoac khong can tai file (dan vao PowerShell):
#   irm https://raw.githubusercontent.com/tientran90td-commits/vtgt-cap-nhat/claude/movie-summary-app-0q90dq/RecapStudio/xoa_moi_truong_cu.ps1 | iex
& {

    $ErrorActionPreference = 'SilentlyContinue'
    Set-Location $env:USERPROFILE

    $Drives = @('C:\', 'D:\') | Where-Object { Test-Path $_ }
    $SkipTop = @('Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', '$Recycle.Bin',
                 'System Volume Information', 'Recovery', 'PerfLogs')
    $Videos = Join-Path $env:USERPROFILE 'Videos'
    $NamePat = '^(MovieRecapAI|RecapStudio|Recap Studio|vtgt-cap-nhat|video-subtitle-remover|vsr[_-])'

    $items = New-Object System.Collections.ArrayList
    function Add-Cand($path, $why) {
        if (-not $path -or -not (Test-Path -LiteralPath $path)) { return }
        $full = (Resolve-Path -LiteralPath $path).ProviderPath.TrimEnd('\')
        $low = $full.ToLower()
        if ($low.StartsWith($Videos.ToLower())) { return }          # khong dung vao video
        foreach ($x in $items) {                                     # bo trung / bo thu muc con cua muc da co
            $xl = $x.Path.ToLower()
            if ($low -eq $xl -or $low.StartsWith($xl + '\')) { return }
        }
        for ($i = $items.Count - 1; $i -ge 0; $i--) {                # muc moi chua muc cu -> bo muc cu
            if ($items[$i].Path.ToLower().StartsWith($low + '\')) { $items.RemoveAt($i) }
        }
        [void]$items.Add([pscustomobject]@{ Path = $full; Why = $why; GB = 0.0 })
    }

    function Is-AppDir($d) {
        # thu muc app that su: co main.py va thu muc ma nguon cua app
        $app = (Test-Path -LiteralPath (Join-Path $d 'main.py')) -and (
            (Test-Path -LiteralPath (Join-Path $d 'recap')) -or (Test-Path -LiteralPath (Join-Path $d 'recapstudio')))
        $vsr = Test-Path -LiteralPath (Join-Path $d 'backend\main.py')     # video-subtitle-remover tai tay
        return ($app -or $vsr)
    }

    Write-Host "Dang tim tren o: $($Drives -join ', ') ... (co the mat vai phut)" -ForegroundColor Cyan

    # 1) Thu muc cai app, ban giai nen, VSR tai tay - tim sau toi 6 cap thu muc
    foreach ($drv in $Drives) {
        $tops = Get-ChildItem -LiteralPath $drv -Directory -Force | Where-Object { $SkipTop -notcontains $_.Name }
        foreach ($t in $tops) {
            $cands = @($t) + @(Get-ChildItem -LiteralPath $t.FullName -Recurse -Depth 6 -Force `
                                 -Attributes 'Directory+!ReparsePoint')
            foreach ($d in $cands) {
                if ($d.Name -notmatch $NamePat) { continue }
                $dl = $d.FullName.ToLower()
                if ($dl.StartsWith($env:APPDATA.ToLower()) -or $dl.StartsWith($env:LOCALAPPDATA.ToLower())) { continue }
                $hasApp = (Is-AppDir $d.FullName) -or
                          (@(Get-ChildItem -LiteralPath $d.FullName -Directory -Force | Where-Object { Is-AppDir $_.FullName }).Count -gt 0)
                if ($hasApp) { Add-Cand $d.FullName 'Thu muc app / ban giai nen (gom ca .venv)' }
            }
            # file zip cac phien ban cu
            # (giu lai RecapStudio-2.0.0.zip de cai lai)
            Get-ChildItem -LiteralPath $t.FullName -File -Recurse -Depth 4 -Force |
                Where-Object { ($_.Extension -eq '.zip' -or $_.Extension -eq '.7z') -and
                               $_.Name -match '^(MovieRecapAI|RecapStudio|video-subtitle-remover|vsr)' -and
                               $_.Name -notmatch '2\.0\.0' } |
                ForEach-Object { Add-Cand $_.FullName 'File nen phien ban cu' }
        }
    }

    # 2) Du lieu, model, cache da biet vi tri
    Add-Cand (Join-Path $env:APPDATA 'MovieRecapAI')        'Du lieu app cu: cai dat, model VSR/Whisper, ffmpeg, du an'
    Add-Cand (Join-Path $env:APPDATA 'RecapStudio')         'Du lieu Recap Studio: cai dat, du an, Whisper GPU, Piper'
    Add-Cand (Join-Path $env:USERPROFILE '.recapstudio')    'Du lieu Recap Studio (kieu cu)'
    Add-Cand (Join-Path $env:USERPROFILE '.cache\huggingface') 'Model Whisper / giong AI da tai (Hugging Face)'
    Add-Cand (Join-Path $env:LOCALAPPDATA 'pip\cache')      'Bo nho tam cai thu vien Python'
    Add-Cand (Join-Path $env:USERPROFILE '.ollama\models')  'Model AI cua Ollama (qwen2.5... vai GB)'

    if ($items.Count -eq 0) {
        Write-Host "Khong tim thay moi truong cu nao." -ForegroundColor Green
        Read-Host "Enter de thoat" | Out-Null
        return
    }

    Write-Host "Dang tinh dung luong..." -ForegroundColor Cyan
    foreach ($x in $items) {
        $sum = (Get-ChildItem -LiteralPath $x.Path -Recurse -File -Force | Measure-Object Length -Sum).Sum
        if (-not $sum -and (Test-Path -LiteralPath $x.Path -PathType Leaf)) { $sum = (Get-Item -LiteralPath $x.Path).Length }
        $x.GB = [math]::Round(($sum / 1GB), 2)
    }

    Write-Host ""
    Write-Host "=========== SE XOA CAC MUC SAU ===========" -ForegroundColor Yellow
    $i = 0
    foreach ($x in $items) {
        $i++
        Write-Host ("[{0,2}] {1,7} GB  {2}" -f $i, $x.GB, $x.Path) -ForegroundColor White
        Write-Host ("            {0}" -f $x.Why) -ForegroundColor DarkGray
    }
    $total = ($items | Measure-Object GB -Sum).Sum
    Write-Host ("Tong: {0} GB.  Video da xuat trong {1} KHONG bi xoa." -f [math]::Round($total, 2), $Videos) -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Go Y  = xoa TAT CA cac muc tren"
    Write-Host "Go so cac muc muon GIU lai (vd: 3,7) roi Enter = xoa phan con lai"
    Write-Host "Enter trong = huy, khong xoa gi"
    $ans = (Read-Host "Lua chon").Trim()
    if (-not $ans) { Write-Host "Da huy." ; Read-Host "Enter de thoat" | Out-Null; return }

    $keep = @()
    if ($ans -notmatch '^[Yy]$') {
        $keep = $ans -split '[,; ]+' | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }
        if ($keep.Count -eq 0) { Write-Host "Khong hieu lua chon - da huy."; Read-Host "Enter de thoat" | Out-Null; return }
    }
    $todo = @()
    for ($k = 0; $k -lt $items.Count; $k++) { if ($keep -notcontains ($k + 1)) { $todo += $items[$k] } }

    # tat app / Ollama dang chay tu cac thu muc se xoa
    $paths = $todo | ForEach-Object { $_.Path }
    Get-Process | Where-Object { $_.Path } | ForEach-Object {
        $p = $_
        foreach ($t in $paths) { if ($p.Path -like "$t*") { Stop-Process -Id $p.Id -Force; break } }
    }
    if ($paths | Where-Object { $_ -like '*\.ollama\models' }) { Get-Process ollama* | Stop-Process -Force }
    Start-Sleep -Seconds 1

    $freed = 0.0
    foreach ($x in $todo) {
        Write-Host "Xoa $($x.Path) ..." -NoNewline
        Remove-Item -LiteralPath $x.Path -Recurse -Force
        if (Test-Path -LiteralPath $x.Path) {      # duong dan qua dai / file bi khoa -> thu cach khac
            if (Test-Path -LiteralPath $x.Path -PathType Container) {
                cmd /c "rd /s /q `"\\?\$($x.Path)`"" 2>$null
            }
        }
        if (Test-Path -LiteralPath $x.Path) {
            Write-Host " CHUA XOA HET (file dang mo - khoi dong lai may roi chay lai)" -ForegroundColor Red
        } else {
            Write-Host " xong" -ForegroundColor Green
            $freed += $x.GB
        }
    }
    Write-Host ""
    Write-Host ("Da giai phong khoang {0} GB." -f [math]::Round($freed, 2)) -ForegroundColor Green
    Write-Host "Cai lai: giai nen RecapStudio-2.0.0.zip -> install.bat -> run.bat" -ForegroundColor Cyan
    Write-Host "Go han Ollama / Python: Settings > Apps > (Ollama / Python) > Uninstall" -ForegroundColor Cyan
    Read-Host "Enter de thoat" | Out-Null
}
