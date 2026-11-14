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

$C = [System.Drawing.Color]
$navy = $C::FromArgb(31, 53, 80)
$navy2 = $C::FromArgb(45, 86, 130)
$ink = $C::FromArgb(31, 53, 80)
$muted = $C::FromArgb(94, 107, 115)
$headImg = $null
try {
    $imgPath = Join-Path $PSScriptRoot 'school.png'
    if (Test-Path -LiteralPath $imgPath) { $headImg = [System.Drawing.Image]::FromFile($imgPath) }
} catch { }
$subText = $(if ($school) { $school + '  —  Επιλέξτε εφαρμογή' } else { 'Επιλέξτε εφαρμογή' })

# Εικονίδιο .ico → εικόνα: τα .ico των εφαρμογών έχουν καρέ PNG, που το Icon.ToBitmap() δεν διαβάζει σωστά
# (κενό ή «θόρυβος»). Διαβάζουμε μόνοι μας το κατάλληλο καρέ.
function Get-IcoBitmap([string]$path, [int]$size) {
    try {
        if (-not (Test-Path -LiteralPath $path)) { return $null }
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $n = [BitConverter]::ToUInt16($bytes, 4)
        $pick = -1; $pickW = 0
        for ($i = 0; $i -lt $n; $i++) {
            $o = 6 + 16 * $i
            $w = [int]$bytes[$o]; if ($w -eq 0) { $w = 256 }
            if ($pick -lt 0 -or ($w -ge $size -and ($pickW -lt $size -or $w -lt $pickW)) -or ($pickW -lt $size -and $w -gt $pickW)) { $pick = $i; $pickW = $w }
        }
        if ($pick -lt 0) { return $null }
        $o = 6 + 16 * $pick
        $len = [BitConverter]::ToUInt32($bytes, $o + 8)
        $off = [BitConverter]::ToUInt32($bytes, $o + 12)
        if ($bytes[$off] -eq 0x89 -and $bytes[$off + 1] -eq 0x50) {
            $ms = New-Object System.IO.MemoryStream($bytes, [int]$off, [int]$len)
            $src = [System.Drawing.Image]::FromStream($ms)
        } else {
            $src = (New-Object System.Drawing.Icon($path, $pickW, $pickW)).ToBitmap()
        }
        $bmp = New-Object System.Drawing.Bitmap($size, $size)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($src, 0, 0, $size, $size)
        $g.Dispose()
        return $bmp
    } catch { return $null }
}

