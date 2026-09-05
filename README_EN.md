# Dread Hunger Linux Server Toolkit

[简体中文](README.md) | **English**

This toolkit helps you manage a self-hosted Dread Hunger server on Linux. It includes:

- A Linux web server manager for starting, stopping, configuring, and managing plugins.
- A Linux GM web console for viewing players and running GM commands.
- A Frida injector and server-side plugins.
- Windows clients for server management, GM administration, and quick joining.
- Linux scripts for one-click installation, startup, shutdown, and status checks.

> Compatibility: The plugin memory offsets currently target the Dread Hunger Finale 1.2.4 Linux server build. If the game binary is updated, the offsets must be verified again. Do not inject these plugins into an unknown version.

## Requirements

- At least 4 GB of RAM is recommended. Configure swap on low-memory systems because the game server, two web services, and Frida run at the same time.
- Python 3.10+, `venv`, and `pip` are required. If dependencies are missing, the installer will use `apt-get`, `dnf`, or `yum`, so root access or working `sudo` access is required.
- Installing Frida requires access to PyPI. If PyPI is slow or unavailable in your region, set the standard `PIP_INDEX_URL` environment variable to a suitable mirror before running the installer.
- The installer only checks that the server directories and binary exist; it does not verify the game version. Confirm manually that your server is Finale 1.2.4 before starting. Do not inject the included plugins into other versions.

## Files Not Included

The repository and Releases **do not include** the Dread Hunger game, the Linux server `Engine/` and `DreadHunger/` directories, PAK files, debug symbols, `DHConnector.exe`, or `dhpow.dll`. You must supply legally obtained, version-compatible files yourself.

A complete Linux directory should look like this:

```text
LinuxServer/
├── Engine/                         # Supplied by the user
├── DreadHunger/                    # Supplied by the user
│   └── Binaries/Linux/
│       └── DreadHungerServer-Linux-Shipping
├── Linux 插件/                     # Linux plugins
├── 开服器/                         # Server manager
├── GM控制台/                       # GM console
├── install.sh
└── dhctl.sh
```

## One-Click Linux Deployment

1. Download and extract `DreadHunger-Linux-Toolkit.tar.gz` from GitHub Releases.
2. Copy the matching `Engine/` and `DreadHunger/` directories into `LinuxServer/`.
3. Run the following commands on the Linux server:

```bash
cd LinuxServer
chmod +x install.sh dhctl.sh
./install.sh
```

The installer will:

1. Check for Python 3.10+ and the complete game server files.
2. Create an isolated `.venv` and install the pinned Frida version.
3. Ask for the public IP address or domain, three ports, and two separate passwords.
4. Start the server manager and GM console.
5. Start the game server through the server manager, which also starts the Frida injector automatically.
6. Display the addresses required by the Windows clients and quick-join tool.

When the installer runs as root and finds the `www` user commonly used by BT Panel, the game and Frida processes run as `www`. The installer automatically creates a writable `.gm_runtime/` directory used only for GM communication; it does not require changing ownership of the entire project. If the project is under `/root` or another parent directory inaccessible to `www`, installation stops with a clear error. Move the project to `/opt`, `/srv`, or `/www/wwwroot` and run the installer again.

For later use:

```bash
./dhctl.sh start
./dhctl.sh status
./dhctl.sh restart
./dhctl.sh stop
```

To change the IP address, ports, or passwords:

```bash
DH_RECONFIGURE=1 ./install.sh
```

For unattended installation, all variables below must be supplied in one command. If any variable is missing, the installer lists the missing variables and exits:

```bash
DH_PUBLIC_HOST=SERVER_IP_OR_DOMAIN \
DH_BIND_HOST=0.0.0.0 \
DH_MANAGER_PORT=8800 \
DH_GM_PORT=9900 \
DH_GAME_PORT=9100 \
DH_MANAGER_PASSWORD='manager-password-at-least-8-characters' \
DH_GM_PASSWORD='different-gm-password-at-least-8-characters' \
./install.sh
```

## Ports and Windows Clients

The default ports serve different purposes and must not be mixed up:

| Purpose | Default port | Protocol | Value entered in the Windows tool |
|---|---:|---|---|
| Server manager API | 8800 | TCP | `SERVER_IP:8800` + server manager password |
| GM API | 9900 | TCP | `SERVER_IP:9900` + GM password |
| Game server | 9100 | UDP | Enter `SERVER_IP:9100` in the quick-join tool |

Allow the corresponding ports in your cloud security group, system firewall, and the BT Panel **Security** page. The game port uses UDP; the manager and GM ports use TCP. It is strongly recommended to restrict ports 8800 and 9900 to the administrator's public IP address instead of exposing them to the entire internet.

