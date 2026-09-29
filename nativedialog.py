# Native file and message dialogs for Ren'Py games, without tkinter.
#
# Pure stdlib. The Python side only talks to the OS through ctypes and
# subprocess, so nothing here needs a C module built into the runtime.
#
# Backends: Windows (comdlg32/shell32/user32 via ctypes), macOS
# (/usr/bin/osascript, always present), Linux (zenity, then kdialog).
#
# Usage from a game:
#
#     import nativedialog
#     path = nativedialog.askopenfilename(
#         title="Import save",
#         filetypes=[("Ren'Py saves", "*.save"), ("All files", "*.*")])

import os
import sys
import shutil
import subprocess

__all__ = [
    "backend",
    "askopenfilename",
    "askopenfilenames",
    "asksaveasfilename",
    "askdirectory",
    "showinfo",
    "showwarning",
    "showerror",
    "askyesno",
]

# True when the last call failed for a reason other than the user
# cancelling (no backend, no display server, tool error). Useful when a
# dialog unexpectedly returns "" / () / None.
last_error = ""


def backend():
    """
    Returns the name of the backend dialogs will use: "windows",
    "osascript", "zenity", "kdialog", or "none".
    """

    if sys.platform == "win32":
        return "windows"

    if sys.platform == "darwin":
        return "osascript"

    if _linux_tool("zenity") is not None:
        return "zenity"

    if _linux_tool("kdialog") is not None:
        return "kdialog"

    return "none"


def _linux_tool(name):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None

    return shutil.which(name)


def _note(msg):
    global last_error
    last_error = msg


def _shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


# The tkinter-compatible API. Options mirror tkinter.filedialog where it
# makes sense; parent/defaultextension are accepted and ignored where a
# backend has no equivalent.


def askopenfilename(title=None, initialdir=None, initialfile=None,
                    filetypes=None, parent=None, **kwargs):
    """
    Ask for an existing file. Returns its path, or "" if the user
    cancelled or no backend is available.
    """

    rv = _open_dialog(False, title, initialdir, initialfile, filetypes)
    return rv[0] if rv else ""


def askopenfilenames(title=None, initialdir=None, initialfile=None,
                     filetypes=None, parent=None, **kwargs):
    """
    Ask for one or more existing files. Returns a tuple of paths, empty
    if the user cancelled or no backend is available.
    """

    rv = _open_dialog(True, title, initialdir, initialfile, filetypes)
    return tuple(rv) if rv else ()


def asksaveasfilename(title=None, initialdir=None, initialfile=None,
                      filetypes=None, defaultextension=None, parent=None,
                      **kwargs):
    """
    Ask for a file to save to, confirming an overwrite. Returns the
    path, or "" if the user cancelled or no backend is available.
    """

    if sys.platform == "win32":
        return _win_save(title, initialdir, initialfile, filetypes, defaultextension)

    if sys.platform == "darwin":
        return _mac_save(title, initialdir, initialfile, defaultextension)

    tool = _linux_tool("zenity")

    if tool is not None:
        args = [ tool, "--file-selection", "--save", "--confirm-overwrite" ]

        if title:
            args += [ "--title", title ]

        args += [ "--filename", os.path.join(initialdir or "", initialfile or "") ]

        for label, patterns in _norm_filetypes(filetypes):
            args += [ "--file-filter", "{} | {}".format(label, " ".join(patterns)) ]

        return _run_line(args) or ""

    tool = _linux_tool("kdialog")

    if tool is not None:
        args = [ tool, "--getsavefilename",
                 os.path.join(initialdir or ".", initialfile or "") ]

        if title:
            args += [ "--title", title ]

        return _run_line(args) or ""

    _note("no dialog backend available")
    return ""


