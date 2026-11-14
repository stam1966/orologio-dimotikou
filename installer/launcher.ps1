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

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Σχολικές Εφαρμογές'
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.ClientSize = New-Object System.Drawing.Size(640, 392)
$form.BackColor = $C::FromArgb(244, 246, 249)
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
if (Test-Path -LiteralPath $oroIco) { try { $form.Icon = New-Object System.Drawing.Icon($oroIco) } catch { } }

# Επάνω ζώνη: διαβάθμιση μπλε, διακριτικοί κύκλοι, εικόνα σχολείου, τίτλος
$hdr = New-Object System.Windows.Forms.Panel
$hdr.Dock = 'Top'
$hdr.Height = 104
$hdr.Add_Paint({
    param($s, $e)
    $g = $e.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $r = $s.ClientRectangle
    $br = New-Object System.Drawing.Drawing2D.LinearGradientBrush($r, $navy, $navy2, [single]20)
    $g.FillRectangle($br, $r)
    $br.Dispose()
    $c1 = New-Object System.Drawing.SolidBrush($C::FromArgb(20, 255, 255, 255))
    $g.FillEllipse($c1, $r.Width - 170, -70, 220, 220)
    $g.FillEllipse($c1, $r.Width - 260, 40, 130, 130)
    $c1.Dispose()
    if ($headImg) { $g.DrawImage($headImg, $r.Width - 132, 8, 110, 88) }
    $f1 = New-Object System.Drawing.Font('Segoe UI', 18, [System.Drawing.FontStyle]::Bold)
    $f2 = New-Object System.Drawing.Font('Segoe UI', 10)
    [System.Windows.Forms.TextRenderer]::DrawText($g, 'Σχολικές Εφαρμογές', $f1, (New-Object System.Drawing.Point(24, 16)), $C::White)
    [System.Windows.Forms.TextRenderer]::DrawText($g, $subText, $f2, (New-Object System.Drawing.Point(28, 62)), $C::FromArgb(214, 225, 238))
    $f1.Dispose(); $f2.Dispose()
})
$form.Controls.Add($hdr)

# Κάρτα εφαρμογής: λωρίδα χρώματος επάνω, εικονίδιο σε χρωματιστό τετράγωνο, τίτλος, περιγραφή, «Άνοιγμα →»
function New-AppCard($x, $title, $desc, $icoPath, $installed, $accent, $tint, $onClick) {
    $p = New-Object System.Windows.Forms.Panel
    $p.Location = New-Object System.Drawing.Point($x, 124)
    $p.Size = New-Object System.Drawing.Size(278, 214)
    $p.BackColor = $C::White
    if (-not $installed) { $accent = $C::FromArgb(170, 178, 184); $tint = $C::FromArgb(236, 239, 241) }
    $p.Tag = @{ hover = $false; accent = $accent; tint = $tint; click = $onClick; ok = $installed }
    $p.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $t = $s.Tag
        $w = $s.ClientSize.Width; $h = $s.ClientSize.Height
        $b = New-Object System.Drawing.SolidBrush($t.accent)
        $g.FillRectangle($b, 0, 0, $w, 8)
        $b.Dispose()
        $b = New-Object System.Drawing.SolidBrush($t.tint)
        $g.FillRectangle($b, 20, 26, 72, 72)
        $b.Dispose()
        if ($t.hover) { $pen = New-Object System.Drawing.Pen($t.accent, 3); $g.DrawRectangle($pen, 1, 1, $w - 3, $h - 3) }
        else { $pen = New-Object System.Drawing.Pen($C::FromArgb(222, 227, 232), 1); $g.DrawRectangle($pen, 0, 0, $w - 1, $h - 1) }
        $pen.Dispose()
    })

    $pb = New-Object System.Windows.Forms.PictureBox
    $pb.Location = New-Object System.Drawing.Point(24, 30)
    $pb.Size = New-Object System.Drawing.Size(64, 64)
    $pb.SizeMode = 'Zoom'
    $pb.BackColor = $tint
    if (Test-Path -LiteralPath $icoPath) { try { $pb.Image = (New-Object System.Drawing.Icon($icoPath, 64, 64)).ToBitmap() } catch { } }
    $p.Controls.Add($pb)

    $lt = New-Object System.Windows.Forms.Label
    $lt.Text = $title
    $lt.Font = New-Object System.Drawing.Font('Segoe UI', 13, [System.Drawing.FontStyle]::Bold)
    $lt.ForeColor = $ink
    $lt.AutoSize = $true
    $lt.Location = New-Object System.Drawing.Point(18, 108)
    $p.Controls.Add($lt)

    $ld = New-Object System.Windows.Forms.Label
    $ld.Text = $(if ($installed) { $desc } else { 'Δεν είναι εγκατεστημένη — ξανατρέξτε το Setup «Σχολικές Εφαρμογές»' })
    $ld.ForeColor = $muted
    $ld.AutoSize = $true
    $ld.MaximumSize = New-Object System.Drawing.Size(244, 0)
    $ld.Location = New-Object System.Drawing.Point(20, 140)
    $p.Controls.Add($ld)

    if ($installed) {
        $lo = New-Object System.Windows.Forms.Label
        $lo.Text = 'Άνοιγμα →'
        $lo.Font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
        $lo.ForeColor = $accent
        $lo.AutoSize = $true
        $lo.Location = New-Object System.Drawing.Point(20, 178)
        $p.Controls.Add($lo)

        $all = @($p) + @($p.Controls)
        foreach ($c in $all) {
            $c.Cursor = [System.Windows.Forms.Cursors]::Hand
            $c.Add_MouseEnter({
                $q = $this; if ($q -isnot [System.Windows.Forms.Panel]) { $q = $q.Parent }
                if (-not $q.Tag.hover) { $q.Tag.hover = $true; $q.Invalidate() }
            })
            $c.Add_MouseLeave({
                $q = $this; if ($q -isnot [System.Windows.Forms.Panel]) { $q = $q.Parent }
                $pt = $q.PointToClient([System.Windows.Forms.Cursor]::Position)
                if (-not $q.ClientRectangle.Contains($pt)) { $q.Tag.hover = $false; $q.Invalidate() }
            })
            $c.Add_Click({
                $q = $this; if ($q -isnot [System.Windows.Forms.Panel]) { $q = $q.Parent }
                & $q.Tag.click
            })
        }
    }
    return $p
}

