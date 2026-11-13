# Σχολικές Εφαρμογές: μικρό παράθυρο επιλογής (Ωρολόγιο Σχολείου / Εφημερίες Εκπαιδευτικών).
# Εγκαθίσταται από το Setup της σουίτας· δεν αλλάζει τίποτα στις εφαρμογές.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$la = $env:LOCALAPPDATA
$oroDir = Join-Path $la 'Programs\OrologioDimotikou'
$oroExe = Join-Path $oroDir 'runtime\pythonw.exe'
$oroIco = Join-Path $oroDir 'src\app.ico'
$efDir = Join-Path $la 'Programs\EfimeriesEkpaideftikon'
$efExe = $null
foreach ($n in @('EfimeriesPortable_x64.exe', 'EfimeriesPortable_x86.exe')) {
    $p = Join-Path $efDir $n
    if (Test-Path -LiteralPath $p) { $efExe = $p; break }
}
$efIco = Join-Path $efDir 'app_icon.ico'

# Όνομα σχολείου από το στιγμιότυπο του Ωρολογίου (αν υπάρχει)
$school = ''
try {
    $cfgPath = Join-Path $env:APPDATA 'SchoolApps\suite.json'
    $common = Join-Path $env:APPDATA 'SchoolApps\Κοινά'
    if (Test-Path -LiteralPath $cfgPath) {
        $cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.root) { $common = Join-Path $cfg.root 'Κοινά' }
    }
    $snapPath = Join-Path $common 'orologio.json'
    if (Test-Path -LiteralPath $snapPath) {
        $snap = Get-Content -LiteralPath $snapPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $school = [string]$snap.school
        if ($snap.year) { $school = $school + ' · ' + [string]$snap.year }
    }
} catch { }

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Σχολικές Εφαρμογές'
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.ClientSize = New-Object System.Drawing.Size(580, 340)
$form.BackColor = [System.Drawing.Color]::FromArgb(244, 246, 249)
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
if (Test-Path -LiteralPath $oroIco) { try { $form.Icon = New-Object System.Drawing.Icon($oroIco) } catch { } }

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Σχολικές Εφαρμογές'
$title.Font = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(24, 16)
$form.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = $(if ($school) { $school } else { 'Επιλέξτε εφαρμογή' })
$sub.ForeColor = [System.Drawing.Color]::FromArgb(94, 107, 115)
$sub.AutoSize = $true
$sub.Location = New-Object System.Drawing.Point(26, 52)
$form.Controls.Add($sub)

function New-AppButton($x, $text, $icoPath, $installed, $accent) {
    $b = New-Object System.Windows.Forms.Button
    $b.Location = New-Object System.Drawing.Point($x, 88)
    $b.Size = New-Object System.Drawing.Size(255, 210)
    $b.FlatStyle = 'Flat'
    $b.FlatAppearance.BorderSize = 2
    $b.FlatAppearance.BorderColor = $accent
    $b.BackColor = [System.Drawing.Color]::White
    $b.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
    $b.TextImageRelation = 'ImageAboveText'
    $b.Cursor = [System.Windows.Forms.Cursors]::Hand
    if ($installed) {
        $b.Text = $text
        if (Test-Path -LiteralPath $icoPath) {
            try { $b.Image = (New-Object System.Drawing.Icon($icoPath, 96, 96)).ToBitmap() } catch { }
        }
    } else {
        $b.Text = $text + "`r`n(δεν είναι εγκατεστημένο)"
        $b.Enabled = $false
    }
    return $b
}

$oroOk = Test-Path -LiteralPath $oroExe
$bOro = New-AppButton 24 "Ωρολόγιο Σχολείου`r`nπρόγραμμα · αναπληρώσεις" $oroIco $oroOk ([System.Drawing.Color]::FromArgb(36, 67, 60))
$bOro.Add_Click({
    Start-Process -FilePath $oroExe -ArgumentList @('-X', 'utf8', ('"' + (Join-Path $oroDir 'src\server.py') + '"')) -WorkingDirectory $oroDir
    $form.Close()
})
$form.Controls.Add($bOro)

$bEf = New-AppButton 301 "Εφημερίες Εκπαιδευτικών`r`nεφημερίες · απουσίες" $efIco ($null -ne $efExe) ([System.Drawing.Color]::FromArgb(37, 99, 235))
$bEf.Add_Click({
    Start-Process -FilePath $efExe -WorkingDirectory $efDir
    $form.Close()
})
$form.Controls.Add($bEf)

$hint = New-Object System.Windows.Forms.Label
$hint.Text = 'Ιδέα και σχεδιασμός: Σταμάτης Κοκολόγος, εκπαιδευτικός ΠΕ70, 22ο Δημοτικό Σχολείο Λαμίας'
$hint.ForeColor = [System.Drawing.Color]::FromArgb(138, 149, 155)
$hint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
$hint.AutoSize = $true
$hint.Location = New-Object System.Drawing.Point(26, 310)
$form.Controls.Add($hint)

[void]$form.ShowDialog()
