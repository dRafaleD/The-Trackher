"""Public-source research controls, using the existing results and case workspace."""
import asyncio

from gui.widgets.common import ctk
from osint.intelligence import RESEARCH_MODES, normalize_target, research_public


class IntelligenceTabMixin:
    def setup_intelligence_controls(self, parent):
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.grid(row=4, column=0, columnspan=5, sticky='ew', padx=20, pady=(0, 10))
        row.grid_columnconfigure(2, weight=1)
        self.intelligence_mode = ctk.CTkOptionMenu(row, values=list(RESEARCH_MODES.values()), width=235,
                                                   fg_color='#23374b', button_color='#304b65')
        self.intelligence_mode.grid(row=0, column=0, sticky='w')
        self.btn_intelligence = ctk.CTkButton(row, text='Kaynakları araştır', width=145,
                                             command=self.start_intelligence_research, fg_color='#164c5d')
        self.btn_intelligence.grid(row=0, column=1, padx=10)
        ctk.CTkLabel(row, text='İlk üçü: alan adı · Bahsedilme: marka / kurum adı',
                     text_color='#91a4ba', wraplength=320, justify='left').grid(row=0, column=2, sticky='w')

    def start_intelligence_research(self):
        if self.__dict__.get('_scan_active'):
            return
        kind = next(k for k, label in RESEARCH_MODES.items() if label == self.intelligence_mode.get())
        try:
            target = normalize_target(kind, self.osint_entry.get())
        except ValueError as exc:
            self.print_to_terminal(f'  [!] {exc}')
            return
        self._prepare_scan_context(kind, target)
        self._begin_scan_results(1, RESEARCH_MODES[kind])
        self.print_to_terminal(f'  [i] {RESEARCH_MODES[kind]}: {target}')
        self.run_in_thread(self.do_intelligence_research, kind, target)

    def do_intelligence_research(self, kind, target):
        try:
            rows = asyncio.run(research_public(kind, target, control=self.__dict__.get('_scan_control'),
                              on_result=lambda row: self.post_ui(self._receive_scan_result, row)))
            self.post_ui(self._complete_scan_results, rows)
            self.print_to_terminal(f'  [i] {RESEARCH_MODES[kind]} tamamlandı · {len(rows)} kaynak / bulgu satırı')
        finally:
            self.post_ui(self._release_scan_results)

    def _render_case_timeline(self):
        from utils.research import case_timeline
        lines = ['KAYNAKLI ZAMAN ÇİZELGESİ',
                 'Yayın / arşiv tarihi ile toplama zamanı ayrı gösterilir. Eşleşmeler sahiplik kanıtı değildir.', '']
        for event in case_timeline(self._case):
            meaning = {'archive': 'Arşiv kaydı', 'published': 'Yayın tarihi', 'certificate': 'Sertifika kaydı',
                       'source': 'Kaynak tarihi', 'collected': 'Toplama zamanı'}.get(event['time_kind'], event['time_kind'])
            lines.append(f"{event['time']} · {meaning} · {event['target']}\n"
                         f"  {event['title']}\n  {event.get('url', '')}\n"
                         f"  Kaynak: {event.get('source_url', '')}\n  Toplandı: {event.get('checked_at', '')}\n")
        if len(lines) == 3:
            lines.append('Henüz tarihli bir bulgu yok.')
        self._set_box(self.timeline_box, '\n'.join(lines))