def askdirectory(title=None, initialdir=None, parent=None, **kwargs):
    """
    Ask for an existing directory. Returns its path, or "" if the user
    cancelled or no backend is available.
    """

    if sys.platform == "win32":
        return _win_directory(title, initialdir)

    if sys.platform == "darwin":
        script = "POSIX path of (choose folder"

        if title:
            script += " with prompt {}".format(_applescript_str(title))

        if initialdir:
            script += " default location (POSIX file {})".format(_applescript_str(initialdir))

        return _run_line([ _osascript, "-e", script + ")" ])

    tool = _linux_tool("zenity")

    if tool is not None:
        args = [ tool, "--file-selection", "--directory" ]

        if title:
            args += [ "--title", title ]

        if initialdir:
            args += [ "--filename", initialdir + "/" ]

        return _run_line(args) or ""

    tool = _linux_tool("kdialog")

    if tool is not None:
        args = [ tool, "--getexistingdirectory", initialdir or "." ]

        if title:
            args += [ "--title", title ]

        return _run_line(args) or ""

    _note("no dialog backend available")
    return ""


def showinfo(title, message, parent=None, **kwargs):
    _message(title, message, "info")


def showwarning(title, message, parent=None, **kwargs):
    _message(title, message, "warning")


def showerror(title, message, parent=None, **kwargs):
    _message(title, message, "error")


def askyesno(title, message, parent=None, **kwargs):
    """
    Ask a yes/no question. Returns True or False; None if the user
    cancelled or no backend is available.
    """

    if sys.platform == "win32":
        rv = _win_message(title, message, 0x04 | 0x40 | 0x40000) # MB_YESNO|ICONINFORMATION|TOPMOST
        return { 6: True, 7: False }.get(rv)

    if sys.platform == "darwin":
        script = 'display dialog {} with title {} buttons {{"No", "Yes"}} default button "Yes"'.format(
            _applescript_str(message), _applescript_str(title))

        out = _run_line([ _osascript, "-e", script ])
        return None if out is None else "Yes" in out

    tool = _linux_tool("zenity")

    if tool is not None:
        p = subprocess.run(
            [ tool, "--question", "--title", title or "", "--text", message or "" ],
            capture_output=True)

        if p.returncode == 0:
            return True

        if p.returncode == 1:
            return False

        _note(p.stderr.decode("utf-8", "replace").strip())
        return None

    tool = _linux_tool("kdialog")

    if tool is not None:
        p = subprocess.run(
            [ tool, "--yesno", message or "", "--title", title or "" ],
            capture_output=True)

        if p.returncode == 0:
            return True

        if p.returncode == 1:
            return False

        _note(p.stderr.decode("utf-8", "replace").strip())
        return None

    _note("no dialog backend available")
    return None


# Shared helpers.


def _norm_filetypes(filetypes):
    """
    Normalizes tkinter-style filetypes to a list of (label, [patterns])
    pairs.
    """

    rv = [ ]

    for ft in filetypes or [ ]:
        label, patterns = ft[0], ft[1]

        if isinstance(patterns, str):
            patterns = [ patterns ]

        rv.append((label, list(patterns)))

    return rv


def _message(title, message, kind):
    if sys.platform == "win32":
        icons = { "info": 0x40, "warning": 0x30, "error": 0x10 }
        _win_message(title, message, icons[kind] | 0x40000) # | MB_TOPMOST

    elif sys.platform == "darwin":
        icon = { "info": "note", "warning": "caution", "error": "stop" }[kind]
        script = "display dialog {} with title {} buttons {{\"OK\"}} default button \"OK\" with icon {}".format(
            _applescript_str(message), _applescript_str(title), icon)

        _run_line([ _osascript, "-e", script ])

    else:
        tool = _linux_tool("zenity")

        if tool is not None:
            subprocess.run(
                [ tool, "--" + kind, "--title", title or "", "--text", message or "" ],
                capture_output=True)

            return

        tool = _linux_tool("kdialog")

        if tool is not None:
            flag = { "info": "--msgbox", "warning": "--sorry", "error": "--error" }[kind]
            subprocess.run([ tool, flag, message or "", "--title", title or "" ], capture_output=True)

            return

        _note("no dialog backend available")


