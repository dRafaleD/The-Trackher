"""Presentation cannot run hidden actions or animate redirected output."""
import io
import os
import unittest
from unittest.mock import Mock, patch

from rich.console import Console

from utils.terminal_home import animation_enabled, compose_home, play_boot, run_menu, show_home, CHOICES


class TerminalHomeTests(unittest.TestCase):
    def console(self, width=90, height=30, tty=False):
        with patch.dict(os.environ, {}, clear=True):
            return Console(file=io.StringIO(), width=width, height=height, force_terminal=tty,
                           no_color=False, color_system='truecolor' if tty else None)

    def test_non_terminal_never_animates_or_reads_input(self):
        console = self.console()
        with patch('utils.terminal_home.play_boot') as animation:
            show_home(console, 'test', '303', '111')
        animation.assert_not_called()
        self.assertNotIn('\x1b', console.file.getvalue())
        read = Mock()
        run_menu(console, Mock(), redraw=Mock(), read=read)
        read.assert_not_called()

    def test_animation_obeys_flags_environment_and_small_terminal(self):
        console = self.console(tty=True)
        with patch('utils.terminal_home.sys.stdin.isatty', return_value=True), patch.dict(os.environ, {}, clear=True):
            self.assertTrue(animation_enabled(console))
            self.assertFalse(animation_enabled(console, True))
            for name in ('NO_COLOR', 'TRACKHER_NO_ANIMATION'):
                with patch.dict(os.environ, {name: ''}):
                    self.assertFalse(animation_enabled(console))
            with patch.dict(os.environ, {'TERM': 'dumb'}):
                self.assertFalse(animation_enabled(console))
            self.assertFalse(animation_enabled(self.console(width=45, tty=True)))

    def test_menu_uses_literal_fixed_argv_and_returns_after_action(self):
        console = self.console(tty=True)
        execute, redraw = Mock(), Mock()
        read = Mock(side_effect=['1', '$(literal); & name', '', '0'])
        with patch('utils.terminal_home.interactive', return_value=True):
            run_menu(console, execute, redraw=redraw, read=read)
        execute.assert_called_once_with(['--username', '$(literal); & name', '--no-animation', '--no-banner'])
        redraw.assert_called_once_with()

    def test_each_menu_option_parses_with_the_existing_cli(self):
        from main import build_parser
        parser = build_parser()
        for _, flag, prompt in CHOICES.values():
            parsed = parser.parse_args([flag, 'sample.example'] if prompt else [flag])
            self.assertIsNotNone(parsed)

    def test_menu_recovers_from_bad_choice_cancel_and_action_error(self):
        console = self.console(tty=True)
        execute = Mock(side_effect=SystemExit(2))
        read = Mock(side_effect=['wrong', '3', '', '8', '', EOFError()])
        with patch('utils.terminal_home.interactive', return_value=True):
            run_menu(console, execute, redraw=Mock(), read=read)
        execute.assert_called_once_with(['--health-check', '--no-animation', '--no-banner'])

    def test_layout_fits_width_and_includes_new_research_modules(self):
        for width in (42, 68, 90, 120):
            console = self.console(width)
            console.print(compose_home(console, 'test', '303', '111'))
            text = console.file.getvalue()
            self.assertLessEqual(max(map(len, text.splitlines())), width)
            for label in ('TRACKHER', 'ANA MENÜ', 'Bahsedilme', 'Web geçmişi'):
                self.assertIn(label, text)

    def test_boot_restores_cursor_on_interruption(self):
        console = self.console(90, 35, tty=True)
        screen = compose_home(console, 'test', '303', '111')
        with patch.dict(os.environ, {}, clear=True), patch('utils.terminal_home.time.sleep', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            play_boot(console, screen)
        self.assertIn('\x1b[?25h', console.file.getvalue())

    def test_explicit_menu_refuses_to_discard_scan_arguments(self):
        import main
        with self.assertRaises(SystemExit) as raised:
            main.main(['--menu', '--username', 'sample'])
        self.assertEqual(raised.exception.code, 2)
