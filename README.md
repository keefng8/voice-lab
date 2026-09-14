# Voice Lab

Hear every speech voice on this machine and find the ones your assistant cannot reach. Windows keeps voices in two registry locations and pyttsx3 reads only the older one, so the newer and usually better voices are installed, working, and invisible. Speaks through .NET System.Speech, so nothing needs installing.

A feature for [Mavis AI](https://www.mavis-ai.com) — a desktop voice assistant.

```
You: "open voice lab"
```

Mavis opens it and stands its own panels down so they are not in your way. Say *"show the interface"* to bring them back.

## Install

From the Mavis Appstore — find **Voice Lab** and click Install.

Or install it directly:

```python
from utils.feature_install import install_from_github
install_from_github("https://github.com/keefng8/voice-lab")
```

## What you can say

- *"open voice lab"*
- *"change mavis's voice"*
- *"what voices do i have"*
- *"the voice sounds robotic"*

These are not matched word for word. Mavis gives them to its language model as examples of intent, so close variations work too.

## How it works

Windows keeps speech voices in two registry locations and pyttsx3 - which is what most assistants speak through - reads only the older SAPI5 one. On the machine this was built on that meant two voices were available to the assistant while five were installed, and the three it could not see were the newer, better-sounding ones including the only male British voice. Nothing anywhere said so. There is a second trap underneath it: System.Speech is a .NET API, and Windows PowerShell 5.1 (.NET Framework) enumerates only the old voices while PowerShell 7 (.NET Core) sees both sets - so built against 5.1 this feature confidently reported that nothing was hidden, which was the exact opposite of the truth. It prefers pwsh and says so when only 5.1 is available. The registry fix is offered as a .reg file to read and apply yourself, never applied silently: a feature that edits HKLM on its own is not one anybody should install.

## Requirements

Python 3.8 or newer, and nothing else — the standard library only. No `pip install`, no model to download, no account.

## Building your own

See [Building features for Mavis](https://github.com/keefng8/mavis-feature-docs) — a feature is just a GitHub repository with a `mavis.json`.

## License

MIT — see [LICENSE](LICENSE).
