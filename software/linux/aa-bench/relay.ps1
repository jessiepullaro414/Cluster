# Windows twin of relay.py, for a machine with no Python: joins the phone's (or emulator's) Android Auto head
# unit server, reached through `adb forward tcp:5277 tcp:5277`, to LIVI's Android Auto port. LIVI may run in WSL:
# Windows reaches a WSL listener on localhost, but WSL cannot reach adb's forward on Windows localhost, which is
# why the relay runs here. Same idea as relay.py: connect to both listeners and copy bytes both ways.
#
#   powershell -File relay.ps1 [-Phone 127.0.0.1:5277] [-Livi 127.0.0.1:5278] [-Once]
param(
    [string]$Phone = "127.0.0.1:5277",
    [string]$Livi = "127.0.0.1:5278",
    [switch]$Once
)

function Connect-Tcp([string]$hostPort) {
    $h, $p = $hostPort.Split(":")
    $c = [System.Net.Sockets.TcpClient]::new()
    $c.NoDelay = $true
    $c.Connect($h, [int]$p)
    return $c
}

while ($true) {
    try {
        Write-Host "[relay] connecting phone $Phone <-> LIVI $Livi"
        $p = Connect-Tcp $Phone
        $l = Connect-Tcp $Livi
        $ps, $ls = $p.GetStream(), $l.GetStream()
        $up = $ps.CopyToAsync($ls)      # phone -> LIVI (the video)
        $down = $ls.CopyToAsync($ps)    # LIVI -> phone (input, sensors, acks)
        $t0 = Get-Date
        while (-not ($up.IsCompleted -or $down.IsCompleted)) {
            [void][System.Threading.Tasks.Task]::WaitAny(@($up, $down), 5000)
            Write-Host ("[relay] {0,5:N0} s  session open" -f ((Get-Date) - $t0).TotalSeconds)
        }
        Write-Host "[relay] session ended (phone->LIVI done: $($up.IsCompleted), LIVI->phone done: $($down.IsCompleted))"
        $p.Close(); $l.Close()
    } catch {
        Write-Host "[relay] $($_.Exception.Message); retrying in 3 s"
    }
    if ($Once) { break }
    Start-Sleep -Seconds 3
}