$oroOk = Test-Path -LiteralPath $oroExe
$cOro = New-AppCard 28 'Ωρολόγιο Σχολείου' 'Πρόγραμμα · αναπληρώσεις · έντυπα' $oroIco $oroOk ($C::FromArgb(46, 125, 91)) ($C::FromArgb(227, 242, 234)) {
    Start-Process -FilePath $oroExe -ArgumentList @('-X', 'utf8', ('"' + (Join-Path $oroDir 'src\server.py') + '"')) -WorkingDirectory $oroDir
    $form.Close()
}
$form.Controls.Add($cOro)

$cEf = New-AppCard 334 'Εφημερίες Εκπαιδευτικών' 'Εφημερίες · απουσίες · αντικαταστάτες' $efIco ($null -ne $efExe) ($C::FromArgb(217, 138, 28)) ($C::FromArgb(251, 239, 220)) {
    Start-Process -FilePath $efExe -WorkingDirectory $efDir
    $form.Close()
}
$form.Controls.Add($cEf)

$hint = New-Object System.Windows.Forms.Label
$hint.Text = 'Ιδέα και σχεδιασμός: Σταμάτης Κοκολόγος, εκπαιδευτικός ΠΕ70, 22ο Δημοτικό Σχολείο Λαμίας'
$hint.ForeColor = $C::FromArgb(138, 149, 155)
$hint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
$hint.AutoSize = $true
$hint.Location = New-Object System.Drawing.Point(28, 356)
$form.Controls.Add($hint)

# Έλεγχος στο CI: αποθηκεύει εικόνα του παραθύρου (με την πρώτη κάρτα «υπό το ποντίκι») και κλείνει.
if ($env:SCHOOLAPPS_LAUNCHER_SNAPSHOT) {
    $form.Add_Shown({
        $cOro.Tag.hover = $true
        $form.Refresh()
        $bmp = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
        $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $bmp.Save($env:SCHOOLAPPS_LAUNCHER_SNAPSHOT, [System.Drawing.Imaging.ImageFormat]::Png)
        $form.Close()
    })
}

[void]$form.ShowDialog()
