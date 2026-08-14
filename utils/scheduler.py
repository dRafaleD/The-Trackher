import platform
import subprocess
from pathlib import Path
from utils.display import print_success, print_error

def schedule_task(interval: str = "daily") -> None:
    current_dir = Path(__file__).parent.parent.resolve()
    script_path = current_dir / "main.py"
    
    if platform.system() == "Windows":
        import sys
        python_exe = sys.executable
        task_name = "DigitalAyakIziTemizleyici"
        command = f"{python_exe} {script_path} --clean-all"
        
        sc = "DAILY" if interval.lower() == "daily" else "WEEKLY"
        
        cmd = [
            "schtasks", "/create", "/tn", task_name, "/tr", command, "/sc", sc, "/f"
        ]
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print_success(f"Windows Görev Zamanlayıcıya '{task_name}' görevi ({sc}) başarıyla eklendi.")
            print_success(f"Bu görev bilgisayarınızda arka planda düzenli olarak çalışacaktır.")
        except subprocess.CalledProcessError:
            print_error("Zamanlanmış görev eklenemedi. Lütfen komut satırını Yönetici olarak çalıştırın.")
            
    elif platform.system() == "Linux":
        import sys
        python_exe = sys.executable
        cron_command = f"{python_exe} {script_path} --clean-all"
        
        # Her gün 14:00 veya her Pazar 14:00
        cron_time = "0 14 * * *" if interval.lower() == "daily" else "0 14 * * 0" 
        
        cron_line = f"{cron_time} {cron_command}\n"
        
        try:
            current_cron_proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            current_cron = current_cron_proc.stdout if current_cron_proc.returncode == 0 else ""
            
            if "digitalayakizi/main.py" in current_cron:
                print_error("Cron görevi zaten mevcut. Eklenmedi.")
                return
                
            new_cron = current_cron + cron_line
            
            p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=new_cron)
            
            print_success(f"Linux cron job ({interval}) başarıyla eklendi.")
        except Exception as e:
            print_error(f"Cron eklenirken hata oluştu: {e}")
            
    else:
        print_error("Bu işletim sistemi için zamanlama henüz desteklenmiyor.")
