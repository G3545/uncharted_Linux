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
    if 'com.valvesoftware.Steam' in str(steam):
        command = ['flatpak', 'run', 'com.valvesoftware.Steam', '-shutdown']
    elif shutil.which('steam'):
        command = [shutil.which('steam'), '-shutdown']
    else:
        return
    subprocess.Popen(command, env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


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


# ---- The Linux launcher: a row per game with Play and Add to Steam ---------------------------

def flatpak_steam(steam):
    return 'com.valvesoftware.Steam' in str(steam)


def steam_command(steam, launcher_file, game):
    """(Exe, LaunchOptions) of the Steam shortcut that starts `game` (u1/u2/u3). Flatpak Steam runs
    in a sandbox and starts programs on the host through flatpak-spawn --host."""
    exe, options = launch_target(launcher_file)
    options = f'{options} {game}'
    if flatpak_steam(steam):
        return '/usr/bin/flatpak-spawn', f'--host "{exe}" {options}'
    return str(exe), options


def steam_logo(size, color, background):
    """The Steam logo, drawn (anti-aliased) as a PIL image: a disc with the piston, two wheels on
    a rod, cut out in the background colour."""
    from PIL import Image, ImageDraw
    scale = 4
    n = size * scale

    def rgb(value):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    image = Image.new('RGB', (n, n), rgb(background))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, n - 1, n - 1), fill=rgb(color))
    cut = rgb(background)
    big = (0.66 * n, 0.36 * n, 0.19 * n)  # x, y, radius of the large wheel
    small = (0.34 * n, 0.68 * n, 0.11 * n)
    draw.line((small[0], small[1], big[0], big[1]), fill=cut, width=int(0.12 * n))
    for x, y, r in (big, small):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=cut)
    x, y, r = big
    draw.ellipse((x - 0.55 * r, y - 0.55 * r, x + 0.55 * r, y + 0.55 * r), fill=rgb(color))
    x, y, r = small
    draw.ellipse((x - 0.45 * r, y - 0.45 * r, x + 0.45 * r, y + 0.45 * r), fill=rgb(color))
    return image.resize((size, size), Image.LANCZOS)


