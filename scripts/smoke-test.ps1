$ErrorActionPreference = "Stop"

$baseUrl = if ($env:API_BASE_URL) { $env:API_BASE_URL } else { "http://localhost:8000" }

Write-Host "PulseBoard smoke test against $baseUrl"

$login = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/login" `
  -ContentType "application/json" `
  -Body '{"email":"ada@pulseboard.local","user_id":"ada","name":"Ada Lovelace","role":"admin"}'

$headers = @{ "X-Session-Token" = $login.session_token }

$health = Invoke-RestMethod "$baseUrl/health"
if ($health.redis -ne "ok") { throw "Redis health check failed" }

$session = Invoke-RestMethod "$baseUrl/auth/session/$($login.session_token)"
if ($session.user_id -ne "ada" -or $session.ttl_seconds -le 0) { throw "Session verification failed" }

$profile = Invoke-RestMethod "$baseUrl/users/ada/profile" -Headers $headers
if ($profile.profile.email -ne "ada@pulseboard.local") { throw "Profile HGETALL verification failed" }

$field = Invoke-RestMethod "$baseUrl/users/ada/profile/email" -Headers $headers
if ($field.value -ne "ada@pulseboard.local") { throw "Profile HGET verification failed" }

$fields = Invoke-RestMethod "$baseUrl/users/ada/profile-fields?fields=email&fields=role" -Headers $headers
if ($fields.fields.email -ne "ada@pulseboard.local") { throw "Profile HMGET verification failed" }

$exists = Invoke-RestMethod "$baseUrl/users/ada/exists" -Headers $headers
if (-not $exists.exists) { throw "Profile exists verification failed" }

$rate = Invoke-RestMethod "$baseUrl/rate-limit/status" -Headers $headers
if ($rate.remaining -lt 0) { throw "Rate-limit verification failed" }

$online = Invoke-RestMethod -Method Post "$baseUrl/presence/online" -Headers $headers
if (-not $online.online) { throw "Presence online verification failed" }

$isOnline = Invoke-RestMethod "$baseUrl/presence/ada" -Headers $headers
if (-not $isOnline.online) { throw "Presence lookup verification failed" }

Invoke-RestMethod -Method Post "$baseUrl/workspaces/incidents/members/ada" -Headers $headers | Out-Null
Invoke-RestMethod -Method Post "$baseUrl/workspaces/incidents/members/bob" -Headers $headers | Out-Null
$members = Invoke-RestMethod "$baseUrl/workspaces/incidents/members" -Headers $headers
if ($members -notcontains "ada") { throw "Workspace members verification failed" }

Invoke-RestMethod -Method Post "$baseUrl/workspaces/platform/members/ada" -Headers $headers | Out-Null
Invoke-RestMethod -Method Post "$baseUrl/workspaces/platform/members/bob" -Headers $headers | Out-Null
$common = Invoke-RestMethod "$baseUrl/workspaces/common?user_a=ada&user_b=bob" -Headers $headers
if ($common.workspaces -notcontains "platform") { throw "Workspace SINTER verification failed" }

$accepted = Invoke-RestMethod -Method Post "$baseUrl/workspaces/warroom/invitations/ada/accept" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"note":"smoke transaction"}'
if (-not $accepted.accepted) { throw "Transaction verification failed" }

$feed = Invoke-RestMethod "$baseUrl/users/ada/feed" -Headers $headers
if ($feed.feed.Count -lt 1) { throw "Feed verification failed" }

Invoke-RestMethod -Method Post "$baseUrl/channels/demo/messages" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"content":"Deployment started from smoke test"}' | Out-Null

Invoke-RestMethod -Method Post "$baseUrl/channels/demo/typing" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"is_typing":true}' | Out-Null

$trending = Invoke-RestMethod "$baseUrl/analytics/trending" -Headers $headers
if ($trending[0].channel_id -ne "demo") { throw "Trending channel verification failed" }

$reputation = Invoke-RestMethod -Method Post "$baseUrl/analytics/reputation/ada" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"delta":2}'
if ($reputation.score -lt 2) { throw "Reputation verification failed" }

Invoke-RestMethod -Method Post "$baseUrl/events" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"type":"workspace.audit","payload":{"workspace_id":"incidents"}}' | Out-Null

Invoke-RestMethod -Method Post "$baseUrl/jobs" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"type":"send_welcome_email","payload":{"user_id":"ada"}}' | Out-Null

Invoke-RestMethod -Method Post "$baseUrl/jobs/scheduled" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"type":"nightly_summary","payload":{"workspace_id":"incidents"},"delay_seconds":1}' | Out-Null

$lock = Invoke-RestMethod -Method Post "$baseUrl/locks/daily_digest/acquire" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"owner":"smoke-test","ttl_seconds":30}'
if (-not $lock.acquired) { throw "Lock acquisition verification failed" }

$lockAgain = Invoke-RestMethod -Method Post "$baseUrl/locks/daily_digest/acquire" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"owner":"smoke-test-2","ttl_seconds":30}'
if ($lockAgain.acquired) { throw "Lock exclusivity verification failed" }

$released = Invoke-RestMethod -Method Post "$baseUrl/locks/daily_digest/release" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"owner":"smoke-test"}'
if (-not $released.released) { throw "Lock release verification failed" }

Invoke-RestMethod -Method Post "$baseUrl/analytics/dau" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"date":"2026-05-30"}' | Out-Null

$dau = Invoke-RestMethod "$baseUrl/analytics/dau/2026-05-30" -Headers $headers
if ($dau.count -lt 1) { throw "DAU verification failed" }

Invoke-RestMethod -Method Post "$baseUrl/attendance/ada/active" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"date":"2026-05-30"}' | Out-Null

$attendance = Invoke-RestMethod "$baseUrl/attendance/ada/2026-05-30" -Headers $headers
if (-not $attendance.active) { throw "Attendance GETBIT verification failed" }

$attendanceCount = Invoke-RestMethod "$baseUrl/attendance/ada/2026-05/count" -Headers $headers
if ($attendanceCount.active_days -lt 1) { throw "Attendance BITCOUNT verification failed" }

Invoke-RestMethod -Method Put "$baseUrl/geo/users/ada" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"longitude":77.5946,"latitude":12.9716}' | Out-Null

$nearby = Invoke-RestMethod "$baseUrl/geo/nearby?longitude=77.5946&latitude=12.9716&radius_km=5" -Headers $headers
if ($nearby.users -notcontains "ada") { throw "Geo verification failed" }

Start-Sleep -Seconds 3

Write-Host "PASS: all PulseBoard Redis requirement smoke checks passed."
