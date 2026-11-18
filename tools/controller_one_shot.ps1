[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateSet('init','preview','install','start-rm','prepare','run','observe','events','uninstall')][string]$Step,
      [string]$Directory = (Join-Path $env:LOCALAPPDATA 'LabPilot\controller-one-shot'))
$ErrorActionPreference = 'Stop'
$Directory = [IO.Path]::GetFullPath($Directory)
$settings = Join-Path $Directory 'acceptance.json'
$profile = Join-Path $Directory 'profile.json'
$review = Join-Path $Directory 'review.json'
function NewJson($Path, $Data) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Data | ConvertTo-Json -Depth 15))
    $stream = [IO.File]::Open($Path, 'CreateNew', 'Write', 'None')
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
}
function ExistingPath($Prompt, $Kind) {
    $path = (Read-Host $Prompt).Trim().Trim('"')
    if (!(Test-Path -LiteralPath $path -PathType $Kind)) { throw "Path does not exist: $path" }
    return (Resolve-Path -LiteralPath $path).ProviderPath
}
function CallPilot([string[]]$Arguments) {
    $raw = & $cli --profile $profile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "labpilot $($Arguments[0]) failed: $raw" }
    if ($raw) { return (($raw -join "`n") | ConvertFrom-Json) }
}
if ($Step -eq 'init') {
    if (Test-Path -LiteralPath $Directory) { throw 'Directory exists. Resume existing steps, or choose another -Directory deliberately.' }
    if (!$env:CONDA_PREFIX) { throw 'Activate the original Labscript conda environment.' }
    $python = Join-Path $env:CONDA_PREFIX 'python.exe'
    & $python -c "import sys; from importlib.metadata import version; print(sys.executable); print({n:version(n) for n in ('labscript','blacs','runmanager','lyse','labscript-utils','labpilot-ai')}); sys.exit(version('labpilot-ai')!='0.3.3')"
    if ($LASTEXITCODE -ne 0) { throw 'Check interpreter, installed packages and LabPilot 0.3.3.' }
    $labconfig = ExistingPath 'Existing LabConfig INI used by BLACS / Runmanager' Leaf
    $iniHash = (Get-FileHash -LiteralPath $labconfig).Hash
    $port = & $python -c "import configparser,sys; c=configparser.ConfigParser(interpolation=None); c.read(sys.argv[1],encoding='utf-8-sig'); p=c.getint('ports','runmanager'); assert 1<=p<=65535; print(p)" $labconfig
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read Runmanager port from selected LabConfig.' }
    $sequence = ExistingPath 'Existing authorized sequence .py' Leaf
    $routine = ExistingPath 'Existing trusted Lyse single-shot routine .py' Leaf
    $data = ExistingPath 'Existing writable LOCAL data directory' Container
    if ($data.StartsWith('\\') -or [IO.DriveInfo]::new([IO.Path]::GetPathRoot($data)).DriveType -eq 'Network') { throw 'Use a local disk for this acceptance.' }
    $result = (Read-Host 'Numeric result name written via save_result').Trim()
    $minimum = [double]::Parse((Read-Host 'Minimum acceptable value'), [Globalization.CultureInfo]::InvariantCulture)
    $maximum = [double]::Parse((Read-Host 'Maximum acceptable value'), [Globalization.CultureInfo]::InvariantCulture)
    if (!$result -or [double]::IsNaN($minimum) -or [double]::IsNaN($maximum) -or [double]::IsInfinity($minimum) -or [double]::IsInfinity($maximum) -or $minimum -gt $maximum) { throw 'Invalid quality rule.' }
    $batch = Join-Path $data ('labpilot-acceptance-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($batch)
    [void][IO.Directory]::CreateDirectory($Directory)
    NewJson $profile @{schema_version=1;simulate=$false;python=$python;host=@{runmanager=@{enabled=$true;allow=@('engage');port=[int]$port;max_shots=1;sequence_root=(Split-Path $sequence);output_root=$data;batch_root=$batch};blacs=@{enabled=$true;allow=@{}}};analysis=@{routine=$routine;routine_sha256=(Get-FileHash -LiteralPath $routine).Hash.ToLowerInvariant();quality_rules=@(@{result=$result;type='number';min=$minimum;max=$maximum});timeout_s=120}}
    NewJson $settings @{python=$python;labconfig=$labconfig;labconfig_sha256=$iniHash;port=[int]$port;sequence=$sequence;sequence_sha256=(Get-FileHash -LiteralPath $sequence).Hash.ToLowerInvariant();profile_sha256=(Get-FileHash -LiteralPath $profile).Hash}
    NewJson (Join-Path $Directory 'engage.json') @{target='runmanager';action='engage';expected_n_shots=1}
    Write-Host "Prepared $Directory. No device action."
    return
}
$site = Get-Content -LiteralPath $settings -Raw -Encoding UTF8 | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $profile).Hash -ne $site.profile_sha256) { throw 'Profile changed since init.' }
if ($Step -in @('preview','install') -and (Get-FileHash -LiteralPath $site.labconfig).Hash -ne $site.labconfig_sha256) { throw 'LabConfig changed since init. Review before installation.' }
if ($Step -in @('run','observe','events') -and !(Test-Path -LiteralPath $review)) { throw 'Missing review.json: prepare and review a task first.' }
$scripts = Join-Path (Split-Path $site.python) 'Scripts'
$cli = Join-Path $scripts 'labpilot.exe'
switch ($Step) {
    'preview' { CallPilot @('doctor','--labconfig',$site.labconfig) | ConvertTo-Json -Depth 12; CallPilot @('install-host','--labconfig',$site.labconfig) | ConvertTo-Json -Depth 8 }
    'install' {
        if ((Read-Host 'BLACS and Runmanager closed, lab idle? Type INSTALL') -cne 'INSTALL') { throw 'Cancelled.' }
        CallPilot @('install-host','--labconfig',$site.labconfig,'--apply') | ConvertTo-Json -Depth 8
    }
    'uninstall' {
        CallPilot @('uninstall-host','--labconfig',$site.labconfig) | ConvertTo-Json -Depth 8
        if ((Read-Host 'Both apps closed, no outstanding task? Type UNINSTALL') -cne 'UNINSTALL') { throw 'Cancelled.' }
        CallPilot @('uninstall-host','--labconfig',$site.labconfig,'--apply') | ConvertTo-Json -Depth 8
    }
    'start-rm' { & (Join-Path $scripts 'labpilot-runmanager.exe') --profile $profile; exit $LASTEXITCODE }
    'prepare' {
        $tasks = @(CallPilot @('list'))
        if ((Test-Path -LiteralPath $review) -or $tasks.Count) { throw 'Existing task: inspect existing review / ledger, do not resubmit.' }
        $caps = (CallPilot @('discover')).value.targets
        if (!$caps.runmanager.managed_batches -or !$caps.blacs.available) { throw 'Managed Runmanager / BLACS plugin unavailable.' }
        $snap = (CallPilot @('snapshot','runmanager')).value
        if ($snap.errors -ne $false -or $snap.flags.run -ne $true -or $snap.n_shots -ne 1 -or [IO.Path]::GetFullPath($snap.sequence) -ne $site.sequence -or $snap.sequence_sha256 -ne $site.sequence_sha256) { throw 'Sequence, file hash, flags, globals or shot count differs.' }
        $task = CallPilot @('prepare',(Join-Path $Directory 'engage.json'))
        NewJson $review $task
        if ($task.expected_config_digest -ne $snap.snapshot_sha256) { throw 'Configuration changed during prepare. Do not approve.' }
        NewJson (Join-Path $Directory 'snapshot.json') $snap
        Write-Host "Runmanager localhost:$($site.port), shots=$($snap.n_shots), sequence=$($snap.sequence), SHA256=$($snap.sequence_sha256)"
        Write-Host "Review snapshot.json, profile.json and review.json in $Directory. No Engage sent."
    }
    'run' {
        if (Test-Path -LiteralPath (Join-Path $Directory 'dispatch-intent.json')) { throw 'Dispatch already attempted. Use observe and events, do not repeat.' }
        $task = Get-Content -LiteralPath $review -Raw -Encoding UTF8 | ConvertFrom-Json
        $snap = Get-Content -LiteralPath (Join-Path $Directory 'snapshot.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $tasks = @(CallPilot @('list'))
        if ($tasks.Count -ne 1 -or $tasks[0].task_id -ne $task.task_id -or $tasks[0].status -ne 'PENDING_APPROVAL' -or $tasks[0].plan_digest -ne $task.plan_digest -or $task.expected_config_digest -ne $snap.snapshot_sha256) { throw 'Expected exactly this unapproved task.' }
        $token = 'ENGAGE ' + $task.task_id
        $operator = (Read-Host 'Approving operator name').Trim()
        if (!$operator -or (Read-Host "One physical shot using $($site.sequence). Type $token") -cne $token) { throw 'Cancelled.' }
        $fresh = (CallPilot @('snapshot','runmanager')).value
        if ($fresh.snapshot_sha256 -ne $task.expected_config_digest) { throw 'Configuration changed after review.' }
        NewJson (Join-Path $Directory 'dispatch-intent.json') @{task_id=$task.task_id;digest=$task.plan_digest;operator=$operator}
        $null = CallPilot @('approve',$task.task_id,$task.plan_digest,'--operator',$operator,'--minutes','5')
        $dispatched = CallPilot @('run-next')
        if (!$dispatched -or $dispatched.task_id -ne $task.task_id) { throw 'Dispatch uncertain. Observe original task; do not repeat.' }
        Write-Host "Task $($task.task_id): $($dispatched.status). Use observe."
    }
    { $_ -in @('observe','events') } {
        $task = Get-Content -LiteralPath $review -Raw -Encoding UTF8 | ConvertFrom-Json
        $observed = CallPilot @($Step,$task.task_id)
        $observed | ConvertTo-Json -Depth 20
        if ($Step -eq 'observe' -and $observed.status -eq 'COMPLETED') {
            foreach ($name in @('compiled_count','queued_count','executed_count','analyzed_count')) { if ($observed.evidence.$name -ne 1) { throw "Unexpected $name" } }
            if ($observed.evidence.quality -ne 'PASS' -or $observed.evidence.analysis_state -ne 'COMPLETE' -or $observed.evidence.simulated -eq $true -or !$observed.observation.value.evidence.blacs_execution_verified) { throw 'Missing native BLACS / Lyse evidence.' }
            Write-Host 'PASS: one compiled, queued, BLACS-completed and Lyse-qualified shot.'
        }
    }
}
