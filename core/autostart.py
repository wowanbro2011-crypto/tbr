# core/autostart.py
import os
import sys

def get_exe_or_script_command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    else:
        main_script = os.path.abspath(sys.argv[0])
        return f'"{sys.executable}" "{main_script}"'

def set_autostart(enable=True):
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        app_name = "tbr_swiss_knife"
        if enable:
            cmd = get_exe_or_script_command()
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True, "Автозагрузка включена" if enable else "Автозагрузка отключена"
    except Exception as e:
        return False, str(e)

def is_autostart_enabled():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            val, _ = winreg.QueryValueEx(key, "tbr_swiss_knife")
            winreg.CloseKey(key)
            return bool(val)
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False