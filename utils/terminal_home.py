"""Trackher's terminal-only visual boot and bounded, explicit action menu."""
import os
import platform
import sys
import time

from rich import box
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


GREEN = '#68d342'
MUTED = '#8b9aaa'
BODY = '#dde5ee'
RADAR = (
    '       .-----------.       ',
    '     /    .-----.    \\     ',
    '    /   /    |    \\   \\    ',
    '   |   |  .--+--.  |   |   ',
    '   |---+--|  o--+--*---|   ',
    '   |   |  \\--+--/  |   |   ',
    '    \\   \\    |    /   /    ',
    '     \\    `-----\'    /     ',
    '       `-----------\'       ',
)
WORDMARK = (
    r' _____ ____      _    ____ _  ___   _ _____ ____  ',
    r'|_   _|  _ \    / \  / ___| |/ / | | | ____|  _ \ ',
    r"  | | | |_) |  / _ \| |   | ' /| |_| |  _| | |_) |",
    r'  | | |  _ <  / ___ \ |___| . \|  _  | |___|  _ < ',
    r'  |_| |_| \_\/_/   \_\____|_|\_\_| |_|_____|_| \_\ ',
)
CHOICES = {
    '1': ('Kullanıcı adı', '--username', 'Kullanıcı adı'),
    '2': ('E-posta', '--email', 'E-posta adresi'),
    '3': ('Alan adı', '--domain', 'Alan adı (example.com)'),
    '4': ('Web geçmişi', '--web-history', 'Alan adı (example.com)'),
    '5': ('Marka adayları', '--brand-research', 'Markanın alan adı'),
    '6': ('Kurum bağlantıları', '--organization', 'Kurumun alan adı'),
    '7': ('Bahsedilme', '--mentions', 'Marka veya kurum adı'),
    '8': ('Platform sağlığı', '--health-check', None),
    '9': ('Grafik arayüz', '--gui', None),
}


def interactive(console):
    return bool(console.is_terminal and sys.stdin.isatty() and not console.is_dumb_terminal)


def animation_enabled(console, no_animation=False):
    return (interactive(console) and console.size.width >= 60 and console.size.height >= 22
            and not no_animation and not console.no_color
            and 'NO_COLOR' not in os.environ and 'TRACKHER_NO_ANIMATION' not in os.environ
            and os.environ.get('TERM') != 'dumb')


def compose_home(console, version, username_count, email_count):
    """Fit the same information to wide, short and narrow terminals."""
    width = min(console.size.width, 108)
    tall = console.size.height >= 35
    narrow = width < 68
    hero = Table.grid(padding=(0, 3))
    if not narrow and console.size.height >= 22:
        hero.add_column(no_wrap=True)
    hero.add_column()
    info = Text(style=BODY)
    info.append(f'trackher@local  v{version}\n', style=f'bold {GREEN}')
    info.append('─' * 30 + '\n', style='#3e5d44')
    details = [('Araç', 'Digital Footprint & Privacy Toolkit'),
               ('Sistem', f'{platform.system()} / {platform.machine()}'),
               ('Runtime', f'Python {platform.python_version()}'),
               ('Katalog', f'{username_count} platforms / {email_count} services'),
               ('Mod', 'Açık kaynak OSINT'),
               ('Kanıt', 'Kaynak / ilişki / zaman çizelgesi')]
    for label, value in details:
        info.append(f'{label:<8}', style=f'bold {GREEN}')
        info.append(value + '\n', style=BODY)
    for color in ('#33414d', '#3e5d44', GREEN, '#73c7e8', '#c2a6f1', '#e7bd72'):
        info.append('██', style=color)
    if len(hero.columns) == 2:
        emblem = Text('\n'.join(RADAR), style=GREEN)
        hero.add_row(emblem, info)
    else:
        hero.add_row(info)
    title = Text('TRACKHER', style=f'bold {GREEN}')
    brand = Text('\n'.join(WORDMARK), style=f'bold {GREEN}') if tall and width >= 74 else Text('T R A C K H E R', style=f'bold {GREEN}')
    body = Group(brand, Text(''), hero) if tall else hero
    header = Panel(body, title=title, subtitle=Text('PUBLIC SOURCE INTELLIGENCE', style=MUTED),
                   border_style='#3e5d44', box=box.ROUNDED, padding=(0, 1), width=width)
    menu = Table.grid(expand=True, padding=(0, 2))
    menu.add_column(ratio=1)
    if not narrow:
        menu.add_column(ratio=1)
    entries = []
    for key, (label, _, _) in CHOICES.items():
        color = '#73c7e8' if int(key) <= 3 else '#c2a6f1' if int(key) <= 7 else '#e7bd72'
        text = Text(f'[{key}] ', style=f'bold {color}')
        text.append(label, style=BODY)
        entries.append(text)
    entries.append(Text('[0] Çıkış    [?] Yardım', style=MUTED))
    if narrow:
        for entry in entries:
            menu.add_row(entry)
    else:
        for i in range(5):
            menu.add_row(entries[i], entries[i + 5])
    actions = Panel(menu, title=Text('ANA MENÜ', style=f'bold {GREEN}'), border_style='#33414d',
                    box=box.ROUNDED, padding=(0, 1), width=width)
    footer = Text('trackher --help  ·  trackher --gui  ·  --no-animation\n', style=MUTED)
    footer.append('trackher@osint ~ $', style=f'bold {GREEN}')
    return Group(header, actions, footer)


