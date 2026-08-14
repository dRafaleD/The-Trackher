import platform
import shlex
import subprocess
import sys
from pathlib import Path
from utils.display import print_success, print_error

def schedule_task(interval: str = "daily") -> None:
    current_dir = Path(__file__).parent.parent.resolve()
    script_path = current_dir / "main.py"
    
    if platform.system() == "Windows":
        python_exe = sys.executable
        task_name = "DigitalAyakIziTemizleyici"
        command = subprocess.list2cmdline(
            [python_exe, str(script_path), "--clean-all", "--no-banner"]
        )
        
        sc = "DAILY" if interval.lower() == "daily" else "WEEKLY"
        
        cmd = [
            "schtasks", "/create", "/tn", task_name, "/tr", command, "/sc", sc, "/f"
        ]
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print_success(f"Windows Görev Zamanlayıcıya '{task_name}' görevi ({sc}) başarıyla eklendi.")
            print_success(f"Bu görev bilgisayarınızda arka planda düzenli olarak çalışacaktır.")
        except (OSError, subprocess.CalledProcessError):
            print_error("Zamanlanmış görev eklenemedi. Lütfen komut satırını Yönetici olarak çalıştırın.")
            
    elif platform.system() == "Linux":
        python_exe = sys.executable
        cron_command = " ".join(
            [
                shlex.quote(python_exe),
                shlex.quote(str(script_path)),
                "--clean-all",
                "--no-banner",
            ]
        )
        
        # Her gün 14:00 veya her Pazar 14:00
        cron_time = "0 14 * * *" if interval.lower() == "daily" else "0 14 * * 0" 
        
        marker = "# digitalayakizi-cleaner"
        cron_line = f"{cron_time} {cron_command} {marker}\n"
        
        try:
            current_cron_proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            current_cron = current_cron_proc.stdout if current_cron_proc.returncode == 0 else ""
            
            if marker in current_cron:
                print_error("Cron görevi zaten mevcut. Eklenmedi.")
                return
                
            new_cron = current_cron + cron_line
            
            subprocess.run(
                ["crontab", "-"],
                input=new_cron,
                text=True,
                capture_output=True,
                check=True,
            )
            
            print_success(f"Linux cron job ({interval}) başarıyla eklendi.")
        except (OSError, subprocess.CalledProcessError) as exc:
            print_error(f"Cron eklenirken hata oluştu: {exc}")
            
    else:
        print_error("Bu işletim sistemi için zamanlama henüz desteklenmiyor.")
