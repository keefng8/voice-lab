"""Voice Lab - hear every voice this machine has, and find the ones Mavis cannot.

WHY THIS EXISTS
---------------
Windows keeps its speech voices in two different places, and most software
only looks in one of them:

    HKLM\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens            <- SAPI5
    HKLM\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices\\Tokens    <- OneCore

pyttsx3 - which is what Mavis speaks through - reads the SAPI5 key only. On
the machine this was written on that key held exactly two voices, both of them
the old "Desktop" ones that sound like a satnav from 2009. The OneCore key
held three more, newer and markedly better, including the only male British
voice on the system.

So the assistant was using the worst voices installed, and nothing anywhere
said so. This feature finds that out for you, lets you hear the difference,
and explains what to do about it.

HOW IT SPEAKS
-------------
Through PowerShell's System.Speech, which is part of .NET and therefore on
every Windows machine. No pip install, no COM wrangling, and - the point -
it can see BOTH registries, so you can audition voices Mavis currently
cannot reach.

Standard library only.
"""
import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import mavis_ui as ui

FEATURE = "voice-lab"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def _shell():
    """PowerShell 7 if it is here, Windows PowerShell 5.1 otherwise.

    This matters more than it looks. System.Speech is a .NET API, and the two
    PowerShells run different .NET runtimes:

        powershell 5.1  (.NET Framework)  -> 2 voices   (SAPI5 only)
        pwsh 7.x        (.NET Core)       -> 5 voices   (SAPI5 + OneCore)

    Measured on the machine this was written on. Built against 5.1 first, this
    feature reported exactly the same two voices pyttsx3 already had and
    confidently announced that nothing was hidden - which was the opposite of
    the truth and the entire point of the feature.

    So pwsh is preferred, and if only 5.1 is available the interface says so
    rather than pretending the machine has fewer voices than it does.
    """
    import shutil
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return exe
    return "powershell"


SHELL = _shell()
MODERN_SHELL = SHELL == "pwsh"

PS = [SHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
      "-Command"]

SAMPLE = ("Good evening. Both services are up, and drive C has twenty two "
          "gigabytes free.")

