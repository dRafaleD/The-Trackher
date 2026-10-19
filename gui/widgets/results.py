"""Complete, filterable scan results; rendered only on the Tk main thread."""
from __future__ import annotations

from collections import Counter
import json
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlsplit
import webbrowser

from gui.widgets.common import ctk
from utils.finding_reviews import search_text


STATUS_GROUPS = {
    'found': 'Bulundu', 'not_found': 'Bulunamadı',
    'unknown': 'Doğrulanamadı', 'error': 'Doğrulanamadı',
    'not_configured': 'Doğrulanamadı', 'possible': 'Olası',
    'manual': 'Manuel', 'no_public_evidence': 'Kanıt yok',
}
COLORS = {'Bulundu': '#5ce0b4', 'Bulunamadı': '#99a9bb',
          'Doğrulanamadı': '#f2bd70', 'Olası': '#aab3ff',
          'Manuel': '#99a9bb', 'Kanıt yok': '#99a9bb'}
CAUSES = {'bot_blocked': 'Otomatik erişim engellendi', 'forbidden': 'Erişim reddedildi',
          'blocked': 'Kaynağa erişim engellendi', 'unsafe_target': 'Herkese açık hedef doğrulanamadı',
          'insufficient_input': 'Marka adı bu araştırma için fazla kısa veya genel',
          'provider_error': 'Kaynak hizmeti hata döndürdü', 'source_unavailable': 'Kaynak kullanılamıyor',
          'response_too_large': 'Yanıt boyutu sınırını aştı', 'cancelled': 'Kullanıcı tarafından durduruldu',
          'rate_limited': 'İstek sınırına ulaşıldı', 'timeout': 'Yanıt süresi aşıldı',
          'parser_mismatch': 'Profil kanıtı doğrulanamadı', 'network_error': 'Bağlantı hatası',
          'redirect_changed': 'Farklı bir adrese yönlendirildi',
          'service_unavailable': 'Hizmet kullanılamıyor'}


def result_row(result: dict) -> dict:
    """Preserve every status, including manual and inconclusive email checks."""
    status = str(result.get('status', 'unknown')).lower()
    cause = str(result.get('unknown_cause') or result.get('diagnostic_cause') or '')
    return {'site': str(result.get('platform') or result.get('service') or 'Alan adı'),
            'group': STATUS_GROUPS.get(status, 'Bilgi'),
            'detail': str(CAUSES.get(cause) or result.get('detail') or status),
            'url': str(result.get('url') or ''), 'status': status}


def filter_rows(rows: list[dict], group: str = 'Tümü', query: str = '') -> list[dict]:
    needle = search_text(query.strip())
    return [row for row in rows if (group == 'Tümü' or row['group'] == group)
            and (not needle or needle in search_text(' '.join(row.values())))]


