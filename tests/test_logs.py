"""The launcher's log and bug reports (launcher/uncharted_logs.py) and the menu entry's
Create bug report action (launcher/uncharted_linux.py).
Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from paths import ROOT

if str(ROOT / 'launcher') not in sys.path:
    sys.path.insert(0, str(ROOT / 'launcher'))
import uncharted_linux as linux
import uncharted_logs as logs


class LogTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.data, self.saves = self.dir / 'data', self.dir / 'saves'
        (self.data / 'logs').mkdir(parents=True)
        self.saves.mkdir()
        # Plenty of space, whatever the test machine's temporary folder has.
        usage = mock.patch.object(logs.shutil, 'disk_usage', return_value=mock.Mock(free=100 << 30))
        self.disk = usage.start()
        self.addCleanup(usage.stop)

    def write(self, name, text):
        (self.data / 'logs' / name).write_text(text, encoding='utf-8')

    def test_rotate_keeps_five(self):
        folder = self.data / 'logs'
        for run in range(7):
            logs.rotate(folder)
            (folder / 'launcher.log').write_text(f'run {run}')
        names = sorted(p.name for p in folder.iterdir())
        self.assertEqual(names, ['launcher.1.log', 'launcher.2.log', 'launcher.3.log', 'launcher.4.log', 'launcher.log'])
        self.assertEqual((folder / 'launcher.4.log').read_text(), 'run 2')

    def test_health_finds_crash_hang_and_unclean_exit(self):
        (self.saves / 'last_run.log').write_text('Run: x\nSTOP: bad thing\n')
        self.write('launcher.log', '== Uncharted launcher\n')
        self.write('launcher.1.log', f'== Uncharted launcher\n[ 3.0s] {logs.NOT_RESPONDING} for 10 s\n')
        found = logs.health(self.data, self.saves, linux.crash_signature)
        self.assertEqual(len(found), 3)
        self.assertIn('STOP: bad thing', found[0])
        self.assertIn('stopped responding', found[1])
        self.assertIn('did not close normally', found[2])

    def test_health_quiet_after_a_normal_session(self):
        self.write('launcher.1.log', f'== Uncharted launcher\n[ 9.0s] {logs.CLOSED} normally\n')
        self.assertEqual(logs.health(self.data, self.saves, linux.crash_signature), [])

    def test_health_warns_about_little_disk_space(self):
        self.disk.return_value = mock.Mock(free=2 << 30)
        self.assertEqual(logs.health(self.data, self.saves, linux.crash_signature),
                         ['Only 2.0 GB free where the launcher keeps its data.'])

    def test_huge_game_log_is_read_from_its_end(self):
        log = self.saves / 'last_run.log'
        with open(log, 'w') as f:
            f.write('spam every frame\n' * 200000)  # 3.4 MB
            f.write('STOP: the real crash\n')
        signature, text = linux.crash_signature(log)
        self.assertEqual(signature, 'STOP: the real crash')
        self.assertLessEqual(len(text), 1 << 20)
        with mock.patch.object(logs, 'REPORT_LOG_BYTES', 1 << 20):
            path = logs.create_report(self.data, self.saves, {}, self.dir, 'v', linux.crash_signature, folder=self.dir)
        with zipfile.ZipFile(path) as report:
            kept = report.read('game/last_run.log').decode()
        self.assertIn('middle left out', kept)
        self.assertTrue(kept.rstrip().endswith('STOP: the real crash'))

    def test_private_removes_home_and_user(self):
        home = str(Path.home())
        with mock.patch('getpass.getuser', return_value='kamadha'):
            text = logs.private(f'{home}/Games/x and /run/media/kamadha/disk and Steam Deck kamadha')
        self.assertNotIn(home, text)
        self.assertIn('~/Games/x', text)
        self.assertIn('/run/media/<user>/disk', text)
        self.assertTrue(text.endswith('kamadha'))  # only paths are changed

    def test_report_holds_logs_system_and_settings(self):
        (self.saves / 'last_run.log').write_text(f'Run: {Path.home()}/game\n')
        self.write('launcher.log', '== Uncharted launcher\n')
        path = logs.create_report(self.data, self.saves, {'game_dir': str(Path.home() / 'g'), 'frame_rate': '60'},
                                  self.dir, '0.3.6-linux.99', linux.crash_signature, folder=self.dir)
        with zipfile.ZipFile(path) as report:
            names = set(report.namelist())
            self.assertTrue({'system.txt', 'health.txt', 'settings.json', 'launcher/launcher.log',
                             'game/last_run.log'} <= names)
            self.assertNotIn(str(Path.home()), report.read('settings.json').decode())
            self.assertIn('~/game', report.read('game/last_run.log').decode())
            self.assertIn('0.3.6-linux.99', report.read('system.txt').decode())


class DialogLogTests(unittest.TestCase):
    def test_dialogs_and_answers_are_logged(self):
        box = mock.Mock(spec=['askyesno', 'showinfo', 'YES'])
        box.askyesno.return_value = True
        box.YES = 'yes'
        notes = []
        with mock.patch.object(logs, 'note', notes.append):
            logged = logs.logged_dialogs(box)
            self.assertTrue(logged.askyesno('Uncharted', 'Open a crash report?'))
        self.assertEqual(logged.YES, 'yes')
        self.assertEqual(notes, ["Dialog askyesno: 'Open a crash report?'", 'Dialog askyesno answered: True'])


class AutoReportTests(unittest.TestCase):
    def test_made_once_after_the_delay(self):
        made = []
        with mock.patch.object(logs.atexit, 'register'):
            logs.auto_report(lambda: made.append(1), after=0.05)
            import time
            time.sleep(0.3)
            logs._auto_report()  # the exit or a hang afterwards: no second report
        self.assertEqual(made, [1])
        logs._auto_report = None


class ReportActionTests(unittest.TestCase):
    def test_existing_entry_gets_the_action_once(self):
        data = Path(tempfile.mkdtemp())
        entry = data / 'applications' / 'uncharted-linux.desktop'
        entry.parent.mkdir()
        entry.write_text('[Desktop Entry]\nType=Application\nName=Uncharted\nExec="/a/Uncharted.AppImage"\n')
        env = {'APPIMAGE': '/a/Uncharted.AppImage', 'XDG_DATA_HOME': str(data)}
        with mock.patch.dict(os.environ, env), mock.patch.object(linux, 'desktop_folder', return_value=None):
            linux.add_report_action()
            linux.add_report_action()
        text = entry.read_text()
        self.assertEqual(text.count('[Desktop Action report]'), 1)
        self.assertIn('Actions=report;', text)
        self.assertIn('Exec="/a/Uncharted.AppImage" --report', text)

    def test_entry_of_another_copy_is_left_alone(self):
        data = Path(tempfile.mkdtemp())
        entry = data / 'applications' / 'uncharted-linux.desktop'
        entry.parent.mkdir()
        entry.write_text('[Desktop Entry]\nExec="/other/Uncharted.AppImage"\n')
        env = {'APPIMAGE': '/a/Uncharted.AppImage', 'XDG_DATA_HOME': str(data)}
        with mock.patch.dict(os.environ, env), mock.patch.object(linux, 'desktop_folder', return_value=None):
            linux.add_report_action()
        self.assertNotIn('report', entry.read_text())


if __name__ == '__main__':
    unittest.main()