def _open_dialog(multiple, title, initialdir, initialfile, filetypes):
    if sys.platform == "win32":
        return _win_open(multiple, title, initialdir, initialfile, filetypes)

    if sys.platform == "darwin":
        return _mac_open(multiple, title, initialdir)

    tool = _linux_tool("zenity")

    if tool is not None:
        args = [ tool, "--file-selection" ]

        if multiple:
            args += [ "--multiple", "--separator", "\n" ]

        if title:
            args += [ "--title", title ]

        args += [ "--filename", os.path.join(initialdir or "", initialfile or "") ]

        for label, patterns in _norm_filetypes(filetypes):
            args += [ "--file-filter", "{} | {}".format(label, " ".join(patterns)) ]

        args += [ "--file-filter", "All files | *" ]

        out = _run_line(args)

        if not out:
            return [ ]

        return out.splitlines()

    tool = _linux_tool("kdialog")

    if tool is not None:
        args = [ tool, "--getopenfilename", os.path.join(initialdir or ".", initialfile or "") ]

        if multiple:
            args += [ "--multiple", "--separate-output" ]

        if title:
            args += [ "--title", title ]

        out = _run_line(args)

        if not out:
            return [ ]

        return out.splitlines()

    _note("no dialog backend available")
    return [ ]


def _run_line(args):
    """
    Runs a dialog helper that prints its result to stdout. Returns the
    stripped output, or None if the user cancelled or the tool failed.
    """

    try:
        p = subprocess.run(args, capture_output=True)
    except Exception as e:
        _note(repr(e))
        return None

    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()

        if "user cancel" in err.lower() or "-128" in err:
            return None

        _note(err)
        return None

    return p.stdout.decode("utf-8", "replace").strip()


def _applescript_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Windows backend (comdlg32, shell32, user32 through ctypes).