def public_link(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme in ('https', 'http') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


class ScanResultsMixin:
    def setup_scan_results(self, parent):
        self._result_rows = []
        self._raw_results = []
        self._result_index = {}
        self._scan_active = False
        self._scan_total = 0
        self._results_render_pending = False
        self.result_filter = tk.StringVar(value='Tümü')
        self.result_query = tk.StringVar()

        cards = ctk.CTkFrame(parent, fg_color='transparent')
        cards.grid(row=2, column=0, sticky='ew', pady=(8, 8))
        self.result_counts = {}
        for index, (key, title, color) in enumerate((('Tümü', 'TOPLAM KONTROL', '#e8f1fa'),
                ('Bulundu', 'BULUNDU', '#5ce0b4'), ('Bulunamadı', 'BULUNAMADI', '#99a9bb'),
                ('Doğrulanamadı', 'DOĞRULANAMADI', '#f2bd70'))):
            cards.grid_columnconfigure(index, weight=1, uniform='stats')
            card = ctk.CTkFrame(cards, fg_color='#152130', corner_radius=12, border_width=1, border_color='#26384b')
            card.grid(row=0, column=index, sticky='ew', padx=(0 if index == 0 else 5, 0 if index == 3 else 5))
            ctk.CTkLabel(card, text=title, height=20, text_color='#91a4ba', font=ctk.CTkFont(size=11, weight='bold')).pack(side='left', padx=(12, 4), pady=6)
            number = ctk.CTkLabel(card, text='0', text_color=color, font=ctk.CTkFont(size=23, weight='bold'))
            number.pack(side='right', padx=12, pady=6)
            self.result_counts[key] = number

        panel = ctk.CTkFrame(parent, fg_color='#111c29', corner_radius=12, border_width=1, border_color='#26384b')
        panel.grid(row=3, column=0, sticky='nsew')
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)
        toolbar = ctk.CTkFrame(panel, fg_color='transparent')
        toolbar.grid(row=0, column=0, sticky='ew', padx=16, pady=(12, 8))
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(toolbar, text='Tarama sonuçları', font=ctk.CTkFont(size=16, weight='bold'), text_color='#edf4fc').grid(row=0, column=0, sticky='w')
        self.results_summary = ctk.CTkLabel(toolbar, text='Yeni bir arama başlatın', text_color='#91a4ba')
        self.results_summary.grid(row=0, column=1, padx=12)
        search = ctk.CTkEntry(toolbar, placeholder_text='Sonuçlarda ara…', width=180, height=30, fg_color='#0c1520', border_color='#304459')
        self.result_search = search
        search.grid(row=0, column=2)
        search.bind('<KeyRelease>', lambda event: self._search_results())
        filters = ctk.CTkSegmentedButton(panel, values=['Tümü', 'Bulundu', 'Bulunamadı', 'Doğrulanamadı', 'Olası', 'Manuel', 'Kanıt yok', 'Bilgi'], variable=self.result_filter,
            command=lambda value: self._render_results(), selected_color='#164c5d', selected_hover_color='#206579', unselected_color='#192737', unselected_hover_color='#263b51', fg_color='#192737', height=30)
        filters.grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 10))

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Trackher.Treeview', background='#111c29', fieldbackground='#111c29', foreground='#cad8e8', borderwidth=0, rowheight=32, font=('Segoe UI', 11))
        style.configure('Trackher.Treeview.Heading', background='#1b2a3c', foreground='#d4e2f1', relief='flat', font=('Segoe UI', 10, 'bold'))
        style.map('Trackher.Treeview', background=[('selected', '#20495d')], foreground=[('selected', '#ffffff')])
        holder = ctk.CTkFrame(panel, fg_color='transparent')
        holder.grid(row=2, column=0, sticky='nsew', padx=16)
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        self.results_tree = ttk.Treeview(holder, columns=('site', 'status', 'detail'), show='headings', style='Trackher.Treeview', selectmode='browse', height=4)
        for key, title, width in (('site', 'PLATFORM / HİZMET', 210), ('status', 'DURUM', 150), ('detail', 'AÇIKLAMA', 430)):
            self.results_tree.heading(key, text=title)
            self.results_tree.column(key, width=width, minwidth=100, stretch=True)
        self.results_tree.grid(row=0, column=0, sticky='nsew')
        scroll = ctk.CTkScrollbar(holder, command=self.results_tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.results_tree.configure(yscrollcommand=scroll.set)
        for group, color in COLORS.items():
            self.results_tree.tag_configure(group, foreground=color)
        self.results_tree.bind('<<TreeviewSelect>>', self._select_result)
        self.results_tree.bind('<Double-1>', lambda event: self._open_result())
        self.results_tree.bind('<Return>', lambda event: self._open_result())
        self.empty_label = ctk.CTkLabel(holder, text='Henüz sonuç yok\nBir kullanıcı adı veya e-posta ile başlayın.', text_color='#91a4ba', font=ctk.CTkFont(size=14), fg_color='#111c29')
        self.empty_label.place(relx=.5, rely=.55, anchor='center')

        footer = ctk.CTkFrame(panel, fg_color='transparent')
        footer.grid(row=3, column=0, sticky='ew', padx=16, pady=10)
        footer.grid_columnconfigure(0, weight=1)
        self.result_detail = ctk.CTkLabel(footer, text='Bir satır seçerek ayrıntıları görüntüleyin.', text_color='#91a4ba', anchor='w', justify='left', wraplength=480)
        self.result_detail.grid(row=0, column=0, sticky='w')
        self.copy_result_button = ctk.CTkButton(footer, text='Bağlantıyı kopyala', width=125, height=30, state='disabled', command=self._copy_result, fg_color='#23374b', hover_color='#304b65')
        self.copy_result_button.grid(row=0, column=2, padx=8)
        self.open_result_button = ctk.CTkButton(footer, text='Kaynağı aç ↗', width=100, height=30, state='disabled', command=self._open_result, fg_color='#164c5d', hover_color='#206579')
        self.open_result_button.grid(row=0, column=3)
        self.evidence_button = ctk.CTkButton(footer, text='Kanıt', width=72, height=30, state='disabled', command=self._show_evidence, fg_color='#23374b', hover_color='#304b65')
        self.evidence_button.grid(row=0, column=1)

    def _begin_scan_results(self, total, kind):
        if self.__dict__.get('results_tree') is None:
            return
        from osint.scan_control import ScanControl
        self._scan_control = ScanControl()
        self._only_platforms = None
        self._only_queries = None
        self.pause_scan_button.configure(state='normal', text='Beklet')
        self.stop_scan_button.configure(state='normal')
        self._scan_active = True
        self._scan_total = total
        self._result_rows = []
        self._raw_results = []
        self._result_index = {}
        self._scan_history_enabled = bool(self.chk_history.get())
        self._discover_links_enabled = bool(self.discover_links_checkbox.get())
        self.discover_links_checkbox.configure(state='disabled')
        self.result_filter.set('Tümü')
        self.result_query.set('')
        self.result_search.delete(0, 'end')
        for button in (self.btn_user, self.btn_email):
            button.configure(state='disabled')
        self.btn_domain.configure(state='disabled')
        if self.__dict__.get('btn_intelligence') is not None:
            self.btn_intelligence.configure(state='disabled')
            self.intelligence_mode.configure(state='disabled')
        self.opt_profile.configure(state='disabled')
        self.scan_status.configure(text=f'{kind} taranıyor…', text_color='#50d7e8')
        self.scan_progress.configure(mode='indeterminate')
        self.scan_progress.start()
        if not self._results_render_pending:
            self._results_render_pending = True
            self.after(80, self._flush_result_render)

    def _flush_result_render(self):
        self._results_render_pending = False
        self._render_results()

    def _receive_scan_result(self, result):
        if not self._scan_active:
            return
        row = result_row(result)
        from utils.research import result_key
        key = result_key(result)
        if key in self._result_index:
            self._result_rows[self._result_index[key]] = row
            self._raw_results[self._result_index[key]] = dict(result)
        else:
            self._result_index[key] = len(self._result_rows)
            self._result_rows.append(row)
            self._raw_results.append(dict(result))
        self._scan_total = max(self._scan_total, len(self._result_rows))
        self.scan_status.configure(text=f'{len(self._result_rows)} / {self._scan_total} kontrol tamamlandı · Tarama sürüyor')
        self.scan_progress.stop()
        self.scan_progress.configure(mode='determinate')
        self.scan_progress.set(min(len(self._result_rows) / max(self._scan_total, 1), 1))
        if not self._results_render_pending:
            self._results_render_pending = True
            self.after(80, self._flush_result_render)

    def _complete_scan_results(self, results):
        self._raw_results = list(results)
        self._result_rows = [result_row(result) for result in results]
        self._scan_active = False
        self.scan_progress.stop()
        self.scan_progress.configure(mode='determinate')
        self.scan_progress.set(1)
        stopped = self.__dict__.get('_scan_control') is not None and self._scan_control.stopped.is_set()
        self.scan_status.configure(text=f'{"Tarama durduruldu" if stopped else "Tarama tamamlandı"} · {len(results)} sonuç', text_color='#f2bd70' if stopped else '#5ce0b4')
        self._record_research_scan(results)
        self._render_results()

    def _release_scan_results(self):
        if self.__dict__.get('_scan_control') is not None:
            self._scan_control.finish()
            self.pause_scan_button.configure(state='disabled')
            self.stop_scan_button.configure(state='disabled')
        if self._scan_active:
            self.scan_progress.stop()
            self.scan_status.configure(text='Tarama tamamlanamadı · İşlem günlüğünü inceleyin', text_color='#f2bd70')
        self._scan_active = False
        self.opt_profile.configure(state='normal')
        self.discover_links_checkbox.configure(state='normal')
        self.btn_domain.configure(state='normal')
        if self.__dict__.get('btn_intelligence') is not None:
            self.btn_intelligence.configure(state='normal')
            self.intelligence_mode.configure(state='normal')
        for button in (self.btn_user, self.btn_email):
            button.configure(state='normal')

    def _render_results(self):
        rows = filter_rows(self._result_rows, self.result_filter.get(), self.result_query.get())
        selected = self.results_tree.selection()
        selected_index = selected[0] if selected else None
        children = self.results_tree.get_children()
        if children:
            self.results_tree.delete(*children)
        visible = {id(row) for row in rows}
        for index, row in enumerate(self._result_rows):
            if id(row) in visible:
                self.results_tree.insert('', 'end', iid=str(index), values=(row['site'], row['group'], row['detail']), tags=(row['group'],))
        if selected_index and self.results_tree.exists(selected_index):
            self.results_tree.selection_set(selected_index)
        else:
            self.result_detail.configure(text='Bir satır seçerek ayrıntıları görüntüleyin.')
            self.open_result_button.configure(state='disabled')
            self.copy_result_button.configure(state='disabled')
            self.evidence_button.configure(state='disabled')
        counts = Counter(row['group'] for row in self._result_rows)
        for group, label in self.result_counts.items():
            label.configure(text=str(len(self._result_rows) if group == 'Tümü' else counts[group]))
        self.results_summary.configure(text=f'{len(rows)} / {len(self._result_rows)} sonuç gösteriliyor')
        if rows:
            self.empty_label.place_forget()
        else:
            self.empty_label.configure(text='Eşleşen sonuç yok' if self._result_rows else 'Henüz sonuç yok\nBir kullanıcı adı veya e-posta ile başlayın.')
            self.empty_label.place(relx=.5, rely=.55, anchor='center')

    def _search_results(self):
        self.result_query.set(self.result_search.get())
        self._render_results()

    def _selected_result(self):
        selected = self.results_tree.selection()
        return self._result_rows[int(selected[0])] if selected else None

    def _select_result(self, event=None):
        row = self._selected_result()
        if row:
            self.result_detail.configure(text=f"{row['site']} · {row['detail']}\n{row['url']}")
            state = 'normal' if public_link(row['url']) else 'disabled'
            self.open_result_button.configure(state=state)
            self.copy_result_button.configure(state=state)
            self.evidence_button.configure(state='normal')

    def _show_document(self, title, text):
        window = ctk.CTkToplevel(self)
        window.title(title)
        window.geometry(f'800x{min(620, int(self.winfo_screenheight() / self._get_window_scaling()) - 100)}')
        window.minsize(580, 380)
        window.transient(self)
        window.configure(fg_color='#0c1420')
        box = ctk.CTkTextbox(window, fg_color='#111c29', text_color='#c5cfdb', wrap='word', font=ctk.CTkFont(size=13))
        box.pack(fill='both', expand=True, padx=18, pady=18)
        box.insert('1.0', text)
        box.configure(state='disabled')

    def _show_evidence(self):
        selected = self.results_tree.selection()
        if not selected:
            return
        from osint.evidence import evidence_card
        from utils.platform_health import load_cached_health_summary
        result = self._raw_results[int(selected[0])]
        card = result.get('evidence_card') or evidence_card(result)
        labels = {'checked_at': 'Kontrol zamanı', 'source_url': 'Kaynak', 'http_status': 'HTTP durumu',
                  'detector': 'Doğrulama yöntemi', 'reason': 'Açıklama', 'unknown_cause': 'Belirsizlik nedeni'}
        lines = [str(result.get('platform') or result.get('service') or 'Kanıt kartı'), '']
        lines += [f'{label}: {card.get(key) or "—"}' for key, label in labels.items()]
        lines += ['', 'KAYNAĞI GÖRÜLEBİLEN ALANLAR']
        for field in card.get('fields', []):
            lines.append(f"{field.get('field')}: {field.get('value')}\n  Kaynak alan: {field.get('source')}")
        lines += ['', 'EŞLEŞEN DOĞRULAMA KURALLARI', json.dumps(card.get('rules', []), ensure_ascii=False, indent=2)]
        if result.get('discovered_from'):
            lines += ['', 'BU HESABA BAĞLANTI VEREN KAYNAK', str(result['discovered_from'].get('source_url', ''))]
        health = load_cached_health_summary() or {}
        for item in health.get('items', []):
            if item.get('platform') == result.get('platform'):
                lines += ['', 'SİTE KURALI SAĞLIĞI', f"Son referans çifti doğrulaması: {item.get('last_reference_success_at') or 'Henüz yok'}"]
                break
        lines += ['', 'Profil varlığı ve herkese açık beyanlar, gerçek kişi sahipliğini kanıtlamaz.']
        self._show_document('Kanıt kartı', '\n'.join(lines))

    def _open_result(self):
        row = self._selected_result()
        if row and public_link(row['url']):
            webbrowser.open(row['url'])

    def _copy_result(self):
        row = self._selected_result()
        if row and public_link(row['url']):
            self.clipboard_clear()
            self.clipboard_append(row['url'])

    def _saved_history_choice(self):
        control = self.__dict__.get('_scan_control')
        if (control is not None and control.stopped.is_set()) or self.__dict__.get('_retry_base'):
            return False
        if '_scan_history_enabled' in self.__dict__:
            return self._scan_history_enabled
        return bool(self.chk_history.get())
