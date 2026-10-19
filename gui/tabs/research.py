"""Local case workspace and inspectable relationship map."""
import json
import hashlib
import math
import tkinter as tk
from tkinter import filedialog, messagebox

from gui.widgets.common import ctk
from gui.widgets.reviews import FindingReviewMixin
from utils.research import new_case, load_case, save_case, record_scan, graph_for_scan, result_key


class ResearchTabMixin(FindingReviewMixin):
    def setup_research_tab(self):
        self._case = new_case()
        self._case_saved_digest = self._case_digest()
        self._close_save_pending = False
        self._case_path = None
        self._scan_context = None
        self._retry_base = []
        self._scan_control = None
        tab = self.tabview.tab('Araştırma')
        top = ctk.CTkFrame(tab, fg_color='transparent')
        top.pack(fill='x', pady=(0, 8))
        self.case_title = ctk.CTkEntry(top, placeholder_text='Araştırma adı', width=230)
        self.case_title.insert(0, self._case['title'])
        self.case_title.pack(side='left', padx=(0, 8))
        for label, command in [('Yeni', self._new_case), ('Aç', self._open_case), ('Kaydet', self._save_case), ('Rapor', self._export_case)]:
            ctk.CTkButton(top, text=label, width=75, command=command, fg_color='#233b52').pack(side='left', padx=3)
        self.case_tags = ctk.CTkEntry(top, placeholder_text='Etiketler (virgülle)', width=200)
        self.case_tags.pack(side='right')
        self.case_notes = ctk.CTkTextbox(tab, height=55, wrap='word', fg_color='#152130')
        self.case_notes.pack(fill='x', pady=(0, 8))
        self.case_notes.insert('1.0', '')
        row = ctk.CTkFrame(tab, fg_color='transparent')
        row.pack(fill='x', pady=(0, 8))
        self.case_scan_menu = ctk.CTkOptionMenu(row, values=['Henüz tarama yok'], width=370, command=lambda _: self._render_case_scan())
        self.case_scan_menu.pack(side='left')
        for label, command in [('Kalanı sürdür', lambda: self._retry_scan(False)), ('Başarısızları dene', lambda: self._retry_scan(True))]:
            ctk.CTkButton(row, text=label, width=140, command=command, fg_color='#233b52').pack(side='right', padx=4)
        self.research_tabs = ctk.CTkTabview(tab, fg_color='#111c29')
        self.research_tabs.pack(fill='both', expand=True)
        for name in ('Bulgu inceleme', 'İlişki haritası', 'Değişiklikler', 'Zaman çizelgesi', 'Tarama kontrolü'):
            self.research_tabs.add(name)
        self.setup_finding_reviews()
        mapping = self.research_tabs.tab('İlişki haritası')
        self.graph_focus = ctk.CTkOptionMenu(mapping, values=['Profil seçin'], width=380, command=lambda _: self._draw_graph())
        self.graph_focus.pack(anchor='w', pady=5)
        self.graph_caption = ctk.CTkLabel(mapping, text='Düğümler ve çizgiler tıklanarak kanıtlar incelenebilir.', text_color='#91a4ba')
        self.graph_caption.pack(anchor='w')
        self.graph_canvas = tk.Canvas(mapping, background='#111c29', highlightthickness=0, height=180)
        self.graph_canvas.pack(fill='both', expand=True)
        self.graph_canvas.bind('<Configure>', lambda _: self._draw_graph())
        self.diff_box = ctk.CTkTextbox(self.research_tabs.tab('Değişiklikler'), wrap='word', fg_color='#111c29')
        self.diff_box.pack(fill='both', expand=True)
        self.control_box = ctk.CTkTextbox(self.research_tabs.tab('Tarama kontrolü'), wrap='word', fg_color='#111c29')
        self.control_box.pack(fill='both', expand=True)
        self.timeline_box = ctk.CTkTextbox(self.research_tabs.tab('Zaman çizelgesi'), wrap='word', fg_color='#111c29')
        self.timeline_box.pack(fill='both', expand=True)
        self._graph = {'nodes': [], 'edges': []}
        self._refresh_case_menu()
        self.after(300, self._tick_scan_control)

    def _set_box(self, box, text):
        box.configure(state='normal')
        box.delete('1.0', 'end')
        box.insert('1.0', text)
        box.configure(state='disabled')

    def _prepare_scan_context(self, kind, target, profile='standard'):
        self._scan_context = {'kind': kind, 'target': target, 'profile': profile}
        self._retry_base = []

    def _scan_kwargs(self):
        if self.__dict__.get('_scan_control') is None:
            return {}
        args = {'control': self._scan_control}
        if self.__dict__.get('_only_platforms') is not None:
            args['only_platforms'] = self._only_platforms
        if self.__dict__.get('_only_queries') is not None:
            args['only_queries'] = self._only_queries
        return args

    def _merge_results(self, rows):
        merged = {result_key(r): dict(r, retained_from_previous_scan=True) for r in self.__dict__.get('_retry_base', [])}
        for row in rows:
            key = result_key(row)
            old = merged.get(key, {})
            updated = dict(row)
            if old.get('discovered_from') and not updated.get('discovered_from'):
                updated['discovered_from'] = old['discovered_from']
            updated.pop('retained_from_previous_scan', None)
            merged[key] = updated
        return list(merged.values())

    def _record_research_scan(self, rows):
        if not self.__dict__.get('_scan_context') or not self.__dict__.get('_case'):
            return
        context = self._scan_context
        control = self.__dict__.get('_scan_control')
        try:
            record_scan(self._case, context['kind'], context['target'], context['profile'], rows,
                        stopped=control is not None and control.stopped.is_set())
            self._refresh_case_menu()
        except ValueError as exc:
            self.print_to_terminal(f'  [!] Araştırmaya eklenemedi: {exc}')

    def _selected_case_scan(self):
        labels = self.__dict__.get('_case_scan_labels', {})
        return labels.get(self.case_scan_menu.get())

    def _refresh_case_menu(self):
        self._case_scan_labels = {f'{i + 1} · {s["target"]} · {s["checked_at"]}': s for i, s in enumerate(self._case['scans'])}
        values = list(self._case_scan_labels) or ['Henüz tarama yok']
        self.case_scan_menu.configure(values=values)
        self.case_scan_menu.set(values[-1])
        self._render_case_scan()

    def _render_case_scan(self):
        scan = self._selected_case_scan()
        self._graph = graph_for_scan(scan, self._case['decisions'])
        self._graph_labels = {f'{node["label"]} · {node["id"]}': node['id'] for node in self._graph['nodes']}
        values = list(self._graph_labels) or ['Profil seçin']
        self.graph_focus.configure(values=values)
        self.graph_focus.set(values[0])
        diff = scan.get('diff', {}) if scan else {}
        names = {'new_profile': 'Yeni profil', 'new_record': 'Yeni kaynak kaydı', 'unavailable': 'Şu anda doğrulanamıyor', 'status': 'Durum değişti',
                 'field': 'Alan değişti', 'field_unavailable': 'Alan artık çıkarılamıyor',
                 'removed_link': 'Profildeki bağlantı kaldırıldı', 'added_link': 'Profile yeni bağlantı eklendi'}
        lines = [diff.get('message', 'Henüz tarama yok.'), '']
        if diff.get('coverage_changed'):
            lines.append('Kapsam değişti; kapsam dışındaki hesaplar kaldırılmış sayılmaz.')
        for item in diff.get('changes', []):
            lines.append(f"{item['site']} · {names.get(item['type'], item['type'])} · {item.get('field', '')}\n  Önce: {item.get('before', '—')}\n  Sonra: {item.get('after', '—')}\n")
        self._set_box(self.diff_box, '\n'.join(lines))
        self._render_finding_reviews()
        if self.__dict__.get('timeline_box') is not None:
            self._render_case_timeline()
        self._draw_graph()

    def _draw_graph(self):
        if not self.__dict__.get('_graph'):
            return
        canvas = self.graph_canvas
        canvas.delete('all')
        focus = self.__dict__.get('_graph_labels', {}).get(self.graph_focus.get())
        if not focus:
            return
        nodes = {n['id']: n for n in self._graph['nodes']}
        edges = [e for e in self._graph['edges'] if focus in (e['left'], e['right'])]
        neighbors = list(dict.fromkeys(e['right'] if e['left'] == focus else e['left'] for e in edges))
        visible = neighbors[:24]
        width, height = max(canvas.winfo_width(), 400), max(canvas.winfo_height(), 140)
        positions = {focus: (width / 2, height / 2)}
        for i, nid in enumerate(visible):
            angle = 2 * math.pi * i / max(len(visible), 1)
            positions[nid] = (width / 2 + (width / 2 - 90) * math.cos(angle), height / 2 + (height / 2 - 35) * math.sin(angle))
        for i, edge in enumerate(edges):
            if edge['left'] not in positions or edge['right'] not in positions:
                continue
            color = '#f2bd70' if edge['conflicts'] else {'related': '#5ce0b4', 'unrelated': '#dd8199'}.get(edge['decision'], '#5a889f')
            tag = f'edge{i}'
            canvas.create_line(*positions[edge['left']], *positions[edge['right']], fill=color, width=3, tags=tag, dash=(4, 3) if edge['kind'] in ('candidate', 'mention_candidate', 'certificate_candidate') else ())
            canvas.tag_bind(tag, '<Button-1>', lambda _, e=edge: self._inspect_edge(e))
        for i, (nid, (x, y)) in enumerate(positions.items()):
            node = nodes[nid]
            tag = f'node{i}'
            canvas.create_oval(x-9, y-9, x+9, y+9, fill='#50d7e8' if node['kind'] == 'profile' else '#aab3ff', outline='', tags=tag)
            canvas.create_text(x, y+18, text=node['label'][:27], fill='#c5cfdb', font=('Segoe UI', 10), tags=tag)
            canvas.tag_bind(tag, '<Button-1>', lambda _, n=node: self._show_document('Düğüm kanıtı', json.dumps(n, ensure_ascii=False, indent=2)))
        self.graph_caption.configure(text=f'{len(visible)} / {len(neighbors)} komşu gösteriliyor · Diğer düğümleri üstten seçin. Kesikli çizgi: aday ilişki. Sarı: çelişki.' + (' · İlk 200 profil işlendi.' if self._graph.get('truncated') else ''))

    def _inspect_edge(self, edge):
        win = ctk.CTkToplevel(self)
        win.title('İlişkinin kanıtları ve çelişkileri')
        win.geometry('760x520')
        win.transient(self)
        box = ctk.CTkTextbox(win, wrap='word')
        box.pack(fill='both', expand=True, padx=12, pady=12)
        self._set_box(box, 'Bu ilişki gerçek kişi sahipliğini kanıtlamaz. Kararınız yerel bir araştırma notudur.\n\n' + json.dumps(edge, ensure_ascii=False, indent=2))
        row = ctk.CTkFrame(win, fg_color='transparent')
        row.pack(pady=(0, 12))
        for label, value in [('İlişkili', 'related'), ('İlgisiz', 'unrelated'), ('Belirsiz', 'uncertain')]:
            def decide(value=value):
                self._case['decisions'][edge['id']] = value
                self._render_case_scan()
                win.destroy()
            ctk.CTkButton(row, text=label, command=decide, width=110).pack(side='left', padx=5)

    def _update_case_notes(self):
        self._case.update(title=self.case_title.get()[:200], notes=self.case_notes.get('1.0', 'end-1c'),
                          tags=[v.strip()[:80] for v in self.case_tags.get().split(',') if v.strip()][:30])

    def _load_case_widgets(self):
        self.case_title.delete(0, 'end')
        self.case_title.insert(0, self._case['title'])
        self.case_tags.delete(0, 'end')
        self.case_tags.insert(0, ', '.join(self._case.get('tags', [])))
        self.case_notes.delete('1.0', 'end')
        self.case_notes.insert('1.0', self._case.get('notes', ''))
        self._refresh_case_menu()
        self._case_saved_digest = self._case_digest()

    def _case_digest(self):
        return hashlib.sha256(json.dumps(self._case, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()

    def _has_unsaved_case(self):
        self._update_case_notes()
        return self._case_digest() != self.__dict__.get('_case_saved_digest')

    def _confirm_case_replacement(self):
        if not self._has_unsaved_case():
            return True
        choice = messagebox.askyesnocancel('Araştırmayı kaydet', 'Açık araştırmadaki değişiklikleri kaydetmek ister misin?', parent=self)
        return bool(self._save_case()) if choice is True else choice is False

    def _close_case_can_exit(self):
        editor = self.__dict__.get('_review_editor')
        if editor and editor['window'].winfo_exists():
            editor['window'].lift()
            editor['window'].focus_set()
            return False
        if self.__dict__.get('_close_save_pending'):
            if self.__dict__.get('_scan_active'):
                self.after(150, self._on_close)
                return False
            self._close_save_pending = False
            return bool(self._save_case())
        active = self.__dict__.get('_scan_active', False)
        if not active:
            return self._confirm_case_replacement()
        choice = messagebox.askyesnocancel('Tarama devam ediyor', 'Taramayı durdurup sonuçları ve notları kaydetmek ister misin? Hayır seçeneği kaydetmeden kapatır.', parent=self)
        if choice is True:
            self._stop_scan()
            self._close_save_pending = True
            self.after(150, self._on_close)
            return False
        return choice is False

    def _case_idle(self):
        if self.__dict__.get('_scan_active'):
            self.print_to_terminal('  [i] Önce taramayı durdurun veya tamamlanmasını bekleyin.')
            return False
        return True

    def _new_case(self):
        if not self._case_idle():
            return
        if not self._confirm_case_replacement():
            return
        self._case, self._case_path = new_case(), None
        self._load_case_widgets()

    def _open_case(self):
        if not self._case_idle():
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[('Trackher araştırması', '*.trackher.json'), ('JSON', '*.json')])
        if not path:
            return
        try:
            loaded = load_case(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Araştırma açılamadı', str(exc), parent=self)
            return
        if not self._confirm_case_replacement():
            return
        self._case, self._case_path = loaded, path
        self._load_case_widgets()

    def _save_case(self):
        if not self._case_idle():
            return False
        self._update_case_notes()
        path = self._case_path or filedialog.asksaveasfilename(parent=self, defaultextension='.trackher.json', filetypes=[('Trackher araştırması', '*.trackher.json')])
        if not path:
            return False
        try:
            save_case(path, self._case)
            self._case_path = path
            self._case_saved_digest = self._case_digest()
            self.print_to_terminal(f'  [+] Araştırma kaydedildi: {path}')
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror('Kaydedilemedi', str(exc), parent=self)
            return False

    def _export_case(self):
        from utils.research import export_case_html
        self._update_case_notes()
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.html', filetypes=[('HTML rapor', '*.html')])
        if path:
            try:
                export_case_html(path, self._case)
            except (OSError, ValueError) as exc:
                messagebox.showerror('Rapor oluşturulamadı', str(exc), parent=self)

    def _toggle_scan_pause(self):
        control = self.__dict__.get('_scan_control')
        if not control or not self._scan_active:
            return
        if control.paused.is_set():
            control.paused.clear()
            self.pause_scan_button.configure(text='Beklet')
        else:
            control.paused.set()
            self.pause_scan_button.configure(text='Devam et')

    def _stop_scan(self):
        control = self.__dict__.get('_scan_control')
        if control:
            control.stopped.set()

    def _tick_scan_control(self):
        if self._closing.is_set():
            return
        control = self.__dict__.get('_scan_control')
        if control:
            snapshot = control.snapshot()
            jobs = snapshot['jobs']
            counts = {state: sum(j['state'] == state for j in jobs) for state in ('waiting', 'running', 'done', 'stopped')}
            title = f"{snapshot['elapsed']} sn · Bekleyen {counts['waiting']} · Çalışan {counts['running']} · Tamamlanan {counts['done']} · Durdurulan {counts['stopped']}"
            if snapshot['paused']:
                title += '\nBekletiliyor: çalışan kontroller tamamlanır, yeni kontrol başlamaz.'
            lines = [title, '', *[f"{j['name']} · {j['state']} · {j['seconds']} sn" for j in jobs]]
            for row in self.__dict__.get('_raw_results', []):
                if row.get('unknown_cause') or row.get('diagnostic_cause'):
                    lines.append(f"{row.get('platform') or row.get('service')} · {row.get('unknown_cause') or row.get('diagnostic_cause')}")
            self._set_box(self.control_box, '\n'.join(lines))
            if self.__dict__.get('_scan_active'):
                self.scan_status.configure(text=f"{snapshot['elapsed']} sn · {counts['done']} tamamlandı · {counts['waiting']} bekliyor" + (' · Bekletiliyor' if snapshot['paused'] else ''))
        self.after(500, self._tick_scan_control)

    def _retry_scan(self, failures):
        if not self._case_idle():
            return
        scan = self._selected_case_scan()
        if not scan or scan['kind'] not in ('username', 'email'):
            self.print_to_terminal('  [i] Sürdürmek için kullanıcı adı veya e-posta taraması seçin.')
            return
        initial_target = scan['target']
        selected = [r for r in scan['rows'] if (str(r.get('status', '')).lower() in ('unknown', 'error', 'not_configured')
                    if failures else r.get('unknown_cause') == 'cancelled')]
        names = {str(r.get('platform') or r.get('service')) for r in selected}
        if not names:
            self.print_to_terminal('  [i] Seçilen taramada yeniden denenebilecek kontrol yok.')
            return
        self._prepare_scan_context(scan['kind'], scan['target'], scan['profile'])
        self._begin_scan_results(len(scan['rows']), 'Yeniden deneme')
        self._only_platforms = names
        if scan['kind'] == 'username':
            self._only_queries = [(str(r.get('platform')), r.get('queried_username') or initial_target) for r in selected]
        self.osint_entry.delete(0, 'end')
        self.osint_entry.insert(0, scan['target'])
        self.profile_var.set(scan['profile'])
        self._retry_base = list(scan['rows'])
        for row in scan['rows']:
            self._receive_scan_result(row)
        self.tabview.set('OSINT')
        worker = self.do_username_osint if scan['kind'] == 'username' else self.do_email_osint
        self.run_in_thread(worker, scan['target'], scan['profile'])
