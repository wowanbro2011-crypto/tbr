# core/disk_utils.py
import subprocess
import os
import sys
import datetime
import csv
import io
import re
from utils.helpers import format_file_size, write_log, write_error_log

def get_physical_drives():
    """Возвращает список словарей с информацией о физических дисках с четким маппингом разделов."""
    write_log('disk', ">>> Начало парсинга дисков через CIM/PowerShell")
    drives = []

    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "$drives = Get-CimInstance Win32_DiskDrive; "
            "$result = @(); "
            "foreach ($d in $drives) { "
            "   $letters = @(); "
            "   try { "
            "       $parts = Get-Disk -Number $d.Index -ErrorAction SilentlyContinue | Get-Partition -ErrorAction SilentlyContinue; "
            "       foreach ($p in $parts) { "
            "           if ($p.DriveLetter -and [int][char]$p.DriveLetter -ne 0) { "
            "               $letters += ($p.DriveLetter + ':') "
            "           } "
            "       } "
            "   } catch {} "
            "   if ($letters.Count -eq 0) { "
            "       try { "
            "           $q = \"ASSOCIATORS OF {Win32_DiskDrive.DeviceID='$($d.DeviceID)'} WHERE AssocClass = Win32_DiskDriveToDiskPartition\"; "
            "           $partitions = Get-CimInstance -Query $q -ErrorAction SilentlyContinue; "
            "           foreach ($part in $partitions) { "
            "               $q2 = \"ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($part.DeviceID)'} WHERE AssocClass = Win32_LogicalDiskToPartition\"; "
            "               $logicals = Get-CimInstance -Query $q2 -ErrorAction SilentlyContinue; "
            "               foreach ($ld in $logicals) { if ($ld.DeviceID) { $letters += $ld.DeviceID } } "
            "           } "
            "       } catch {} "
            "   } "
            "   $lettersStr = ($letters | Sort-Object -Unique) -join ', '; "
            "   try { "
            "       $rawTemp = (Get-CimInstance -Namespace root/wmi -ClassName MSStorageDriver_Temperature -ErrorAction SilentlyContinue | Where-Object { $_.InstanceName -match [regex]::Escape($d.PNPDeviceID) -or $_.InstanceName -match ('_' + $d.Index) }).Temperature; "
            "       if ($rawTemp -gt 2000) { $temp = [math]::Round(($rawTemp / 10.0) - 273.15) } "
            "       elseif ($rawTemp -gt 200) { $temp = [math]::Round($rawTemp - 273.15) } "
            "       else { $temp = $rawTemp } "
            "   } catch { $temp = $null }; "
            "   $result += [PSCustomObject]@{ "
            "       Model = if ($d.Model) { $d.Model.Trim() } else { 'Unknown Drive' }; "
            "       Size = if ($d.Size) { [string]$d.Size } else { '0' }; "
            "       Letters = $lettersStr; "
            "       Temperature = if ($temp -ne $null) { [string]$temp } else { '' }; "
            "       Status = if ($d.Status) { $d.Status } else { 'OK' } "
            "   } "
            "}; "
            "$result | ConvertTo-Csv -NoTypeInformation"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith('"Model"'):
                    continue
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)
                if len(parts) >= 5:
                    model = parts[0].strip('"')
                    size_str = parts[1].strip('"')
                    letters = parts[2].strip('"')
                    temp_str = parts[3].strip('"')
                    status = parts[4].strip('"')

                    try:
                        size_bytes = int(size_str)
                        size_fmt = format_file_size(size_bytes)
                    except ValueError:
                        size_bytes = 0
                        size_fmt = size_str

                    try:
                        temp_val = int(float(temp_str)) if temp_str else None
                        temp_display = f"{temp_val}°C" if temp_val is not None else "N/A"
                    except ValueError:
                        temp_display = "N/A"

                    drives.append({
                        'model': model,
                        'size': size_bytes,
                        'size_fmt': size_fmt,
                        'temperature': temp_display,
                        'status': 'Healthy' if status in ('OK', 'Healthy') else status,
                        'letters': letters if letters else '—'
                    })
            if drives:
                write_log('disk', f"Распарсено дисков: {len(drives)}")
                return drives
    except Exception as e:
        write_error_log("Ошибка опроса дисков", e)

    return []

def get_logical_drives():
    """Возвращает список букв логических томов (C:, D: и т.д.)."""
    try:
        cmd = ['powershell', '-NoProfile', '-Command',
               'Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -in @(2,3,4) } | Select-Object -ExpandProperty DeviceID']
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        drives = [line.strip().upper() for line in result.stdout.splitlines() if line.strip() and len(line.strip()) == 2]
        return sorted(list(dict.fromkeys(drives))) or ["C:"]
    except Exception:
        return ["C:"]

def run_disk_check(drive_letter, mode):
    """Запускает chkdsk."""
    args = ["chkdsk", drive_letter]
    args.extend(["/f", "/x"] if mode == "moderate" else ["/r", "/x"])
    try:
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='cp866', bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        write_error_log(f"Ошибка chkdsk {drive_letter}", e)
        return None

def parse_chkdsk_progress(line):
    patterns = [r'(\d+)\s*процентов\s*завершено', r'Этап\s*\d+:\s*(\d+)%', r'(\d+)%']
    for pat in patterns:
        m = re.search(pat, line, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None

CHKDSK_ERROR_MESSAGES = {
    0: "✅ Проверка успешно завершена. Ошибок не найдено.",
    1: "✅ Проверка завершена. Ошибки исправлены.",
    2: "⚠️ Ошибки обнаружены, но не исправлены.",
    3: "❌ Том занят другим процессом.",
    4: "❌ Том не найден.",
    5: "❌ Отказано в доступе. Нужны права Администратора.",
    50: "💀 Аппаратная ошибка накопителя.",
    255: "⚠️ Непредвиденная ошибка chkdsk."
}

def get_chkdsk_message(code):
    return CHKDSK_ERROR_MESSAGES.get(code, f"Код возврата: {code}")