def play_boot(console, screen, *, frames=22, duration=1.25):
    """Cosmetic scan/decode sweep; never implies that a network scan ran."""
    lines = console.render_lines(screen, console.options, pad=False)
    if len(lines) >= console.size.height:
        return
    plain = [''.join(segment.text for segment in line) for line in lines]
    with Live(console=console, auto_refresh=False, transient=True, vertical_overflow='crop') as live:
        for frame in range(frames):
            head = int(frame * (len(plain) + 4) / max(frames - 1, 1))
            text = Text()
            for index, line in enumerate(plain):
                if index < head - 2:
                    text.append(line + '\n', style=GREEN if index < 3 else BODY)
                elif index <= head:
                    decoded = ''.join(c if c.isspace() or (pos + frame) % 4 == 0 else '.:+01'[(pos + index + frame) % 5]
                                      for pos, c in enumerate(line))
                    text.append(decoded + '\n', style='#bcff9a')
                else:
                    text.append(' ' * len(line) + '\n')
            live.update(text, refresh=True)
            time.sleep(duration / frames)


def show_home(console, version, username_count, email_count, *, no_animation=False):
    screen = compose_home(console, version, username_count, email_count)
    if animation_enabled(console, no_animation):
        play_boot(console, screen)
    console.print(screen)


def run_menu(console, execute, *, redraw, read=None):
    """Only fixed argv lists are dispatched; user input is never a shell command."""
    if not interactive(console):
        return
    if read is None:
        read = console.input
    try:
        while True:
            choice = read('[bold #68d342]trackher › [/]').strip().lower()
            if choice in ('0', 'q', 'quit', 'exit', 'çıkış'):
                return
            if choice in ('?', 'h', 'help', 'yardım'):
                command = ['--help']
            elif choice in CHOICES:
                _, flag, prompt = CHOICES[choice]
                command = [flag, '--no-animation', '--no-banner']
                if prompt:
                    value = read(prompt + ': ').strip()
                    if not value:
                        continue
                    command = [flag, value, '--no-animation', '--no-banner']
            else:
                console.print('1–9 arasında seçim yapın; yardım için ?, çıkış için 0.', style=MUTED)
                continue
            try:
                execute(command)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    console.print('İşlem tamamlanamadı; yukarıdaki açıklamayı inceleyin.', style='#e7bd72')
            read('\nAna menü için Enter…')
            redraw()
    except (EOFError, KeyboardInterrupt):
        console.print()
