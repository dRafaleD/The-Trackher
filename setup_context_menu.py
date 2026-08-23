import sys
import platform
import subprocess
from pathlib import Path

from utils.app_paths import launcher_arguments

def setup_windows_context_menu():
    import winreg
    try:
        command = subprocess.list2cmdline(launcher_arguments("--shred", "%1"))
        
        # Klasörler için sağ tık menüsü
        key_path_dir = r"Software\Classes\Directory\shell\FootprintShred"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path_dir) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "🛡️ Securely delete with Trackher (Shred)")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "imageres.dll,-53")
            with winreg.CreateKey(key, "command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, command)
                
        # Dosyalar için sağ tık menüsü
        key_path_file = r"Software\Classes\*\shell\FootprintShred"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path_file) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "🛡️ Securely delete with Trackher (Shred)")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "imageres.dll,-53")
            with winreg.CreateKey(key, "command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, command)
                
        print("[OK] Trackher was added to the user context menu.")
    except PermissionError:
        print("[ERROR] Could not write to the user registry.")
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")

def setup_linux_context_menu():
    desktop_file = """[Desktop Entry]
Type=Action
Name=Securely delete with Trackher (Shred)
Icon=user-trash
Terminal=true
Profiles=profile-zero;

[X-Action-Profile profile-zero]
Exec={launcher_command} %f
Name=Default profile
"""

    def quote_exec_arg(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("`", "\\`").replace("$", "\\$")
        escaped = escaped.replace("%", "%%")
        return f'"{escaped}"'

    quoted_args = [quote_exec_arg(part) for part in launcher_arguments("--shred")]
    
    content = desktop_file.format(
        launcher_command=" ".join(quoted_args),
    )
    
    target_dir = Path.home() / ".local" / "share" / "file-manager" / "actions"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / "trackher-shred.desktop"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"[OK] Trackher context-menu action created: {file_path}")
    print("Note: You may need to restart the file manager (Nautilus, Nemo, etc.).")

if __name__ == "__main__":
    if platform.system() == "Windows":
        setup_windows_context_menu()
    elif platform.system() == "Linux":
        setup_linux_context_menu()
    else:
        print("[WARN] Context-menu integration is supported only on Windows and Linux.")
