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
import threading
import time

APP_ID = 'uncharted-linux'

# The packaged Python and OpenSSL come from Debian and look for certificates in /usr/lib/ssl,
# which Fedora and others do not have: every HTTPS request (update check) failed there. Point
# them, and the game (online play), at the system's bundle.
if not os.environ.get('SSL_CERT_FILE'):
    for _bundle in ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt',
                    '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem', '/etc/ssl/cert.pem',
                    '/etc/ssl/ca-bundle.pem'):
        if os.path.isfile(_bundle):
            os.environ['SSL_CERT_FILE'] = _bundle
            break
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


# ---- Updates --------------------------------------------------------------------------------

def install_appimage(url, target):
    """Downloads the AppImage at `url` next to `target` and puts it in its place (a rename: the
    running AppImage keeps its own mounted copy until it closes)."""
    import urllib.request
    part = target.with_name(target.name + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'uncharted-linux-launcher'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(part, 'wb') as out:
            expected = int(response.headers.get('Content-Length') or 0)
            shutil.copyfileobj(response, out, 1 << 20)
        size = part.stat().st_size
        with open(part, 'rb') as check:
            magic = check.read(4)
        if magic != b'\x7fELF' or size < (1 << 20) or (expected and size != expected):
            raise ValueError('the download is incomplete')
        part.chmod(0o755)
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)


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


REPO_URL = 'https://github.com/spacepepperoni/uncharted_Linux'


def icon_image(name, size, color, background):
    """launcher/icons/<name>.png (white on transparent: Simple Icons, CC0) in `color` on
    `background`, as a PIL image of size x size."""
    from PIL import Image
    folder = Path(getattr(sys, '_MEIPASS', '')) / 'icons'
    if not folder.is_dir():
        folder = Path(__file__).resolve().parent / 'icons'
    mask = Image.open(folder / f'{name}.png').convert('RGBA').getchannel('A').resize((size, size), Image.LANCZOS)

    def rgb(value):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    image = Image.new('RGB', (size, size), rgb(background))
    image.paste(Image.new('RGB', (size, size), rgb(color)), (0, 0), mask)
    return image


def desktop_game_entry(launcher_file, key, name):
    """`name` (one game) in the application menu and on the desktop."""
    exe, options = launch_target(launcher_file)
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    icon = data / 'icons' / 'hicolor' / '256x256' / 'apps' / 'uncharted-linux.png'
    text = ('[Desktop Entry]\nType=Application\n'
            f'Name={name}\nExec="{exe}" {options} {key}\nIcon={icon if icon.is_file() else ""}\n'
            'Terminal=false\nCategories=Game;\n')
    written = []
    for folder in (data / 'applications', desktop_folder()):
        if folder is None:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{APP_ID}-{key}.desktop'
        path.write_text(text, encoding='utf-8')
        path.chmod(0o755)
        written.append(path)
    return written


def apply_defaults(ns):
    """Linux settings the Windows launcher does not have: Steam Deck mode (on by default on
    SteamOS) and a 30 FPS frame rate."""
    ns['APP_DEFAULTS'].setdefault('steam_deck', steam_deck())
    if not any(value == '30' for value, _text in ns['FRAME_RATES']):
        ns['FRAME_RATES'].insert(0, ('30', '30 FPS (Steam Deck)'))


def saves_for(game_dir):
    return str(Path(game_dir) / 'Saves') if game_dir else ''


def default_saves(settings, data_dir=None):
    """An empty saves folder means <game folder>/Saves."""
    if not settings.get('user_dir') and settings.get('game_dir'):
        settings['user_dir'] = saves_for(settings['game_dir'])


def deck_environment(settings, env):
    """Steam Deck mode: what the Deck needs to hold 30 FPS. Applied before the player's own
    Environment entries, which can override any of it."""
    if not settings.get('steam_deck'):
        return
    env['BB_VBLANK_HZ'] = '30'           # a steady 30 instead of an uneven 15-25
    env['BB_WINDOW_SIZE'] = '1280x800'   # the Deck's screen: no 1080p output pass to scale down
    env['BB_PRESENT_MODE'] = 'Fifo'      # gamescope paces FIFO best
    env['BB_FULLSCREEN'] = '1'
    env['BB_FRAME_STATS'] = '1'          # frame time breakdown in last_run.log (tuning the Deck)


