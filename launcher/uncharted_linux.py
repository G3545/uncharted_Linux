# SPDX-License-Identifier: GPL-2.0-or-later
"""Linux and Steam Deck counterparts of the launcher's Windows calls (this fork's additions).

Kept apart from uncharted_launcher.py so that changes from the Windows project merge cleanly:
the launcher only calls into this module where it would otherwise call a Windows API.
"""
import ctypes
import ctypes.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

APP_ID = 'uncharted-linux'
TITLE = 'Uncharted: The Nathan Drake Collection'


def config_dir():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'uncharted-launcher'


def steam_deck():
    """SteamOS (the Steam Deck and other SteamOS devices)."""
    try:
        return 'ID=steamos' in Path('/etc/os-release').read_text()
    except OSError:
        return False


def clean_env():
    """The environment for programs outside this one: a frozen launcher (PyInstaller) points
    LD_LIBRARY_PATH at its own libraries, which xdg-open or Steam must not get."""
    env = dict(os.environ)
    original = env.pop('LD_LIBRARY_PATH_ORIG', None)
    if getattr(sys, 'frozen', False):
        env.pop('LD_LIBRARY_PATH', None)
        if original:
            env['LD_LIBRARY_PATH'] = original
    return env


def open_path(target):
    """A folder or URL in the desktop's default program."""
    subprocess.Popen(['xdg-open', str(target)], env=clean_env(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def add_font(path):
    """Makes a bundled TTF available to Tk (fontconfig, this process only); before Tk() starts."""
    try:
        library = ctypes.CDLL(ctypes.util.find_library('fontconfig') or 'libfontconfig.so.1')
        library.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.FcConfigAppFontAddFile(None, str(path).encode())
    except (OSError, AttributeError):
        pass


def set_icon(root, tk):
    """The window icon from launcher/uncharted.png (Tk on X11/Wayland does not read .ico)."""
    for folder in (Path(getattr(sys, '_MEIPASS', '')), Path(__file__).resolve().parent):
        png = folder / 'uncharted.png'
        if png.is_file():
            try:
                root._icon = tk.PhotoImage(file=str(png))
                root.iconphoto(True, root._icon)
            except tk.TclError:
                pass
            return


class GameJob:
    """run.py and everything it starts in one process group, so Stop ends all of them."""

    popen_options = {'start_new_session': True}

    def __init__(self, process):
        self.pgid = process.pid

    def terminate(self):
        if self.pgid:
            try:
                os.killpg(self.pgid, signal.SIGTERM)
            except OSError:
                pass

    def close(self):
        self.pgid = None


def wait_for(pid, seconds=60):
    for _ in range(int(seconds * 10)):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)


# ---- Steam ----------------------------------------------------------------------------------

def steam_folder():
    """Steam's data folder (native, the Steam Deck, or the Flatpak), or None."""
    home = Path.home()
    for candidate in (home / '.steam' / 'steam', home / '.local' / 'share' / 'Steam',
                      home / '.var' / 'app' / 'com.valvesoftware.Steam' / '.local' / 'share' / 'Steam'):
        if (candidate / 'userdata').is_dir():
            return candidate.resolve()
    return None


def steam_running():
    result = subprocess.run(['pgrep', '-x', 'steam'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def steam_shutdown(steam):
    command = shutil.which('steam')
    if command:
        subprocess.Popen([command, '-shutdown'], env=clean_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    elif str(steam).find('com.valvesoftware.Steam') >= 0:
        subprocess.Popen(['flatpak', 'run', 'com.valvesoftware.Steam', '-shutdown'], env=clean_env(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def launch_target(launcher_file):
    """(program, launch options) that start the game with the saved settings: the packaged
    Uncharted binary, else this Python with the launcher script."""
    if os.environ.get('APPIMAGE'):
        return Path(os.environ['APPIMAGE']), '--play'
    if getattr(sys, 'frozen', False):
        return Path(sys.executable), '--play'
    return Path(sys.executable), f'"{Path(launcher_file).resolve()}" --play'


# ---- Desktop entry --------------------------------------------------------------------------

def desktop_entry(launcher_file, port_dir):
    """Uncharted in the application menu and on the desktop (a .desktop file)."""
    if os.environ.get('APPIMAGE'):
        command = f'"{os.environ["APPIMAGE"]}"'
    elif getattr(sys, 'frozen', False):
        command = f'"{sys.executable}"'
    else:
        command = f'"{sys.executable}" "{Path(launcher_file).resolve()}"'
    icon = Path(port_dir) / 'launcher' / 'uncharted.png'
    if not icon.is_file():
        icon = Path(getattr(sys, '_MEIPASS', port_dir)) / 'uncharted.png'
    text = ('[Desktop Entry]\nType=Application\nName=Uncharted\n'
            f'Comment={TITLE} for Linux\nExec={command}\nPath={port_dir}\nIcon={icon}\n'
            'Terminal=false\nCategories=Game;\n')
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    written = []
    for folder in (data / 'applications', desktop_folder()):
        if folder and folder.is_dir() or folder == data / 'applications':
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'{APP_ID}.desktop'
            path.write_text(text, encoding='utf-8')
            path.chmod(0o755)
            written.append(path)
    return written


def desktop_folder():
    try:
        result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, env=clean_env())
        folder = Path(result.stdout.strip())
        if result.returncode == 0 and folder != Path.home() and folder.is_dir():
            return folder
    except OSError:
        pass
    folder = Path.home() / 'Desktop'
    return folder if folder.is_dir() else None


# ---- The Linux launcher: plain game buttons, one Steam entry per game -------------------------

def launcher_class(base, ns):
    """A subclass of the launcher's Launcher (ns: the launcher module's globals) whose Play page
    has a button per game instead of the artwork, and whose Add to Steam adds each game."""
    _ = ns['_']
    GAMES, SURFACE, TEXT, MUTED, CARD = ns['GAMES'], ns['SURFACE'], ns['TEXT'], ns['MUTED'], ns['CARD']
    NAME = ns['NAME']

    class LinuxLauncher(base):
        def build_play(self):
            tk = self.tk
            page = tk.Frame(self.content, bg=SURFACE)
            self.pages['play'] = page
            self.cards, self.card_images, self.game_buttons = {}, {}, {}
            shell = tk.Frame(page, bg=SURFACE)
            shell.pack(fill='both', expand=True, padx=self.px(44), pady=(self.px(30), self.px(10)))
            tk.Label(shell, text=_('Library'), bg=SURFACE, fg=TEXT, font=self.font_title).pack(anchor='w')
            tk.Label(shell, text=_('One game folder holds the whole collection. Pick a game to play.'),
                     bg=SURFACE, fg=MUTED, font=self.font_ui_sm).pack(anchor='w', pady=(self.px(4), self.px(18)))
            for number, (key, title, subtitle, _exe) in enumerate(GAMES, start=1):
                row = tk.Frame(shell, bg=CARD, highlightthickness=0)
                row.pack(fill='x', pady=(0, self.px(10)))
                text = tk.Frame(row, bg=CARD)
                text.pack(side='left', padx=self.px(18), pady=self.px(14))
                tk.Label(text, text=f'Uncharted {number}: {title}', bg=CARD, fg=TEXT,
                         font=self.font_brand_md).pack(anchor='w')
                tk.Label(text, text=subtitle.split('·')[-1].strip(), bg=CARD, fg=MUTED, font=self.font_ui_sm).pack(anchor='w')
                button = self.pill(row, _('Play'), lambda k=key: self.play_game(k), kind='primary',
                                   background=CARD, padding=(26, 8))
                button.pack(side='right', padx=self.px(18))
                self.game_buttons[key] = button
            row = tk.Frame(shell, bg=SURFACE)
            row.pack(fill='x', pady=(self.px(14), self.px(8)))
            self.toggle(row, self.var('fullscreen'), SURFACE).pack(side='left')
            fullscreen = tk.Label(row, text=_('Fullscreen'), bg=SURFACE, fg=TEXT, font=self.font_ui, cursor='hand2')
            fullscreen.pack(side='left', padx=(self.px(10), 0))
            fullscreen.bind('<Button-1>', lambda _e: self.var('fullscreen').set(not self.var('fullscreen').get()))
            self.pill(row, _('Add to Steam'), self.add_to_steam, background=SURFACE, padding=(14, 6)).pack(
                side='left', padx=(self.px(24), 0))
            self.pill(row, _('Desktop shortcut'), self.shortcut, background=SURFACE, padding=(14, 6)).pack(
                side='left', padx=(self.px(8), 0))
            self.ready = tk.Label(shell, text='', bg=SURFACE, fg=MUTED, font=self.font_ui_sm,
                                  wraplength=self.px(820), justify='left')
            self.ready.pack(anchor='w', pady=(0, self.px(16)))

        def play_game(self, key):
            self.var('start').set(key)
            self.play()

        # No artwork on this page.
        def draw_hero(self):
            pass

        def draw_card(self, key):
            pass

        def fit_posters(self, _event=None):
            pass

        def add_to_steam(self):
            """Uncharted 1, 2 and 3 in the Steam library, one non-Steam game each, started with
            the settings saved in this launcher."""
            import bbport_steam
            steam = steam_folder()
            configs = bbport_steam.user_configs(steam) if steam else []
            if not configs:
                self.messagebox.showerror(NAME, _('Steam was not found on this PC (or nobody has signed in to it yet).'))
                return
            self.collect()
            info = self.info or {}
            games = [(number, key, title) for number, (key, title, _s, _e) in enumerate(GAMES, start=1)
                     if key in info.get('games', [key for key, *_r in GAMES])]
            exe, options = launch_target(ns['__file__'])
            restart = False
            if steam_running():
                if not self.messagebox.askyesno(NAME, _('Steam has to close while the game is added; it starts '
                                                        'again afterwards. Close Steam now?')):
                    return
                steam_shutdown(steam)
                for _i in range(60):
                    time.sleep(0.5)
                    if not steam_running():
                        break
                else:
                    self.messagebox.showerror(NAME, _('Steam did not close. Close it yourself and try again.'))
                    return
                time.sleep(1)
                restart = True
            icon = Path(ns['PORT_DIR']) / 'launcher' / 'uncharted.png'
            try:
                for config in configs:
                    for number, key, title in games:
                        name = f'Uncharted {number}: {title}'
                        bbport_steam.add_shortcut(config / 'shortcuts.vdf', name, str(exe), str(Path(exe).parent),
                                                  str(icon) if icon.is_file() else str(exe), f'{options} {key}',
                                                  match_name=True)
                        try:  # library pictures from the player's own game folder
                            import uncharted_art
                            uncharted_art.steam_artwork(self.app['game_dir'], config / 'grid',
                                                        bbport_steam.shortcut_id(f'"{exe}"', name))
                        except Exception:
                            pass
            except (OSError, ValueError) as error:
                self.messagebox.showerror(NAME, _('Could not add the game to Steam: {}').format(error))
                return
            if restart:
                open_path('steam://open/games')
            self.messagebox.showinfo(NAME, _('Uncharted 1, 2 and 3 are in your Steam library. They start with '
                                             'the settings saved in this launcher.'))

    return LinuxLauncher
