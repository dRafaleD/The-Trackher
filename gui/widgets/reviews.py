"""A searchable, annotated review queue for each saved scan."""
from collections import Counter
import json
from tkinter import ttk, filedialog, messagebox

from gui.widgets.common import ctk
from gui.widgets.results import result_row
from utils.finding_reviews import REVIEW_STATES, VIEW_STATES, PRIORITIES, review_rows, review_for, set_review, export_reviews_csv


class FindingReviewMixin:
    def setup_finding_reviews(self):
        tab = self.research_tabs.tab('Bulgu inceleme')
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        filters = ctk.CTkFrame(tab, fg_color='transparent')
        filters.grid(row=0, column=0, sticky='ew', pady=(4, 8))
        filters.grid_columnconfigure(0, weight=1)
        self.review_search = ctk.CTkEntry(filters, placeholder_text='Site, kullanıcı adı, not veya etikette ara…', height=30)
        self.review_search.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.review_search.bind('<KeyRelease>', lambda _: self._render_finding_reviews())
        self.review_state_filter = ctk.CTkOptionMenu(filters, values=['Tüm incelemeler', *VIEW_STATES.values()], width=150, command=lambda _: self._render_finding_reviews())
        self.review_state_filter.grid(row=0, column=1, padx=(0, 8))
        self.review_priority_filter = ctk.CTkOptionMenu(filters, values=['Tüm öncelikler', *PRIORITIES.values()], width=135, command=lambda _: self._render_finding_reviews())
        self.review_priority_filter.grid(row=0, column=2)
        holder = ctk.CTkFrame(tab, fg_color='transparent')
        holder.grid(row=1, column=0, sticky='nsew')
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        self.review_tree = ttk.Treeview(holder, columns=('site', 'handle', 'detection', 'review', 'priority', 'tags'), show='headings', selectmode='extended', style='Trackher.Treeview', height=4)
        for name, label, width in [('site', 'PLATFORM', 160), ('handle', 'HEDEF / KULLANICI', 175),
                                   ('detection', 'TARAMA SONUCU', 160), ('review', 'ANALİST İNCELEMESİ', 160),
                                   ('priority', 'ÖNCELİK', 80), ('tags', 'ETİKETLER', 170)]:
            self.review_tree.heading(name, text=label)
            self.review_tree.column(name, width=width, minwidth=65)
        self.review_tree.grid(row=0, column=0, sticky='nsew')
        scroll = ctk.CTkScrollbar(holder, command=self.review_tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal = ctk.CTkScrollbar(holder, orientation='horizontal', command=self.review_tree.xview, height=12)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.review_tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        for state, color in [('new', '#cad8e8'), ('reviewed', '#5ce0b4'), ('rejected', '#99a9bb'), ('uncertain', '#aab3ff'), ('stale', '#f2bd70')]:
            self.review_tree.tag_configure(state, foreground=color)
        self.review_tree.bind('<Double-1>', lambda _: self._edit_finding_review())
        self.review_tree.bind('<Return>', lambda _: self._edit_finding_review())
        self.review_tree.bind('<<TreeviewSelect>>', lambda _: self._update_review_selection())
        footer = ctk.CTkFrame(tab, fg_color='transparent')
        footer.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        self.review_summary = ctk.CTkLabel(footer, text='Henüz tarama yok', text_color='#91a4ba', height=24, anchor='w')
        self.review_summary.pack(side='left')
        self.review_csv_button = ctk.CTkButton(footer, text='Görünenleri CSV', width=130, height=28, command=self._export_review_csv, fg_color='#233b52')
        self.review_csv_button.pack(side='right', padx=(8, 0))
        self.review_edit_button = ctk.CTkButton(footer, text='Not / etiket', width=100, height=28, command=self._edit_finding_review, state='disabled', fg_color='#164c5d')
        self.review_edit_button.pack(side='right', padx=(8, 0))
        self.review_batch = ctk.CTkOptionMenu(footer, values=['Seçileni işaretle', *REVIEW_STATES.values()], width=155, command=self._batch_review_state)
        self.review_batch.pack(side='right')
        self._review_visible = []

    def _render_finding_reviews(self):
        if self.__dict__.get('review_tree') is None:
            return
        scan = self._selected_case_scan()
        states = {label: key for key, label in VIEW_STATES.items()}
        priorities = {label: key for key, label in PRIORITIES.items()}
        all_rows = review_rows(self._case, scan)
        visible = review_rows(self._case, scan, query=self.review_search.get(),
                              state=states.get(self.review_state_filter.get(), 'all'),
                              priority=priorities.get(self.review_priority_filter.get(), 'all'))
        selected = set(self.review_tree.selection())
        children = self.review_tree.get_children()
        if children:
            self.review_tree.delete(*children)
        self._review_visible = visible
        for row in visible:
            review = row['review']
            self.review_tree.insert('', 'end', iid=str(row['index']),
                values=(row['site'], row['handle'], result_row(row['result'])['group'], VIEW_STATES[review['view_state']],
                        PRIORITIES[review['priority']], ', '.join(review['tags'])), tags=(review['view_state'],))
        remaining = [str(row['index']) for row in visible if str(row['index']) in selected]
        if remaining:
            self.review_tree.selection_set(remaining)
        counts = Counter(row['review']['view_state'] for row in all_rows)
        self.review_summary.configure(text=f'{len(visible)} / {len(all_rows)} bulgu · Bekleyen {counts["new"]} · Kanıtı değişen {counts["stale"]}')
        self._update_review_selection()

    def _update_review_selection(self):
        count = len(self.review_tree.selection())
        self.review_edit_button.configure(state='normal' if count == 1 else 'disabled')
        self.review_batch.configure(state='normal' if count else 'disabled')

    def _edit_finding_review(self):
        scan = self._selected_case_scan()
        selected = self.review_tree.selection()
        if not scan or len(selected) != 1:
            return
        case = self._case
        row = scan['rows'][int(selected[0])]
        review = review_for(case, scan, row)
        win = ctk.CTkToplevel(self)
        win.title('Bulgu notu ve inceleme')
        height = min(570, int(self.winfo_screenheight() / self._get_window_scaling()) - 100)
        win.geometry(f'740x{height}')
        win.minsize(600, min(height, 450))
        win.transient(self)
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=1)
        name = row.get('platform') or row.get('service') or 'Bulgu'
        ctk.CTkLabel(win, text=f'{name} · Tarama sonucu: {result_row(row)["group"]}', anchor='w', font=ctk.CTkFont(size=16, weight='bold')).grid(row=0, column=0, sticky='ew', padx=18, pady=(14, 4))
        message = 'İnceleme notu tarama sonucunu değiştirmez. Uyguladıktan sonra araştırmayı Kaydet ile dosyaya yazın.'
        if review['stale']:
            message = 'Kanıt inceleme yapılan sürümden farklı; notlar korundu. Bu sürümü inceleyip yeniden uygulayabilirsiniz.'
        ctk.CTkLabel(win, text=message, wraplength=665, anchor='w', justify='left', text_color='#f2bd70' if review['stale'] else '#91a4ba').grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 8))
        tabs = ctk.CTkTabview(win)
        tabs.grid(row=2, column=0, sticky='nsew', padx=18)
        for label in ('Not', 'Kaynak kanıtı'):
            tabs.add(label)
        notes = ctk.CTkTextbox(tabs.tab('Not'), wrap='word')
        notes.pack(fill='both', expand=True)
        notes.insert('1.0', review['notes'])
        evidence = ctk.CTkTextbox(tabs.tab('Kaynak kanıtı'), wrap='word')
        evidence.pack(fill='both', expand=True)
        self._set_box(evidence, json.dumps(row, ensure_ascii=False, indent=2))
        tags = ctk.CTkEntry(win, placeholder_text='Etiketler (virgülle)')
        tags.grid(row=3, column=0, sticky='ew', padx=18, pady=10)
        tags.insert(0, ', '.join(review['tags']))
        controls = ctk.CTkFrame(win, fg_color='transparent')
        controls.grid(row=4, column=0, sticky='ew', padx=18, pady=(0, 14))
        state = ctk.CTkOptionMenu(controls, values=list(REVIEW_STATES.values()), width=145)
        state.set(REVIEW_STATES[review['state']])
        state.pack(side='left', padx=(0, 10))
        priority = ctk.CTkOptionMenu(controls, values=list(PRIORITIES.values()), width=120)
        priority.set(PRIORITIES[review['priority']])
        priority.pack(side='left')

        def close_editor():
            win.grab_release()
            win.destroy()
            self._review_editor = None

        def apply():
            if case is not self._case:
                messagebox.showerror('Araştırma değişti', 'Bu notun araştırması artık açık değil.', parent=win)
                return
            try:
                set_review(case, scan, row, state=next(k for k, v in REVIEW_STATES.items() if v == state.get()),
                           priority=next(k for k, v in PRIORITIES.items() if v == priority.get()),
                           notes=notes.get('1.0', 'end-1c'), tags=[t.strip() for t in tags.get().split(',') if t.strip()])
            except ValueError as exc:
                messagebox.showerror('Not uygulanamadı', str(exc), parent=win)
                return
            self._render_finding_reviews()
            close_editor()

        ctk.CTkButton(controls, text='Uygula', width=100, command=apply).pack(side='right')
        ctk.CTkButton(controls, text='Vazgeç', width=90, command=close_editor, fg_color='#233b52').pack(side='right', padx=8)
        self._review_editor = {'window': win, 'notes': notes, 'tags': tags, 'state': state, 'priority': priority, 'apply': apply}
        win.protocol('WM_DELETE_WINDOW', close_editor)
        win.grab_set()

    def _batch_review_state(self, label):
        self.review_batch.set('Seçileni işaretle')
        state = next((key for key, value in REVIEW_STATES.items() if value == label), None)
        scan = self._selected_case_scan()
        if state is None or scan is None:
            return
        for selected in self.review_tree.selection():
            row = scan['rows'][int(selected)]
            review = review_for(self._case, scan, row)
            set_review(self._case, scan, row, state=state, priority=review['priority'], notes=review['notes'], tags=review['tags'])
        self._render_finding_reviews()

    def _export_review_csv(self):
        if not self._review_visible:
            self.print_to_terminal('  [i] Dışa aktarılacak görünür bulgu yok.')
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv', filetypes=[('CSV tablosu', '*.csv')])
        if path:
            try:
                export_reviews_csv(path, self._review_visible)
                self.print_to_terminal(f'  [+] {len(self._review_visible)} bulgu CSV olarak kaydedildi: {path}')
            except OSError as exc:
                messagebox.showerror('CSV kaydedilemedi', str(exc), parent=self)