if sys.platform == "win32":

    import ctypes
    from ctypes import wintypes

    _comdlg32 = ctypes.WinDLL("comdlg32.dll")
    _shell32 = ctypes.WinDLL("shell32.dll")
    _user32 = ctypes.WinDLL("user32.dll")
    _ole32 = ctypes.WinDLL("ole32.dll")

    _OFN_ALLOWMULTISELECT = 0x00000200
    _OFN_EXPLORER = 0x00080000
    _OFN_FILEMUSTEXIST = 0x00001000
    _OFN_HIDEREADONLY = 0x00000004
    _OFN_OVERWRITEPROMPT = 0x00000002
    _OFN_PATHMUSTEXIST = 0x00000800

    class _OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", ctypes.c_void_p),
            ("lpstrCustomFilter", ctypes.c_void_p),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", ctypes.c_void_p),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", ctypes.c_void_p),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", ctypes.c_void_p),
            ("lpstrTitle", ctypes.c_void_p),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", ctypes.c_void_p),
            ("lCustData", ctypes.c_void_p),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", ctypes.c_void_p),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    class _BROWSEINFOW(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", ctypes.c_void_p),
            ("lpszTitle", ctypes.c_void_p),
            ("ulFlags", wintypes.UINT),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("iImage", ctypes.c_int),
        ]

    def _win_filter(filetypes):
        # "Label\0*.png;*.jpg\0...\0All files\0*.*\0\0"
        parts = [ ]

        for label, patterns in _norm_filetypes(filetypes):
            parts.append(label)
            parts.append(";".join(patterns))

        parts += [ "All files", "*.*" ]

        buf = ctypes.create_unicode_buffer("\x00".join(parts) + "\x00\x00")
        return ctypes.cast(buf, ctypes.c_void_p), buf

    def _win_open(multiple, title, initialdir, initialfile, filetypes):
        buf = ctypes.create_unicode_buffer(0x10000)

        if initialfile:
            buf.value = initialfile

        filter_ptr, filter_buf = _win_filter(filetypes)

        flags = _OFN_EXPLORER | _OFN_FILEMUSTEXIST | _OFN_PATHMUSTEXIST | _OFN_HIDEREADONLY

        if multiple:
            flags |= _OFN_ALLOWMULTISELECT

        ofn = _OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(_OPENFILENAMEW)
        ofn.lpstrFilter = filter_ptr
        ofn.lpstrFile = ctypes.cast(buf, ctypes.c_void_p)
        ofn.nMaxFile = 0x10000
        ofn.lpstrInitialDir = initialdir
        ofn.lpstrTitle = title
        ofn.Flags = flags

        if not _comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return [ ]

        if not multiple:
            return [ buf.value ]

        return _win_parse_multi(buf.value)

    def _win_save(title, initialdir, initialfile, filetypes, defaultextension):
        buf = ctypes.create_unicode_buffer(0x10000)

        if initialfile:
            buf.value = initialfile

        filter_ptr, filter_buf = _win_filter(filetypes)
        defext = defaultextension.lstrip(".") if defaultextension else None

        ofn = _OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(_OPENFILENAMEW)
        ofn.lpstrFilter = filter_ptr
        ofn.lpstrFile = ctypes.cast(buf, ctypes.c_void_p)
        ofn.nMaxFile = 0x10000
        ofn.lpstrInitialDir = initialdir
        ofn.lpstrTitle = title
        ofn.lpstrDefExt = defext
        ofn.Flags = _OFN_EXPLORER | _OFN_OVERWRITEPROMPT | _OFN_PATHMUSTEXIST | _OFN_HIDEREADONLY

        if not _comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
            return ""

        return buf.value

    def _win_parse_multi(value):
        """
        Parses the space-separated, quote-escaped file list that
        GetOpenFileNameW returns in Explorer mode.
        """

        tokens = [ ]
        cur = ""
        in_quotes = False

        for c in value:
            if c == '"':
                in_quotes = not in_quotes
            elif c == " " and not in_quotes:
                tokens.append(cur)
                cur = ""
            else:
                cur += c

        tokens.append(cur)

        if len(tokens) == 1:
            return [ tokens[0] ]

        directory = tokens[0]
        rv = [ ]

        for name in tokens[1:]:
            rv.append(os.path.join(directory, name))

        return rv

    def _win_directory(title, initialdir):
        _ole32.CoInitializeEx(None, 0) # COINIT_MULTITHREADED

        display = ctypes.create_unicode_buffer(wintypes.MAX_PATH)

        bi = _BROWSEINFOW()
        bi.lpstrTitle = title
        bi.pszDisplayName = ctypes.cast(display, ctypes.c_void_p)
        bi.ulFlags = 0x0040 # BIF_NEWDIALOGSTYLE

        pidl = _shell32.SHBrowseForFolderW(ctypes.byref(bi))

        if not pidl:
            return ""

        try:
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            _shell32.SHGetPathFromIDListW(pidl, buf)
            return buf.value
        finally:
            _ole32.CoTaskMemFree(pidl)

    def _win_message(title, message, kind):
        # MB_TOPMOST so the box is not buried behind the game window.
        return _user32.MessageBoxW(None, message, title, kind | 0x40000)


# macOS backend (/usr/bin/osascript).

if sys.platform == "darwin":

    _osascript = "/usr/bin/osascript"

    def _mac_open(multiple, title, initialdir):
        script = "set fl to (choose file"

        if title:
            script += " with prompt {}".format(_applescript_str(title))

        if initialdir:
            script += " default location (POSIX file {})".format(_applescript_str(initialdir))

        if multiple:
            script += " with multiple selections allowed"

        script += ")\nif class of fl is not list then set fl to {fl}\nset out to \"\"\nrepeat with f in fl\nset out to out & (POSIX path of f) & linefeed\nend repeat\nreturn out"

        out = _run_line([ _osascript, "-e", script ])

        if not out:
            return [ ]

        return out.splitlines()

    def _mac_save(title, initialdir, initialfile, defaultextension):
        script = "POSIX path of (choose file name"

        if title:
            script += " with prompt {}".format(_applescript_str(title))

        if initialfile:
            script += " default name {}".format(_applescript_str(initialfile))
        elif defaultextension:
            script += " default name {}".format(_applescript_str("unnamed" + defaultextension))

        if initialdir:
            script += " default location (POSIX file {})".format(_applescript_str(initialdir))

        return _run_line([ _osascript, "-e", script + ")" ]) or ""