def rotate_logs(folder, keep=5):
    """last_run.log -> last_run.1.log ... (the previous runs stay readable)."""
    folder = Path(folder)
    for n in range(keep - 1, 0, -1):
        older = folder / f'last_run.{n}.log'
        newer = folder / ('last_run.log' if n == 1 else f'last_run.{n - 1}.log')
        if newer.is_file():
            try:
                os.replace(newer, older)
            except OSError:
                pass


def update_in_background(latest_release, version_tuple, version, settings):
    """Games started from Steam (Gaming Mode) never open the launcher: the update check runs
    beside the game and the new AppImage is swapped in for the next start. Returns the thread."""
    if not os.environ.get('APPIMAGE') or not settings.get('check_updates', True):
        return None

    def work():
        try:
            newest, url, _page = latest_release()
            if url and version_tuple(newest) > version_tuple(version):
                install_appimage(url, Path(os.environ['APPIMAGE']))
                print(f'Update: version {newest} installed for the next start')
        except (OSError, ValueError, KeyError):
            pass
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return thread


def launcher_class(base, ns):
    """A subclass of the launcher's Launcher (ns: the launcher module's globals): the Play page
    lists the three games, each with Add to Steam, Desktop shortcut and Play, usable only when
    that game's executable is in the chosen folder."""
    _ = ns['_']
    GAMES, SURFACE, TEXT, MUTED, CARD = ns['GAMES'], ns['SURFACE'], ns['TEXT'], ns['MUTED'], ns['CARD']
    NAME, PORT_DIR, game_info, GOLD = ns['NAME'], ns['PORT_DIR'], ns['game_info'], ns['GOLD']
    from uncharted_widgets import PillButton, rounded_image

    class IconButton(PillButton):
        """A pill button with an icon (launcher/icons) before its text."""

        def __init__(self, *args, icon_name='steam', **kwargs):
            self.icon_name = icon_name
            super().__init__(*args, **kwargs)

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
            c.delete('all')
            c.create_image(0, 0, anchor='nw', image=rounded_image(w, h, h // 2, fill, self.bg))
            self._icon = ImageTk.PhotoImage(icon_image(self.icon_name, size, fg, fill))
            x = w // 2 - (text_w + size + gap) // 2
            c.create_image(x, h // 2, anchor='w', image=self._icon)
            c.create_text(x + size + gap, h // 2, text=self.text, anchor='w', fill=fg, font=self.font)

    LAUNCH_TEXTS = (_('Preparing the game; it opens in its own window…'), _('The game is running.'),
                    _('Starting the next game of the collection…'))

    class LinuxLauncher(base):
        def build(self):
            super().build()
            self.saves_autofill()
            # "Launching…" for every step of starting a game.
            configure = self.status.configure

            def status(**kw):
                if kw.get('text') in LAUNCH_TEXTS:
                    kw['text'] = _('Launching…')
                return configure(**kw)
            self.status.configure = self.status.config = status
            # The GitHub mark (this fork's repository) instead of the note in the sidebar.
            from PIL import ImageTk
            self._github = ImageTk.PhotoImage(icon_image('github', self.px(26), MUTED, ns['BG']))
            self.side_note.configure(text='', image=self._github, cursor='hand2')
            self.side_note.bind('<Button-1>', lambda _e: open_path(REPO_URL))
            self.side_note.bind('<Enter>', lambda _e: self.side_note.configure(
                image=self._github_hot) if hasattr(self, '_github_hot') else None)
            self._github_hot = ImageTk.PhotoImage(icon_image('github', self.px(26), TEXT, ns['BG']))
            self.side_note.bind('<Leave>', lambda _e: self.side_note.configure(image=self._github))

        def style(self):
            super().style()
            # Dropdowns with round ends, like the buttons (clam draws square ones).
            from PIL import Image, ImageDraw, ImageTk
            h = self.px(30)
            r = h // 2
            images = []
            for color in (ns['CARD_HI'], ns['GOLD_DIM']):
                # Opaque corners in the card colour behind the dropdowns: Tk fills transparent
                # pixels of an element image with the widget's own (field) colour.
                image = Image.new('RGB', (h * 4 * 2, h * 4), CARD)
                ImageDraw.Draw(image).rounded_rectangle((0, 0, h * 8 - 1, h * 4 - 1), r * 4, fill=color)
                images.append(ImageTk.PhotoImage(image.resize((h * 2, h), Image.LANCZOS)))
            self._field_images = images
            s = self.ttk.Style(self.root)
            try:
                s.element_create('Round.field', 'image', images[0], ('focus', images[0]),
                                 border=(r, r // 2, r, r // 2), sticky='nswe')
            except self.tk.TclError:
                pass
            s.layout('TCombobox', [('Round.field', {'sticky': 'nswe', 'children': [
                ('Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}),
                ('Combobox.padding', {'expand': '1', 'sticky': 'nswe', 'children': [
                    ('Combobox.textarea', {'sticky': 'nswe'})]})]})])
            s.configure('TCombobox', arrowcolor=GOLD, background=ns['CARD_HI'], bordercolor=ns['CARD_HI'],
                        lightcolor=ns['CARD_HI'], darkcolor=ns['CARD_HI'], padding=(self.px(4), 2))

        def page(self, name, title, subtitle):
            f = super().page(name, title, subtitle)
            if name == 'display':
                self.check(f, 'steam_deck', _('Steam Deck mode'),
                           _('30 FPS at the Deck\'s 1280 × 800, for a steady frame rate on the Steam Deck. '
                             'On by default on SteamOS.'))
            return f

        def build_play(self):
            tk = self.tk
            page = tk.Frame(self.content, bg=SURFACE)
            self.pages['play'] = page
            self.cards, self.card_images = {}, {}
            self.game_rows = {}
            shell = tk.Frame(page, bg=SURFACE)
            shell.pack(fill='both', expand=True, padx=self.px(44), pady=(self.px(36), self.px(10)))
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
                shortcut = self.pill(row, _('Desktop shortcut'), lambda k=key: self.game_shortcut(k),
                                     background=CARD, padding=(14, 8))
                shortcut.pack(side='right', padx=(self.px(8), 0))
                steam = IconButton(self.tk, row, _('Add to Steam'), lambda k=key: self.add_game_to_steam(k),
                                   ns['COLORS'], self.px, self.font_button, 'secondary', CARD, (16, 8),
                                   icon_name='steam')
                steam.pack(side='right')
                self.game_rows[key] = (play, steam, shortcut, note, exe)
            row = tk.Frame(shell, bg=SURFACE)
            row.pack(fill='x', pady=(self.px(14), self.px(8)))
            self.toggle(row, self.var('fullscreen'), SURFACE).pack(side='left')
            fullscreen = tk.Label(row, text=_('Fullscreen'), bg=SURFACE, fg=TEXT, font=self.font_ui, cursor='hand2')
            fullscreen.pack(side='left', padx=(self.px(10), 0))
            fullscreen.bind('<Button-1>', lambda _e: self.var('fullscreen').set(not self.var('fullscreen').get()))
            self.ready = tk.Label(shell, text='', bg=SURFACE, fg=MUTED, font=self.font_ui_sm,
                                  wraplength=self.px(820), justify='left')
            self.ready.pack(anchor='w', pady=(0, self.px(16)))

        def saves_autofill(self):
            # Choosing a game folder fills in <folder>/Saves, unless the player chose a saves
            # folder of their own (the field is empty or still holds the previous automatic one).
            game, saves = self.var('game_dir'), self.var('user_dir')
            self._auto_saves = saves_for(game.get())

            def follow(*_args):
                if saves.get() in ('', self._auto_saves):
                    self._auto_saves = saves_for(game.get())
                    saves.set(self._auto_saves)
            game.trace_add('write', follow)
            if not saves.get():
                follow()

        def collect(self):
            for key, var in self.vars.items():
                self.app[key] = var.get()
            before = self.app.get('user_dir')
            default_saves(self.app, ns['DATA_DIR'])
            if self.app.get('user_dir') != before and 'user_dir' in self.vars:
                self.vars['user_dir'].set(self.app['user_dir'])  # the Game page shows it
            super().collect()

        def refresh(self):
            super().refresh()
            info = self.info
            for key, (play, steam, shortcut, note, exe) in getattr(self, 'game_rows', {}).items():
                present = bool(info) and key in info['games']
                play.configure(state='normal' if present and not self.process else 'disabled')
                for button in (steam, shortcut):
                    button.configure(state='normal' if present else 'disabled')
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

        def game_name(self, key):
            number, title = next((n, t) for n, (k, t, _s, _e) in enumerate(GAMES, start=1) if k == key)
            return f'Uncharted {number}: {title}'

        def play_game(self, key):
            if self.available(key):
                self.var('start').set(key)
                self.play()

        def play(self):
            if not self.process:
                rotate_logs(Path(self.app.get('user_dir') or ns['DATA_DIR'] / 'user'))
            super().play()

        def game_shortcut(self, key):
            if not self.available(key):
                return
            try:
                desktop_game_entry(ns['__file__'], key, self.game_name(key))
            except OSError as error:
                self.messagebox.showerror(NAME, str(error))
                return
            self.messagebox.showinfo(NAME, _('{} is in the application menu and on the desktop.').format(
                self.game_name(key)))

        # No artwork on this page.
        def draw_hero(self):
            pass

        def draw_card(self, key):
            pass

        def fit_posters(self, _event=None):
            pass

        # ---- updates: the AppImage replaces itself with the newest release of this fork ----------
        def offer_update(self, version, url, page):
            """A newer release: an AppImage downloads it in the background and swaps it in, then
            offers a restart. Other installs (the tarball, a source tree) get the release page."""
            parts = version.split('.')
            if len(parts) == 4:  # tag v0.3.1-linux.8 arrives as 0.3.1.8
                version = '.'.join(parts[:3]) + '-linux.' + parts[3]
            if self.update_box or not os.environ.get('APPIMAGE') or not url:
                return super().offer_update(version, url, page)
            self.update_box = 'downloading'
            self.status.configure(text=_('Downloading version {}…').format(version), fg=GOLD)

            def work():
                try:
                    install_appimage(url, Path(os.environ['APPIMAGE']))
                except (OSError, ValueError) as failure:
                    def failed(error=failure):
                        self.update_box = None
                        if not self.process:
                            self.status.configure(text=_('Update failed: {}').format(error), fg=MUTED)
                        super(LinuxLauncher, self).offer_update(version, None, page)
                    self.ui_calls.put(failed)
                    return
                self.ui_calls.put(lambda: self.updated(version))
            threading.Thread(target=work, daemon=True).start()

        def updated(self, version):
            tk = self.tk
            box = tk.Frame(self.side, bg=CARD, highlightthickness=1, highlightbackground=ns['GOLD_DIM'])
            tk.Label(box, text=_('Version {} is installed. Restart to use it.').format(version), bg=CARD,
                     fg=GOLD, font=self.font_ui_md, wraplength=self.px(190), justify='left').pack(
                anchor='w', padx=12, pady=(10, 8))
            self.pill(box, _('Restart'), self.restart_updated, kind='primary', padding=(14, 6)).pack(
                anchor='w', padx=12, pady=(0, 12))
            box.pack(fill='x', padx=18, pady=(0, 14), before=self.side_note)
            self.update_box = box
            if not self.process:
                self.status.configure(text=_('Version {} is installed. Restart to use it.').format(version), fg=GOLD)

        def restart_updated(self):
            if self.process:
                self.messagebox.showinfo(NAME, _('Close the game before restarting.'))
                return
            env = clean_env()
            for name in ('APPIMAGE', 'APPDIR', 'ARGV0', 'OWD'):  # the new AppImage sets its own
                env.pop(name, None)
            subprocess.Popen([os.environ['APPIMAGE']], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            self.close()

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
            name = self.game_name(key)
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