$C = @{
    navy1 = [System.Drawing.Color]::FromArgb(31, 53, 80)
    navy2 = [System.Drawing.Color]::FromArgb(45, 86, 130)
    bg    = [System.Drawing.Color]::FromArgb(244, 246, 249)
    ink   = [System.Drawing.Color]::FromArgb(31, 53, 80)
    muted = [System.Drawing.Color]::FromArgb(94, 107, 115)
    faint = [System.Drawing.Color]::FromArgb(138, 149, 155)
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Σχολικές Εφαρμογές'
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.ClientSize = New-Object System.Drawing.Size(640, 420)
$form.BackColor = $C.bg
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
if (Test-Path -LiteralPath $oroIco) { try { $form.Icon = New-Object System.Drawing.Icon($oroIco) } catch { } }

# ---- Επάνω ζώνη: διαβάθμιση, διακριτικοί κύκλοι, ζωγραφιά σχολείου ----
$header = New-Object System.Windows.Forms.Panel
$header.Location = New-Object System.Drawing.Point(0, 0)
$header.Size = New-Object System.Drawing.Size(640, 104)
$header.BackColor = $C.navy1
$header.Add_Paint({
    param($s, $e)
    $g = $e.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $r = $s.ClientRectangle
    $lg = New-Object System.Drawing.Drawing2D.LinearGradientBrush($r, $C.navy1, $C.navy2, [single]20)
    $g.FillRectangle($lg, $r); $lg.Dispose()
    $w = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(20, 255, 255, 255))
    $g.FillEllipse($w, $r.Width - 140, -70, 220, 220)
    $g.FillEllipse($w, $r.Width - 250, 40, 130, 130)
    $w.Dispose()
    # Σχολείο: κτίριο, στέγη, ρολόι, παράθυρα, πόρτα, γρασίδι
    $x = $r.Width - 112; $y = 26
    $wall = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(240, 196, 120))
    $roof = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(184, 64, 52))
    $win  = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(126, 192, 222))
    $door = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(150, 92, 60))
    $grass= New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(110, 170, 90))
    $white= New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $pen  = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(60, 60, 60), [single]1.5)
    $g.FillRectangle($wall, $x, $y + 22, 72, 40)
    $pts = [System.Drawing.PointF[]]@(
        (New-Object System.Drawing.PointF(($x - 4), ($y + 24))),
        (New-Object System.Drawing.PointF(($x + 36), ($y + 2))),
        (New-Object System.Drawing.PointF(($x + 76), ($y + 24))))
    $g.FillPolygon($roof, $pts)
    $g.FillEllipse($white, $x + 29, $y + 9, 14, 14)
    $g.DrawEllipse($pen, $x + 29, $y + 9, 14, 14)
    $g.DrawLine($pen, $x + 36, $y + 16, $x + 36, $y + 11)
    $g.DrawLine($pen, $x + 36, $y + 16, $x + 40, $y + 16)
    foreach ($wx in @(6, 52)) { $g.FillRectangle($win, $x + $wx, $y + 30, 14, 10); $g.FillRectangle($win, $x + $wx, $y + 45, 14, 10) }
    $g.FillRectangle($door, $x + 28, $y + 38, 16, 24)
    $g.FillEllipse($grass, $x - 10, $y + 56, 40, 14)
    $g.FillEllipse($grass, $x + 44, $y + 56, 40, 14)
    foreach ($b in @($wall, $roof, $win, $door, $grass, $white)) { $b.Dispose() }
    $pen.Dispose()
}.GetNewClosure())
$form.Controls.Add($header)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Σχολικές Εφαρμογές'
$title.Font = New-Object System.Drawing.Font('Segoe UI', 18, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::White
$title.BackColor = [System.Drawing.Color]::Transparent
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(26, 16)
$header.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = $(if ($school) { $school + '  —  Επιλέξτε εφαρμογή' } else { 'Επιλέξτε εφαρμογή' })
$sub.ForeColor = [System.Drawing.Color]::FromArgb(214, 224, 236)
$sub.BackColor = [System.Drawing.Color]::Transparent
$sub.AutoSize = $true
$sub.Location = New-Object System.Drawing.Point(29, 62)
$header.Controls.Add($sub)

# ---- Κάρτες εφαρμογών ----
function New-AppCard($x, $name, $desc, $icoPath, $installed, $accent, $tint, $onOpen) {
    $card = New-Object System.Windows.Forms.Panel
    $card.Location = New-Object System.Drawing.Point($x, 126)
    $card.Size = New-Object System.Drawing.Size(280, 222)
    $card.BackColor = [System.Drawing.Color]::White
    $card.Tag = @{ hover = $false; accent = $accent; ok = $installed }
    $card.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $t = $s.Tag
        $band = New-Object System.Drawing.SolidBrush($(if ($t.ok) { $t.accent } else { [System.Drawing.Color]::FromArgb(200, 205, 210) }))
        $g.FillRectangle($band, 0, 0, $s.Width, 8); $band.Dispose()
        $col = $(if ($t.hover) { $t.accent } else { [System.Drawing.Color]::FromArgb(226, 230, 235) })
        $pw = $(if ($t.hover) { 3 } else { 1 })
        $p = New-Object System.Drawing.Pen($col, [single]$pw)
        $p.Alignment = [System.Drawing.Drawing2D.PenAlignment]::Inset
        $g.DrawRectangle($p, 0, 0, $s.Width - 1, $s.Height - 1); $p.Dispose()
    })

    $pic = New-Object System.Windows.Forms.PictureBox
    $pic.Location = New-Object System.Drawing.Point(22, 30)
    $pic.Size = New-Object System.Drawing.Size(68, 68)
    $pic.BackColor = $tint
    $pic.SizeMode = 'CenterImage'
    $img = Get-IcoBitmap $icoPath 48
    if ($img) { $pic.Image = $img }
    elseif ($env:SCHOOLAPPS_LAUNCHER_SNAPSHOT -and (Test-Path -LiteralPath $icoPath)) { [Console]::Error.WriteLine('Δεν φορτώθηκε το εικονίδιο: ' + $icoPath) }
    $card.Controls.Add($pic)

    $ln = New-Object System.Windows.Forms.Label
    $ln.Text = $name
    $ln.Font = New-Object System.Drawing.Font('Segoe UI', 13, [System.Drawing.FontStyle]::Bold)
    $ln.ForeColor = $C.ink
    $ln.AutoSize = $true
    $ln.Location = New-Object System.Drawing.Point(20, 110)
    $card.Controls.Add($ln)

    $ld = New-Object System.Windows.Forms.Label
    $ld.Text = $desc
    $ld.ForeColor = $C.muted
    $ld.AutoSize = $false
    $ld.Size = New-Object System.Drawing.Size(240, 40)
    $ld.Location = New-Object System.Drawing.Point(22, 140)
    $card.Controls.Add($ld)

    $lo = New-Object System.Windows.Forms.Label
    $lo.Font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
    $lo.AutoSize = $true
    $lo.Location = New-Object System.Drawing.Point(22, 186)
    if ($installed) {
        $lo.Text = 'Άνοιγμα  →'
        $lo.ForeColor = $accent
    } else {
        $lo.Text = 'Δεν είναι εγκατεστημένο'
        $lo.ForeColor = $C.faint
    }
    $card.Controls.Add($lo)

    if ($installed) {
        $enter = { $card.Tag.hover = $true; $card.Invalidate() }.GetNewClosure()
        $leave = {
            $pt = $card.PointToClient([System.Windows.Forms.Cursor]::Position)
            if (-not $card.ClientRectangle.Contains($pt)) { $card.Tag.hover = $false; $card.Invalidate() }
        }.GetNewClosure()
        foreach ($c in @($card, $pic, $ln, $ld, $lo)) {
            $c.Cursor = [System.Windows.Forms.Cursors]::Hand
            $c.Add_MouseEnter($enter)
            $c.Add_MouseLeave($leave)
            $c.Add_Click($onOpen)
        }
    }
    return $card
}

