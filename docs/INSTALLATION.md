# Installation and Scheduling

CtxZip is a Python 3.10+ command-line application with no third-party runtime dependencies. It reads local session sources for the operating-system user that runs it and writes derived data to the configured private archive.

## Install

Clone the repository:

```sh
git clone https://github.com/halilogia/CtxZip.git
cd CtxZip
```

Create the private settings file with the command for your shell:

```powershell
Copy-Item ctxzip.settings.example.json ctxzip.settings.json
```

```sh
cp ctxzip.settings.example.json ctxzip.settings.json
```

On Windows, install Python 3.10 or newer and use the Python launcher (`py -3`) or the full path to `python.exe`. On macOS and Linux, use an installed Python 3 executable (`python3`). Confirm the interpreter before running CtxZip:

```powershell
py -3 --version
py -3 ctxzip.py --help
```

```sh
python3 --version
python3 ctxzip.py --help
```

Edit the private settings file so the archive and source roots match this account. The sample includes a model placeholder; automatic summarization will reject it until `llm.model` is set to a provider model. API keys belong in the configured environment variable (default `CTXZIP_API_KEY`), not in the settings file or repository.

For a first local run, inspect the discovered projects with `status`/`durum`, then run `all --manual`. Manual mode collects sources, creates transcripts and prompt files, and makes no provider request:

```powershell
py -3 ctxzip.py --settings ctxzip.settings.json all --manual
py -3 ctxzip.py --settings ctxzip.settings.json status
```

```sh
python3 ctxzip.py --settings ctxzip.settings.json all --manual
python3 ctxzip.py --settings ctxzip.settings.json status
```

Run `python scripts/install_hook.py` once per clone if you want the staged-file privacy check installed. The hook is local Git configuration and is not copied by `git clone`.

## Schedule unattended collection

Schedule the same manual-mode command with the same OS account that owns the AI tool sessions and settings. Use an absolute path to the Python executable, `ctxzip.py`, and the private settings file; set the working directory to the cloned repository. Start with a modest interval such as hourly. A run collects files available at that time; it does not launch coding tools, export cloud chats, or guarantee that an active session is complete.

Manual mode is the safe default for unattended runs. It does not send prompts to an LLM. Do not add `--onayli-gonder` to a scheduled task unless you deliberately want to bypass the per-request confirmation and send session text to the configured provider. Secret cleanup is limited and cannot guarantee that every sensitive value is removed. Logs may contain project names or operational details, so keep them outside the repository and restrict their access.

### Windows Task Scheduler

1. Find the interpreter path with `py -3 -c "import sys; print(sys.executable)"`.
2. In Task Scheduler, create a task with a time trigger and a **Start a program** action.
3. Set **Program/script** to the full `python.exe` path.
4. Set **Add arguments** to the quoted absolute `ctxzip.py` path followed by `--settings`, the quoted absolute settings path, and `all --manual`. For example:

   ```text
   "<repository-root>\ctxzip.py" --settings "<repository-root>\ctxzip.settings.json" all --manual
   ```

5. Set **Start in** to the repository directory and configure the task to run as the account whose session files should be collected.

Task Scheduler separates the executable, arguments, and working directory in its action configuration; see [Microsoft's Task Actions reference](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-actions) and [WorkingDirectory reference](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-workingdirectory-exectype-element).

### macOS `launchd`

Use a per-user LaunchAgent. Get the Python executable path with `python3 -c 'import sys; print(sys.executable)'`. Create the log directory with private permissions, then replace every example path below with an absolute path for this account:

```sh
mkdir -p "$HOME/.local/state/ctxzip"
chmod 700 "$HOME/.local/state/ctxzip"
mkdir -p "$HOME/Library/LaunchAgents"
```

Save this as `$HOME/Library/LaunchAgents/com.ctxzip.collect.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ctxzip.collect</string>
  <key>ProgramArguments</key>
  <array>
    <string>/absolute/path/to/python3</string>
    <string>/absolute/path/to/CtxZip/ctxzip.py</string>
    <string>--settings</string>
    <string>/absolute/path/to/CtxZip/ctxzip.settings.json</string>
    <string>all</string>
    <string>--manual</string>
  </array>
  <key>WorkingDirectory</key><string>/absolute/path/to/CtxZip</string>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardOutPath</key><string>/absolute/path/to/.local/state/ctxzip/stdout.log</string>
  <key>StandardErrorPath</key><string>/absolute/path/to/.local/state/ctxzip/stderr.log</string>
</dict>
</plist>
```

Load and run it in the logged-in user's session:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.ctxzip.collect.plist"
launchctl kickstart -k "gui/$(id -u)/com.ctxzip.collect"
```

`StartInterval` is in seconds. Apple documents per-user agents and interval/calendar scheduling in [Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) and [Scheduling Timed Jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html). Keep the log directory private because output is local archive-adjacent operational data.

### Linux `systemd` user timer

Create `~/.config/systemd/user/ctxzip.service`:

```ini
[Unit]
Description=Collect local AI coding sessions with CtxZip

[Service]
Type=oneshot
WorkingDirectory=%h/src/CtxZip
ExecStart=/usr/bin/python3 %h/src/CtxZip/ctxzip.py --settings %h/src/CtxZip/ctxzip.settings.json all --manual
```

Create `~/.config/systemd/user/ctxzip.timer`:

```ini
[Unit]
Description=Run CtxZip collection hourly

[Timer]
OnCalendar=hourly
Persistent=true
Unit=ctxzip.service

[Install]
WantedBy=timers.target
```

Replace `/usr/bin/python3` and `%h/src/CtxZip` with the interpreter and checkout paths on this machine. Then enable and inspect the timer:

```sh
systemctl --user daemon-reload
systemctl --user enable --now ctxzip.timer
systemctl --user start ctxzip.service
systemctl --user list-timers ctxzip.timer
journalctl --user -u ctxzip.service
```

`Persistent=true` allows a calendar timer to catch up a missed run when its user service manager becomes active again. User-service lifetime and login behavior depend on the Linux distribution configuration. See the [systemd timer unit documentation](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml) and [service unit documentation](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml).

## Disable scheduling

- Windows: disable or delete the task in Task Scheduler.
- macOS: run `launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.ctxzip.collect.plist"` and remove the plist if it is no longer needed.
- Linux: run `systemctl --user disable --now ctxzip.timer` and remove the two user unit files.

Scheduling is optional. Run the CLI manually when you want a foreground LLM approval flow or a context pack for a specific task.
