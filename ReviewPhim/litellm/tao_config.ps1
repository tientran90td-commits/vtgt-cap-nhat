# Tao config LiteLLM cho AI may nha: Ollama (mien phi, khong gioi han) + Gemini (neu co key) tu chuyen khi loi.
param([string]$Model = "gemma3:4b", [string]$Keys = "", [string]$Master = "", [string]$Out = "config-may-nha.yaml")
$keys = @($Keys.Split(",; `t".ToCharArray()) | ForEach-Object { $_.Trim() } | Where-Object { $_.Length -ge 20 })
$ollama = "    litellm_params: {model: `"ollama_chat/$Model`", api_base: `"http://localhost:11434`"}"
$l = New-Object System.Collections.Generic.List[string]
$l.Add("# Tao boi CAI_AI_MAY_NHA.bat - sua tay duoc. App goi model 'chinh' (viet / dich) va 'nhin-anh' (doc tranh).")
$l.Add("model_list:")
if ($keys.Count -gt 0) {
  foreach ($k in $keys) {
    $l.Add("  - model_name: chinh");    $l.Add("    litellm_params: {model: gemini/gemini-2.5-flash, api_key: `"$k`"}")
    $l.Add("  - model_name: nhin-anh"); $l.Add("    litellm_params: {model: gemini/gemini-2.5-flash, api_key: `"$k`"}")
  }
  $l.Add("  - model_name: may-nha"); $l.Add($ollama)
} else {
  $l.Add("  - model_name: chinh");    $l.Add($ollama)
  $l.Add("  - model_name: nhin-anh"); $l.Add($ollama)
}
$l.Add("litellm_settings:")
$l.Add("  num_retries: 2")
$l.Add("  request_timeout: 600")
$l.Add("  allowed_fails: 2")
$l.Add("  cooldown_time: 60")
$l.Add("  drop_params: true")
if ($keys.Count -gt 0) {
  $l.Add("  fallbacks:")
  $l.Add("    - chinh: [may-nha]")
  $l.Add("    - nhin-anh: [may-nha]")
}
$l.Add("general_settings:")
$l.Add("  master_key: `"$Master`"")
[System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot $Out), $l)
Write-Host "Da tao $Out ($($keys.Count) key Gemini, Ollama: $Model)"