$oroOk = Test-Path -LiteralPath $oroExe
$openOro = {
    Start-Process -FilePath $oroExe -ArgumentList @('-X', 'utf8', ('"' + (Join-Path $oroDir 'src\server.py') + '"')) -WorkingDirectory $oroDir
    $form.Close()
}
$form.Controls.Add((New-AppCard 28 'Ωρολόγιο Σχολείου' 'Πρόγραμμα · αναπληρώσεις · έντυπα για τη Διεύθυνση' $oroIco $oroOk ([System.Drawing.Color]::FromArgb(46, 125, 91)) ([System.Drawing.Color]::FromArgb(227, 242, 234)) $openOro))

$openEf = {
    Start-Process -FilePath $efExe -WorkingDirectory $efDir
    $form.Close()
}
$form.Controls.Add((New-AppCard 332 'Εφημερίες Εκπαιδευτικών' 'Εφημερίες · απουσίες · αντικαταστάτες' $efIco ($null -ne $efExe) ([System.Drawing.Color]::FromArgb(217, 138, 28)) ([System.Drawing.Color]::FromArgb(251, 239, 220)) $openEf))

$hint = New-Object System.Windows.Forms.Label
$hint.Text = 'Ιδέα και σχεδιασμός: Σταμάτης Κοκολόγος, εκπαιδευτικός ΠΕ70, 22ο Δημοτικό Σχολείο Λαμίας'
$hint.ForeColor = $C.faint
$hint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
$hint.AutoSize = $true
$hint.Location = New-Object System.Drawing.Point(28, 372)
$form.Controls.Add($hint)

# Έλεγχος στο CI: αποθήκευση εικόνας του παραθύρου και κλείσιμο
if ($env:SCHOOLAPPS_LAUNCHER_SNAPSHOT) {
    $form.Add_Shown({
        $form.Refresh()
        [System.Windows.Forms.Application]::DoEvents()
        $bmp = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
        $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $bmp.Save($env:SCHOOLAPPS_LAUNCHER_SNAPSHOT, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        $form.Close()
    })
}

[void]$form.ShowDialog()