LIST_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($v in $s.GetInstalledVoices()) {
  $i = $v.VoiceInfo
  '{0}|{1}|{2}|{3}' -f $i.Name, $i.Culture.Name, $i.Gender, $v.Enabled
}
"""

SAPI5_KEY = r"HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens"
ONECORE_KEY = r"HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"

REG_LIST = r"""
$out = @()
foreach ($k in @('%s','%s')) {
  if (Test-Path $k) {
    foreach ($t in Get-ChildItem $k) {
      $name = (Get-ItemProperty $t.PSPath).'(default)'
      $out += ('{0}|{1}' -f $k, $name)
    }
  }
}
$out
""" % (SAPI5_KEY, ONECORE_KEY)


def run_ps(script, timeout=30):
    try:
        result = subprocess.run(PS + [script], capture_output=True, text=True,
                                timeout=timeout, creationflags=NO_WINDOW)
        return result.returncode == 0, (result.stdout or "").strip(), (result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as error:
        return False, "", str(error)


def installed_voices():
    ok, out, err = run_ps(LIST_SCRIPT)
    if not ok:
        return [], err
    voices = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) != 4:
            continue
        voices.append({"name": parts[0].strip(), "culture": parts[1].strip(),
                       "gender": parts[2].strip(),
                       "enabled": parts[3].strip().lower() == "true"})
    return voices, None


def registry_voices():
    """Which registry each voice is in - that is what decides whether Mavis
    can see it."""
    ok, out, _ = run_ps(REG_LIST)
    sapi5, onecore = set(), set()
    if ok:
        for line in out.splitlines():
            if "|" not in line:
                continue
            key, name = line.split("|", 1)
            target = onecore if "OneCore" in key else sapi5
            target.add(name.strip())
    return sapi5, onecore


def short(full_name):
    """'Microsoft Hazel Desktop - English (Great Britain)' -> 'Microsoft Hazel Desktop'"""
    return re.split(r"\s+-\s+", full_name)[0].strip()


def speak(voice, text, rate, volume):
    """Say something in one voice.

    Rate is -10..10 in System.Speech, which is not a percentage and not
    words per minute; 0 is the voice's natural pace.
    """
    safe_text = text.replace("'", "''")
    safe_voice = voice.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SelectVoice('%s') } catch { $s.SelectVoiceByHints('Female') }; "
        "$s.Rate = %d; $s.Volume = %d; $s.Speak('%s')"
        % (safe_voice, int(rate), int(volume), safe_text))
    return run_ps(script, timeout=60)


class VoiceLab(ui.MavisWindow):
    def __init__(self):
        super().__init__(FEATURE, "Voice Lab", width=780, height=640)
        saved = ui.load_state(FEATURE, {})
        self.voices = []
        self.sapi5 = set()
        self.onecore = set()
        self.busy = False
        self.rate = tk.IntVar(value=saved.get("rate", 0))
        self.volume = tk.IntVar(value=saved.get("volume", 100))

        self._build()
        self.after(200, self.load)

    def _build(self):
        head = tk.Frame(self.content, bg=ui.INK)
        head.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(head, text="Type something for them to say", bg=ui.INK,
                 fg=ui.GLOW, font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x")
        self.text = tk.Text(head, height=3, bg="#07060f", fg=ui.TEXT, relief="flat",
                            insertbackground=ui.GLOW, font=("Segoe UI", 10),
                            wrap="word", highlightthickness=0, padx=10, pady=8)
        self.text.pack(fill="x", pady=(4, 0))
        self.text.insert("1.0", SAMPLE)

        sliders = tk.Frame(head, bg=ui.INK)
        sliders.pack(fill="x", pady=(8, 0))
        for label, var, low, high in (("Speed", self.rate, -10, 10),
                                      ("Volume", self.volume, 0, 100)):
            cell = tk.Frame(sliders, bg=ui.INK)
            cell.pack(side="left", padx=(0, 24))
            tk.Label(cell, text=label, bg=ui.INK, fg=ui.DIM,
                     font=("Segoe UI", 8)).pack(anchor="w")
            tk.Scale(cell, from_=low, to=high, orient="horizontal", variable=var,
                     bg=ui.INK, fg=ui.TEXT, troughcolor=ui.PANEL, highlightthickness=0,
                     relief="flat", length=190, font=("Segoe UI", 7),
                     activebackground=ui.GLOW).pack()

        self.state = tk.Label(sliders, text="", bg=ui.INK, fg=ui.DIM,
                              font=("Segoe UI", 9))
        self.state.pack(side="left", pady=(14, 0))

        tk.Frame(self.content, bg=ui.LINE, height=1).pack(fill="x", pady=(10, 0))

        holder = tk.Frame(self.content, bg=ui.INK)
        holder.pack(fill="both", expand=True, padx=16, pady=10)
        self.canvas = tk.Canvas(holder, bg=ui.INK, highlightthickness=0)
        scroll = tk.Scrollbar(holder, orient="vertical", command=self.canvas.yview,
                              width=8, troughcolor=ui.INK, bg=ui.LINE,
                              relief="flat", borderwidth=0)
        self.list = tk.Frame(self.canvas, bg=ui.INK)
        self.list.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        item = self.canvas.create_window((0, 0), window=self.list, anchor="nw")
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(item, width=e.width))
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.bind_all("<MouseWheel>",
                      lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

    # ------------------------------------------------------------------ load
    def load(self):
        self.state.configure(text="looking…")

        def work():
            voices, error = installed_voices()
            sapi5, onecore = registry_voices()
            self.after(0, lambda: self._loaded(voices, error, sapi5, onecore))

        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, voices, error, sapi5, onecore):
        self.voices = voices
        self.sapi5, self.onecore = sapi5, onecore
        self.state.configure(text="")
        self.render(error)

    def visible_to_mavis(self, voice):
        """Mavis speaks through pyttsx3, which reads the SAPI5 key only."""
        name = short(voice["name"])
        return any(short(entry) == name for entry in self.sapi5)

    def render(self, error=None):
        for child in self.list.winfo_children():
            child.destroy()

        if error:
            tk.Label(self.list, bg=ui.INK, fg=ui.BAD, font=("Segoe UI", 9),
                     wraplength=700, justify="left", anchor="w",
                     text="Could not ask Windows for its voices:\n" + error
                     ).pack(fill="x")
            return
        if not self.voices:
            tk.Label(self.list, text="No voices found.", bg=ui.INK, fg=ui.DIM,
                     font=("Segoe UI", 9)).pack(pady=20)
            return

        if not MODERN_SHELL:
            note = tk.Frame(self.list, bg=ui.PANEL)
            note.pack(fill="x", pady=(0, 10))
            tk.Frame(note, bg=ui.WARN, width=3).pack(side="left", fill="y")
            inner = tk.Frame(note, bg=ui.PANEL)
            inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)
            tk.Label(inner, bg=ui.PANEL, fg=ui.WARN, anchor="w",
                     font=("Segoe UI", 9, "bold"),
                     text="This list may be incomplete").pack(fill="x")
            tk.Label(inner, bg=ui.PANEL, fg=ui.DIM, anchor="w", justify="left",
                     wraplength=640, font=("Segoe UI", 9),
                     text="Only Windows PowerShell 5.1 is installed, and its .NET "
                          "runtime can see the older SAPI5 voices only — the same "
                          "ones Mavis already has. PowerShell 7 sees both sets. If "
                          "this machine has newer voices, they will not appear here "
                          "until PowerShell 7 is installed (winget install "
                          "Microsoft.PowerShell).").pack(fill="x", pady=(4, 0))

        hidden = [v for v in self.voices if not self.visible_to_mavis(v)]
        if hidden:
            warn = tk.Frame(self.list, bg=ui.PANEL)
            warn.pack(fill="x", pady=(0, 10))
            tk.Frame(warn, bg=ui.WARN, width=3).pack(side="left", fill="y")
            inner = tk.Frame(warn, bg=ui.PANEL)
            inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)
            tk.Label(inner, bg=ui.PANEL, fg=ui.WARN, font=("Segoe UI", 9, "bold"),
                     anchor="w", text="Mavis cannot use %d of these %d voices"
                     % (len(hidden), len(self.voices))).pack(fill="x")
            tk.Label(inner, bg=ui.PANEL, fg=ui.DIM, font=("Segoe UI", 9),
                     anchor="w", justify="left", wraplength=640,
                     text="Windows keeps voices in two registry locations. Mavis "
                          "speaks through pyttsx3, which reads the older SAPI5 one "
                          "only — so the newer OneCore voices below are installed, "
                          "work fine here, and are invisible to it. They are usually "
                          "the better-sounding ones.").pack(fill="x", pady=(4, 8))
            ui.button(inner, "Make them available to Mavis…",
                      self.explain_fix).pack(anchor="w")

        for voice in sorted(self.voices, key=lambda v: (not self.visible_to_mavis(v),
                                                        v["name"])):
            self._row(voice)

    def _row(self, voice):
        usable = self.visible_to_mavis(voice)
        card = tk.Frame(self.list, bg=ui.PANEL)
        card.pack(fill="x", pady=(0, 5))
        tk.Frame(card, bg=ui.GOOD if usable else ui.WARN, width=3).pack(side="left", fill="y")
        inner = tk.Frame(card, bg=ui.PANEL)
        inner.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        top = tk.Frame(inner, bg=ui.PANEL)
        top.pack(fill="x")
        tk.Label(top, text=short(voice["name"]), bg=ui.PANEL, fg=ui.TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(top, text="   %s   %s" % (voice["culture"], voice["gender"].lower()),
                 bg=ui.PANEL, fg=ui.DIM, font=("Consolas", 8)).pack(side="left")
        tk.Label(top, text="   Mavis can use this" if usable else "   not visible to Mavis",
                 bg=ui.PANEL, fg=ui.GOOD if usable else ui.WARN,
                 font=("Segoe UI", 8)).pack(side="left")

        side = tk.Frame(card, bg=ui.PANEL)
        side.pack(side="right", padx=(0, 10))
        ui.button(side, "Hear it", lambda v=voice: self.audition(v)).pack(pady=6)

    # -------------------------------------------------------------- speaking
    def audition(self, voice):
        if self.busy:
            return
        self.busy = True
        text = self.text.get("1.0", "end-1c").strip() or SAMPLE
        self.state.configure(text="speaking as %s…" % short(voice["name"]))

        def work():
            ok, _, err = speak(voice["name"], text, self.rate.get(), self.volume.get())
            self.after(0, lambda: self._spoken(ok, err))

        threading.Thread(target=work, daemon=True).start()

    def _spoken(self, ok, err):
        self.busy = False
        self.state.configure(text="" if ok else "could not speak: " + err[:60],
                             fg=ui.DIM if ok else ui.BAD)

    # ------------------------------------------------------------------ fix
    def explain_fix(self):
        """Offer the registry change WITHOUT making it.

        Copying the OneCore voice tokens into the SAPI5 key is the known way
        to expose them to pyttsx3. It is a machine-wide change under HKLM and
        needs elevation, so this writes a .reg file the user can read first
        and apply themselves. A feature that silently edits HKLM is not one
        anybody should install.
        """
        hidden = [v for v in self.voices if not self.visible_to_mavis(v)]
        if not hidden:
            return
        message = (
            "Windows keeps speech voices in two registry locations:\n\n"
            "  SAPI5     ...\\Speech\\Voices\\Tokens        <- Mavis reads this\n"
            "  OneCore   ...\\Speech_OneCore\\Voices\\Tokens <- these are hidden from it\n\n"
            "%d voice%s sit only in OneCore:\n  %s\n\n"
            "Copying those entries into the SAPI5 key makes them available to "
            "Mavis and to anything else using pyttsx3.\n\n"
            "That is a machine-wide change under HKLM and needs an administrator, "
            "so this will NOT do it for you. Save a .reg file instead, read it, "
            "and run it yourself if you are happy with it?"
            % (len(hidden), "" if len(hidden) == 1 else "s",
               "\n  ".join(short(v["name"]) for v in hidden)))
        if not messagebox.askyesno("Make voices available to Mavis", message,
                                   parent=self):
            return

        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".reg",
            initialfile="mavis-extra-voices.reg",
            filetypes=[("Registry file", "*.reg")])
        if not path:
            return

        ok, out, err = run_ps(
            "$src='%s'; $dst='%s'; "
            "if (Test-Path $src) { reg export ($src -replace 'HKLM:','HKLM') "
            "\"%s\" /y | Out-Null; 'ok' } else { 'missing' }"
            % (ONECORE_KEY, SAPI5_KEY, path.replace("\\", "\\\\")))

        if not ok or "ok" not in out:
            messagebox.showwarning("Could not export",
                                   "The OneCore voices could not be exported: %s"
                                   % (err or out)[:200], parent=self)
            return

        # The exported file points at the OneCore key; rewrite the paths so
        # applying it creates the entries under SAPI5 instead.
        try:
            with open(path, "r", encoding="utf-16") as handle:
                body = handle.read()
            body = body.replace("\\Speech_OneCore\\", "\\Speech\\")
            with open(path, "w", encoding="utf-16") as handle:
                handle.write(body)
        except OSError as error:
            messagebox.showwarning("Could not rewrite", str(error), parent=self)
            return

        messagebox.showinfo(
            "Saved",
            "Saved to:\n%s\n\nOpen it in Notepad to see exactly what it changes. "
            "To apply: right-click it and choose Merge, accepting the "
            "administrator prompt. Restart Mavis afterwards.\n\n"
            "To undo, delete the added entries under\n"
            "HKLM\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens." % path,
            parent=self)

    def on_close(self):
        return {"rate": self.rate.get(), "volume": self.volume.get()}


if __name__ == "__main__":
    VoiceLab().mainloop()
