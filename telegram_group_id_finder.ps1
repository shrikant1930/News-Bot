# Telegram Group ID Finder
# Your bot token is NOT saved in this file.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Telegram Group ID Finder ===" -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "Paste your Telegram bot token"

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "No token entered." -ForegroundColor Red
    exit 1
}

$token = $token.Trim()

Write-Host ""
Write-Host "Checking bot token..." -ForegroundColor Yellow

try {
    $me = Invoke-RestMethod "https://api.telegram.org/bot$token/getMe"
}
catch {
    Write-Host "Could not contact Telegram Bot API." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

if (-not $me.ok) {
    Write-Host "Telegram rejected the bot token." -ForegroundColor Red
    exit 1
}

Write-Host "Bot: @$($me.result.username) (ID: $($me.result.id))" -ForegroundColor Green
Write-Host ""

Write-Host "Getting recent Telegram updates..." -ForegroundColor Yellow

try {
    $updates = Invoke-RestMethod "https://api.telegram.org/bot$token/getUpdates"
}
catch {
    Write-Host "Could not retrieve Telegram updates." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

if (-not $updates.ok) {
    Write-Host "Telegram returned an error." -ForegroundColor Red
    exit 1
}

$groups = @{}

foreach ($update in $updates.result) {
    $chat = $null

    if ($null -ne $update.message -and $null -ne $update.message.chat) {
        $chat = $update.message.chat
    }
    elseif ($null -ne $update.my_chat_member -and $null -ne $update.my_chat_member.chat) {
        $chat = $update.my_chat_member.chat
    }
    elseif ($null -ne $update.chat_member -and $null -ne $update.chat_member.chat) {
        $chat = $update.chat_member.chat
    }

    if ($null -eq $chat) {
        continue
    }

    if ($chat.type -notin @("group", "supergroup")) {
        continue
    }

    $id = [string]$chat.id

    if (-not $groups.ContainsKey($id)) {
        $groups[$id] = [PSCustomObject]@{
            ID       = $chat.id
            Title    = $chat.title
            Username = $chat.username
            Type     = $chat.type
        }
    }
}

if ($groups.Count -eq 0) {
    Write-Host ""
    Write-Host "No group chats were found in the bot's recent updates." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Do this:" -ForegroundColor Cyan
    Write-Host "1. Add the bot to the group."
    Write-Host "2. Send /test in that group."
    Write-Host "3. Run this script again."
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "=== Groups Found ===" -ForegroundColor Cyan
Write-Host ""

$groups.Values | Sort-Object Title | Format-Table -AutoSize

Write-Host ""
Write-Host "Use the number in the ID column as the group's Telegram chat_id in Supabase." -ForegroundColor Green
Write-Host ""
Write-Host "Example: -5581824074" -ForegroundColor DarkGray
Write-Host ""

Read-Host "Press Enter to close"