def launcher_class(base, ns):
    """A subclass of the launcher's Launcher (ns: the launcher module's globals): the Play page
    lists the three games, each with Play and Add to Steam, usable only when that game's
    executable is in the chosen folder."""
    _ = ns['_']
    GAMES, SURFACE, TEXT, MUTED, CARD = ns['GAMES'], ns['SURFACE'], ns['TEXT'], ns['MUTED'], ns['CARD']
    NAME, PORT_DIR, game_info = ns['NAME'], ns['PORT_DIR'], ns['game_info']
    from uncharted_widgets import PillButton

    class SteamButton(PillButton):
        """A pill button with the Steam logo before its text."""

        def draw(self):
            import tkinter.font as tkfont
            from PIL import ImageTk
            super().draw()
            c = self.canvas
            font = tkfont.Font(font=self.font)
            size = font.metrics('ascent') + self.px(2)
            gap = self.px(8)
            text_w = font.measure(self.text)
            w = text_w + size + gap + 2 * self.px(self.padding[0])
            h = int(c['height'])
            c.configure(width=w)
            disabled = self.state != 'normal'
            fill = self.colors['button_hi'] if self.hover and not disabled else self.colors['button']
            fg = self.colors['muted'] if disabled else self.colors['text']
            from uncharted_widgets import rounded_image
            c.delete('all')
            c.create_image(0, 0, anchor='nw', image=rounded_image(w, h, h // 2, fill, self.bg))
            self._logo = ImageTk.PhotoImage(steam_logo(size, fg, fill))
            x = w // 2 - (text_w + size + gap) // 2
            c.create_image(x, h // 2, anchor='w', image=self._logo)
            c.create_text(x + size + gap, h // 2, text=self.text, anchor='w', fill=fg, font=self.font)

    class LinuxLauncher(base):
        def build_play(self):
            tk = self.tk
            page = tk.Frame(self.content, bg=SURFACE)
            self.pages['play'] = page
            self.cards, self.card_images = {}, {}
            self.game_rows = {}
            shell = tk.Frame(page, bg=SURFACE)
            shell.pack(fill='both', expand=True, padx=self.px(44), pady=(self.px(30), self.px(10)))
            tk.Label(shell, text=_('Library'), bg=SURFACE, fg=TEXT, font=self.font_title).pack(anchor='w')
            tk.Label(shell, text=_('One game folder holds the whole collection. Pick a game to play.'),
                     bg=SURFACE, fg=MUTED, font=self.font_ui_sm).pack(anchor='w', pady=(self.px(4), self.px(18)))
            for number, (key, title, _subtitle, exe) in enumerate(GAMES, start=1):
                row = tk.Frame(shell, bg=CARD, highlightthickness=0)
                row.pack(fill='x', pady=(0, self.px(10)))
                text = tk.Frame(row, bg=CARD)
                text.pack(side='left', padx=self.px(18), pady=self.px(14))
                tk.Label(text, text=f'Uncharted {number}: {title}', bg=CARD, fg=TEXT,
                         font=self.font_brand_md).pack(anchor='w')
                note = tk.Label(text, text='', bg=CARD, fg=MUTED, font=self.font_ui_sm)
                note.pack(anchor='w')
                play = self.pill(row, _('Play'), lambda k=key: self.play_game(k), kind='primary',
                                 background=CARD, padding=(26, 8))
                play.pack(side='right', padx=(self.px(8), self.px(18)))
                steam = SteamButton(self.tk, row, _('Add to Steam'), lambda k=key: self.add_game_to_steam(k),
                                    ns['COLORS'], self.px, self.font_button, 'secondary', CARD, (16, 8))
                steam.pack(side='right')
                self.game_rows[key] = (play, steam, note, exe)
            row = tk.Frame(shell, bg=SURFACE)
            row.pack(fill='x', pady=(self.px(14), self.px(8)))
            self.toggle(row, self.var('fullscreen'), SURFACE).pack(side='left')
            fullscreen = tk.Label(row, text=_('Fullscreen'), bg=SURFACE, fg=TEXT, font=self.font_ui, cursor='hand2')
            fullscreen.pack(side='left', padx=(self.px(10), 0))
            fullscreen.bind('<Button-1>', lambda _e: self.var('fullscreen').set(not self.var('fullscreen').get()))
            self.pill(row, _('Desktop shortcut'), self.shortcut, background=SURFACE, padding=(14, 6)).pack(
                side='left', padx=(self.px(24), 0))
            self.ready = tk.Label(shell, text='', bg=SURFACE, fg=MUTED, font=self.font_ui_sm,
                                  wraplength=self.px(820), justify='left')
            self.ready.pack(anchor='w', pady=(0, self.px(16)))

        def refresh(self):
            super().refresh()
            info = self.info
            for key, (play, steam, note, exe) in getattr(self, 'game_rows', {}).items():
                present = bool(info) and key in info['games']
                state = 'normal' if present and not self.process else 'disabled'
                play.configure(state=state)
                steam.configure(state='normal' if present else 'disabled')
                if not info:
                    note.configure(text=_('Choose the game folder on the Game page'))
                elif present:
                    note.configure(text=_('Ready'))
                else:
                    note.configure(text=_('{} is not in the game folder').format(exe))

        def available(self, key):
            """The game's executable is in the chosen folder (else a message says what is missing)."""
            self.collect()
            info = game_info(self.app['game_dir'])
            if not info:
                self.messagebox.showerror(NAME, _('Choose the game folder with eboot.bin on the Game page first.'))
                self.show('game')
                return False
            if key not in info['games']:
                exe = next(e for k, _t, _s, e in GAMES if k == key)
                self.messagebox.showerror(NAME, _('{} is not in the game folder, so this game cannot start.').format(exe))
                return False
            return True

        def play_game(self, key):
            if self.available(key):
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
            for key, *_rest in GAMES:
                if key in (self.info or {}).get('games', []):
                    self.add_game_to_steam(key)

        def add_game_to_steam(self, key):
            """This game in the Steam library (a non-Steam game started with the settings saved
            in this launcher), only when its executable is in the game folder."""
            if not self.available(key):
                return
            import bbport_steam
            steam = steam_folder()
            configs = bbport_steam.user_configs(steam) if steam else []
            if not configs:
                self.messagebox.showerror(NAME, _('Steam was not found on this PC (or nobody has signed in to it yet).'))
                return
            number, title = next((n, t) for n, (k, t, _s, _e) in enumerate(GAMES, start=1) if k == key)
            name = f'Uncharted {number}: {title}'
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
            exe, options = steam_command(steam, ns['__file__'], key)
            # The icon install.sh puts in place (the AppImage's own files are gone once it closes).
            icon = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / \
                'icons' / 'hicolor' / '256x256' / 'apps' / 'uncharted-linux.png'
            if not icon.is_file() and not os.environ.get('APPIMAGE'):
                icon = Path(PORT_DIR) / 'launcher' / 'uncharted.png'
            start_dir = Path(os.environ.get('APPIMAGE') or sys.executable).parent
            try:
                for config in configs:
                    bbport_steam.add_shortcut(config / 'shortcuts.vdf', name, exe, str(start_dir),
                                              str(icon) if icon.is_file() else '', options, match_options=True)
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
            self.messagebox.showinfo(NAME, _('{} is in your Steam library. It starts with the settings saved '
                                             'in this launcher.').format(name))

    return LinuxLauncher


def font_scale(root):
    """How much larger fonts are drawn than Tk's screen DPI says: KDE/GNOME scaling under
    XWayland sets Xft.dpi (206 at 215 %) while X reports 96 DPI, and Xft draws every font at
    Xft.dpi. The layout is scaled by the same factor so the text fits."""
    try:
        x11 = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XResourceManagerString.restype = ctypes.c_char_p
        x11.XResourceManagerString.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        display = x11.XOpenDisplay(None)
        if not display:
            return 1.0
        try:
            resources = (x11.XResourceManagerString(display) or b'').decode(errors='replace')
        finally:
            x11.XCloseDisplay(display)
        dpi = next((float(line.split(':', 1)[1]) for line in resources.splitlines()
                    if line.split(':', 1)[0].strip() == 'Xft.dpi'), None)
        scale = dpi / root.winfo_fpixels('1i') if dpi else 1.0
    except (OSError, ValueError, AttributeError):
        return 1.0
    return scale if 1.1 <= scale <= 4.0 else 1.0