```bash
# Example for Ubuntu/Debian using ufw
sudo ufw allow 9100/udp
sudo ufw allow from ADMIN_PUBLIC_IP to any port 8800 proto tcp
sudo ufw allow from ADMIN_PUBLIC_IP to any port 9900 proto tcp

# Game-port example for CentOS/RHEL using firewalld
sudo firewall-cmd --permanent --add-port=9100/udp
sudo firewall-cmd --reload
```

After you save `server_port` in the server manager, it is automatically synchronized with `game_port` in `deploy_config.json`. Both `dhctl status` and the displayed join address will use the actual game port. If these two values differ after upgrading from an older version, save the configuration once in the server manager.

Players can download `DreadHungerQuickJoin.exe` from the GitHub Release and enter the game address displayed after installation. The quick-join tool still requires compatible copies of `DHConnector.exe` and `dhpow.dll` on the player's computer. This project does not distribute those third-party components.

## Plugin Changes and Upgrades

- The injector reads plugin files only when it establishes a Frida session. After adding, deleting, renaming, or editing a plugin, click **Restart Injector** in the server manager, or wait until the current match ends and the next injection begins, before the change takes effect.
- Before upgrading, run `./dhctl.sh stop` and back up `deploy_config.json`, `开服器/manager_config.json`, the GM blacklist, and any custom plugins. Replace the program files, then run `./install.sh` again.
- The current injector finds the game server by process name, so running multiple instances reliably on one machine is not supported. Do not start multiple server instances at the same time; even with different ports, Frida may inject into the wrong process.

## Build the Windows EXE Files from Source

Run the following commands in Windows PowerShell:

```powershell
cd WindowsRemote
python -m pip install pyinstaller
.\build_exe.ps1
.\build_quick_join.ps1
```

Build artifacts are written to `WindowsRemote/dist/`.

## Create a GitHub Release

The repository includes `.github/workflows/release.yml`. After you push a version tag beginning with `v`, GitHub Actions builds the three Windows EXE files, packages the Linux toolkit, and uploads all artifacts to the matching Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## License and Noncommercial Use

Original code, documentation, and assets that the licensor has authority to license are covered by **PolyForm Noncommercial License 1.0.0**. [LICENSE](LICENSE) preserves the [official English terms](https://polyformproject.org/licenses/noncommercial/1.0.0) unchanged and appends this project's `Required Notice:` copyright notice. This is a source-available noncommercial license, not an OSI-defined open-source license. The following summary does not add to, remove, or replace the license terms.

- Noncommercial use, modification, and distribution under the terms are permitted, including personal study, experimentation, private entertainment, and hobby projects without any anticipated commercial application.
- Ordinary individuals or companies selling tools, operating paid servers, selling VIP access, providing paid deployment, or monetizing through advertising generally engage in commercial use outside the general noncommercial permission. Assess each use against the complete terms; modification or compilation does not itself grant commercial rights.
- The official terms expressly permit use by charitable organizations, educational institutions, public research organizations, public safety or health organizations, environmental protection organizations, and government institutions regardless of funding sources or resulting obligations. This is not a blanket commercial-use prohibition for every entity.
- Anyone receiving any part of the software must also receive the terms or their URL and all `Required Notice:` lines supplied by the licensor. Third-party materials retain their own license requirements.
- Following the first written violation notice, licenses can continue if the recipient comes into full compliance and takes practical steps to correct past violations within 32 days; otherwise, licenses end as specified in the Violations clause.
- Donations, cost sharing, and sponsorship require assessment of the actual purpose and full terms; this summary creates no separate blanket permission or prohibition.

The game, Frida, Python, and other third-party components retain their own licenses; this project cannot grant rights on their behalf. Contributors should confirm their authority to license contributions under these terms and retain third-party provenance and license information.

**Earlier licenses:** Commit `78f6a37` adopted MIT; `9648808` replaced it with noncommercial terms. This change cannot withdraw previously valid MIT permissions or prevent commercial use of the corresponding earlier code under those permissions. Later additions do not automatically receive the earlier MIT license. Ownership and third-party permissions depend on actual provenance; repository notices are not a completed ownership audit.

## Security Notes

- The generated `deploy_config.json` stores management passwords, is assigned mode `600`, and is excluded by `.gitignore`.
- Passwords are passed to background services through environment variables and do not appear in process command lines or GM logs.
- Do not commit `.runtime/`, logs, `manager_config.json`, `gm_commands.json`, game binaries, or plugin backups.
- When exposing management services over the internet, consider adding a cloud firewall, VPN, or HTTPS reverse proxy.
