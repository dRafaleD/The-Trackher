import asyncio
import threading
import sys
import os
from pathlib import Path
import tkinter as tk
from PIL import Image

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter module is missing! Install it via 'pip install customtkinter'")
    sys.exit(1)

# Gerekli Modüller (Importing necessary modules)
from osint.checker import check_email
from osint.username_checker import check_username_async
from osint.dorking import generate_dorks
from footprint.shell import clean_shell_history
from footprint.browser import clean_browser_data
from footprint.system import clean_system_traces
from footprint.shredder import shred_file, shred_directory
from utils.helpers import format_size, expand_path

# Theme Settings (Terminal & Hacker dark theme)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green") 

class TrackherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Trackher - OSINT & Digital Footprint Cleaner")
        self.geometry("900x700")
        self.minsize(800, 650)
        
        # Terminal Colors
        self.bg_color = "#0c0c0c"
        self.fg_color = "#00ff00"
        self.font_terminal = ctk.CTkFont(family="Consolas", size=13)
        self.font_ui = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        
        self.configure(fg_color="#181818")
        
        # --- HEADER (Title & Logo) ---
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(15, 5))
        
        # Logo Loading
        logo_path = Path(__file__).parent / "assets" / "logo.jpg"
        if logo_path.exists():
            img = Image.open(logo_path)
            self.logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=(40, 40))
            self.lbl_logo = ctk.CTkLabel(self.header_frame, image=self.logo_image, text="")
            self.lbl_logo.pack(side="left", padx=(0, 10))
        
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="TRACKHER", font=ctk.CTkFont(size=28, weight="bold"), text_color="#00d2ff")
        self.lbl_title.pack(side="left")
        
        # --- TABVIEW ---
        self.tabview = ctk.CTkTabview(self, width=860, height=200, fg_color="#242424", segmented_button_fg_color="#333333")
        self.tabview.pack(padx=20, pady=5, fill="x")
        
        self.tabview.add("🔍 OSINT (Recon)")
        self.tabview.add("🧹 Cleaner")
        self.tabview.add("☢️ Shredder")
        
        self.setup_osint_tab()
        self.setup_cleaning_tab()
        self.setup_shredder_tab()
        
        # --- TERMINAL SCREEN ---
        self.lbl_term = ctk.CTkLabel(self, text="Terminal Output:", font=self.font_ui)
        self.lbl_term.pack(anchor="w", padx=20, pady=(10, 0))
        
        self.terminal = ctk.CTkTextbox(self, width=860, height=300, 
                                       fg_color=self.bg_color, text_color=self.fg_color, 
                                       font=self.font_terminal, wrap="word", border_width=2, border_color="#333")
        self.terminal.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        
        self.print_to_terminal("root@trackher:~# System initialized.")
        self.print_to_terminal("root@trackher:~# Modules loaded. Awaiting instructions...\n")
        
    def print_to_terminal(self, text: str):
        self.terminal.insert(tk.END, text + "\n")
        self.terminal.see(tk.END)
        
    def run_in_thread(self, func, *args):
        # Run in background to keep UI responsive
        thread = threading.Thread(target=func, args=args)
        thread.daemon = True
        thread.start()

    # ================= OSINT TAB =================
    def setup_osint_tab(self):
        tab = self.tabview.tab("🔍 OSINT (Recon)")
        
        self.osint_entry = ctk.CTkEntry(tab, placeholder_text="Enter Target Email or Username...", width=350, font=self.font_ui)
        self.osint_entry.grid(row=0, column=0, padx=20, pady=30)
        
        self.btn_email = ctk.CTkButton(tab, text="Scan Email", font=self.font_ui, command=lambda: self.run_in_thread(self.do_email_osint), fg_color="#1f538d", hover_color="#14375d")
        self.btn_email.grid(row=0, column=1, padx=10, pady=30)
        
        self.btn_user = ctk.CTkButton(tab, text="Scan Username", font=self.font_ui, command=lambda: self.run_in_thread(self.do_username_osint), fg_color="#1f538d", hover_color="#14375d")
        self.btn_user.grid(row=0, column=2, padx=10, pady=30)
        
        self.btn_dork = ctk.CTkButton(tab, text="Gen Dorks", font=self.font_ui, command=self.do_dork, fg_color="#9c59b6", hover_color="#8e44ad")
        self.btn_dork.grid(row=0, column=3, padx=10, pady=30)
        
    def do_email_osint(self):
        target = self.osint_entry.get().strip()
        if not target: return
        self.btn_email.configure(state="disabled")
        self.print_to_terminal(f"\n[+] OSINT: Initiating Email recon for '{target}'...")
        
        results = asyncio.run(check_email(target))
        found = [r for r in results if r["found"]]
        
        for r in found:
            detail = f" - {r.get('detail', '')}" if r.get('detail') else ""
            self.print_to_terminal(f"  [+] FOUND: {r['service']}{detail}")
            
        self.print_to_terminal(f"[!] Total {len(found)} records found across {len(results)} services.")
        self.btn_email.configure(state="normal")
        
    def do_username_osint(self):
        target = self.osint_entry.get().strip()
        if not target: return
        self.btn_user.configure(state="disabled")
        self.print_to_terminal(f"\n[+] OSINT: Initiating Username recon for '{target}'...")
        
        results = asyncio.run(check_username_async(target))
        found = [r for r in results if r["found"]]
        
        for r in found:
            self.print_to_terminal(f"  [+] FOUND: {r['platform']} -> {r['url']}")
            
        self.print_to_terminal(f"[!] Total {len(found)} platforms matched. (Scanned {len(results)})")
        self.btn_user.configure(state="normal")
        
    def do_dork(self):
        target = self.osint_entry.get().strip()
        if not target: return
        self.print_to_terminal(f"\n[+] DORK: Generating advanced search links for '{target}'...")
        
        dorks = generate_dorks(target)
        for d in dorks:
            self.print_to_terminal(f"  [{d['engine']}] {d['type']}: {d['url']}")

    # ================= CLEANING TAB =================
    def setup_cleaning_tab(self):
        tab = self.tabview.tab("🧹 Cleaner")
        
        self.chk_shell = ctk.CTkCheckBox(tab, text="Shell History & Logs", font=self.font_ui)
        self.chk_shell.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        self.chk_shell.select()
        
        self.chk_browser = ctk.CTkCheckBox(tab, text="Browser Cache & Cookies (SQLite Mode)", font=self.font_ui)
        self.chk_browser.grid(row=1, column=0, padx=30, pady=15, sticky="w")
        self.chk_browser.select()
        
        self.chk_system = ctk.CTkCheckBox(tab, text="System Traces (Temp, Trash, Thumbnails)", font=self.font_ui)
        self.chk_system.grid(row=2, column=0, padx=30, pady=15, sticky="w")
        self.chk_system.select()
        
        self.chk_dryrun = ctk.CTkSwitch(tab, text="SIMULATION (Dry-Run)", progress_color="#d35400", font=self.font_ui)
        self.chk_dryrun.grid(row=0, column=1, rowspan=2, padx=100, pady=10)
        self.chk_dryrun.select() 
        
        self.btn_clean = ctk.CTkButton(tab, text="START CLEANING", font=self.font_ui, command=lambda: self.run_in_thread(self.do_clean), fg_color="#c0392b", hover_color="#922b21", width=200, height=40)
        self.btn_clean.grid(row=2, column=1, padx=100, pady=10)
        
    def do_clean(self):
        dry_run = self.chk_dryrun.get()
        mode = "SIMULATION" if dry_run else "DESTRUCTIVE MODE"
        self.btn_clean.configure(state="disabled")
        self.print_to_terminal(f"\n[+] INIT CLEANING SEQUENCE [{mode}]...")
        
        all_items = []
        if self.chk_shell.get():
            self.print_to_terminal("  -> Purging shell traces...")
            all_items.extend(clean_shell_history(dry_run=dry_run))
            
        if self.chk_browser.get():
            self.print_to_terminal("  -> Wiping browser data...")
            all_items.extend(clean_browser_data(dry_run=dry_run))
            
        if self.chk_system.get():
            self.print_to_terminal("  -> Shredding system temporary files...")
            all_items.extend(clean_system_traces(dry_run=dry_run))
            
        total_size = sum(i.get("size", 0) for i in all_items)
        
        show_max = 20
        for item in all_items[:show_max]:
             self.print_to_terminal(f"    - {item['type']} | {item['path']} ({format_size(item['size'])})")
        if len(all_items) > show_max:
             self.print_to_terminal(f"    ... and {len(all_items) - show_max} more items.")
             
        self.print_to_terminal(f"[!] FINISHED: Total {len(all_items)} items processed. Reclaimed space: {format_size(total_size)}")
        self.btn_clean.configure(state="normal")

    # ================= SHREDDER TAB =================
    def setup_shredder_tab(self):
        tab = self.tabview.tab("☢️ Shredder")
        
        lbl = ctk.CTkLabel(tab, text="WARNING: Files wiped from here are unrecoverable!", text_color="#e74c3c", font=self.font_ui)
        lbl.grid(row=0, column=0, columnspan=2, pady=(15,5))
        
        self.shred_path = ctk.CTkEntry(tab, placeholder_text="Absolute path to file or directory...", width=500, font=self.font_ui)
        self.shred_path.grid(row=1, column=0, padx=20, pady=20)
        
        self.btn_shred = ctk.CTkButton(tab, text="SHRED TARGET", font=self.font_ui, command=lambda: self.run_in_thread(self.do_shred), fg_color="#8b0000", hover_color="#5a0000", width=150)
        self.btn_shred.grid(row=1, column=1, padx=10, pady=20)
        
    def do_shred(self):
        path_str = self.shred_path.get().strip()
        if not path_str: return
        
        try:
            target = expand_path(path_str)
        except Exception:
            self.print_to_terminal("  [-] ERROR: Invalid path format!")
            return
            
        self.btn_shred.configure(state="disabled")
        self.print_to_terminal(f"\n[+] SHRED: Attempting secure wipe on '{target}'...")
        
        if not target.exists():
            self.print_to_terminal("  [-] ERROR: Target path not found!")
            self.btn_shred.configure(state="normal")
            return
            
        if target.is_file():
            res = shred_file(str(target), passes=3, dry_run=False)
            if res: self.print_to_terminal("  [+] SUCCESS: File securely eradicated.")
        elif target.is_dir():
            res = shred_directory(str(target), passes=3, dry_run=False)
            self.print_to_terminal(f"  [+] SUCCESS: Directory contents wiped ({len(res)} items).")
        
        self.btn_shred.configure(state="normal")
        self.shred_path.delete(0, tk.END)

if __name__ == "__main__":
    app = TrackherApp()
    app.mainloop()
