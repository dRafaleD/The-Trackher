import sys
import platform
from pathlib import Path

def setup_windows_context_menu():
    import winreg
    try:
        current_dir = Path(__file__).parent.resolve()
        python_exe = sys.executable
        script_path = current_dir / "main.py"
        
        # Tırnak işaretleri argümanı tek parça olarak almak için kritik
        command = f'"{python_exe}" "{script_path}" --shred "%1"'
        
        # Klasörler için sağ tık menüsü
        key_path_dir = r"Software\Classes\Directory\shell\FootprintShred"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path_dir) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "🛡️ Footprint ile Güvenli Sil (Shred)")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "imageres.dll,-53")
            with winreg.CreateKey(key, "command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, command)
                
        # Dosyalar için sağ tık menüsü
        key_path_file = r"Software\Classes\*\shell\FootprintShred"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path_file) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "🛡️ Footprint ile Güvenli Sil (Shred)")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "imageres.dll,-53")
            with winreg.CreateKey(key, "command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, command)
                
        print("[OK] Windows kullanıcı sağ tık menüsüne başarıyla eklendi!")
    except PermissionError:
        print("[HATA] Kullanıcı kayıt defterine yazma izni alınamadı.")
    except Exception as e:
        print(f"[HATA] Hata oluştu: {e}")

def setup_linux_context_menu():
    desktop_file = """[Desktop Entry]
Type=Action
Name=Footprint ile Güvenli Sil (Shred)
Icon=user-trash
Terminal=true
Profiles=profile-zero;

[X-Action-Profile profile-zero]
Exec={python_exe} {script_path} --shred %f
Name=Default profile
"""
    current_dir = Path(__file__).parent.resolve()
    script_path = current_dir / "main.py"
    python_exe = sys.executable

    def quote_exec_arg(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("`", "\\`").replace("$", "\\$")
        escaped = escaped.replace("%", "%%")
        return f'"{escaped}"'
    
    content = desktop_file.format(
        script_path=quote_exec_arg(str(script_path)),
        python_exe=quote_exec_arg(python_exe),
    )
    
    target_dir = Path.home() / ".local" / "share" / "file-manager" / "actions"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / "footprint-shred.desktop"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"[OK] Linux sağ tık menüsü aksiyonu oluşturuldu: {file_path}")
    print("Not: Dosya yöneticisini (Nautilus, Nemo vb.) yeniden başlatmanız gerekebilir.")

if __name__ == "__main__":
    if platform.system() == "Windows":
        setup_windows_context_menu()
    elif platform.system() == "Linux":
        setup_linux_context_menu()
    else:
        print("[UYARI] Sağ tık menüsü yalnızca Windows ve Linux'ta destekleniyor.")
