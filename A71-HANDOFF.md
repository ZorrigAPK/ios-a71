# iOS 16.7 on the Galaxy A71 (SM-A715F) — full handoff

Read this whole file before touching anything. It records what was done, exactly how, and every trap
already hit, so the next session does not repeat them. Last update: 2026-11-09 (evening).

Port of `dipa-studio/ios-sweet` (Redmi Note 10 Pro "sweet", Snapdragon 732G / SM7150) to the Samsung
Galaxy A71 (Snapdragon 730 / SM7150, same SoC family). Fork: https://github.com/ZorrigAPK/ios-a71
(local clone `C:\Users\Techr\ios-a71`). Work files: `C:\Users\Techr\ios-a71-tools`.
The user (French speaker) owns the phone outright (bought new in a shop in 2022, no credit).
Talk to them in French, simply; they press buttons and send photos of the screen.

---------------------------------------------------------------------------------------------------
## 1. Current status

| Item | State |
|---|---|
| iOS 16.7.16 (iPhone X userland) boots to the **lock screen** | WORKS (since boot.img 4) |
| Volume / power keys (sweet_keys.c, PMIC SPMI reads) | WORK (laggy) |
| Display | CPU-rendered, ~5 fps, `sweetfb_hz=30`; slow but correct |
| Touch (Samsung S6SY761/Y771 "sec_ts") | **WORKS** since boot 10 (user confirmed 2026-11-10); accuracy of axes/scale not yet checked — see section 6 |
| USB device mode | not working (USB30 GDSC/clocks are OFF at boot on the A71, unlike sweet) |
| Wi-Fi, BT, audio, modem, camera, GPU, real date/time | not working (no drivers) — expected |

Next concrete step: see section 9.

---------------------------------------------------------------------------------------------------
## 2. Phone state (partitions)

| Partition | Content |
|---|---|
| `boot` (sda21, 64 MB) | our boot.img: shim `Image` as kernel + payload (XNU + ADT + cmdline) as ramdisk + A71 DTB |
| `recovery` | **TWRP 3.7.1** (github.com/Kitchannel2010/twrp_a71 release 23218374983, MD5 of img 3d3970944826e797564610b0b0c18c15) |
| `vbmeta` | verification disabled (flags=3): `ios-a71-tools/work/vbmeta-disabled.img` |
| `userdata` (`/dev/block/sda32`, 117.7 GB) | first 16 GB = iOS HFS+ image; last 4 MiB = kernel log ring |
| One UI / UN1CA | **gone** (userdata replaced, user agreed). To return to Android: TWRP -> Format Data -> sideload UN1CA 3.2.1 zip (MD5 1f12956da711674edae3320e3ee9fceb) -> sideload Magisk-v31.1.zip |

Backups of all important partitions (efs, sec_efs, persist, modemst1/2, fsg, fsc, boot, recovery, dtbo,
vbmeta, vbmeta_samsung, param, devinfo, persistent) + `SHA256SUMS.txt`: `ios-a71-tools\backup`.
Stock Samsung firmware A715FXXSBDXB1 (XEF): `ios-a71-tools\firmware` (BL/AP/CP/CSC .tar.md5).

### Getting into TWRP
Vol- + Power ~7 s (screen off), then immediately Vol+ + Power until the TWRP logo. USB cable plugged.
`adb devices` then shows `recovery product:twrp_a71`. TWRP's adb shell is root.
Download mode (if ever needed): Vol- + Power, then Vol+ + Vol- , then Vol+ on the blue screen.

---------------------------------------------------------------------------------------------------
## 3. The build -> flash -> log loop (the core workflow)

Tools: adb = `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`; gh = `C:\Program Files\GitHub CLI\gh.exe`
(logged in as ZorrigAPK, git uses it via `gh auth setup-git`). Python 3.13 on Windows (`python -I`).

### 3.1 Kernel (XNU) — GitHub Actions only (no Mac here)
- Any push touching `xnu/patches/**` or `.github/workflows/xnu.yml` starts workflow `xnu`.
- Runner MUST be `macos-15-intel` (set in xnu.yml). `macos-14` images are retired ("configuration not
  supported"); `macos-15` arm64 jobs were "not acquired ... capacity constraints" and cancelled after 15 min.
- Build takes ~15-20 min. Watch: `gh run list -R ZorrigAPK/ios-a71 -w xnu -L 1`.
  NOTE: `gh run watch` died once on "unexpected EOF" (network) while the build kept running — poll with
  `gh run view <id> --json status,conclusion` instead. Do not trust a single watcher failure.
- Download: `gh run download <id> -R ZorrigAPK/ios-a71 -n xnu-kernel -D <dir>` -> `kernel.development.sweet` (~17 MB).

### 3.2 Payload + boot.img (Windows, pure Python)
```
python -I tools\mkpayload.py <kernel.development.sweet> ios-a71-tools\a71-build\a71-hi-4.adt payload.bin --cmdline "<CMDLINE>"
python -I tools\a71-mkboot.py ios-a71-tools\backup\boot.img ios-a71-tools\shim-build\Image out-boot.img payload.bin
```
CMDLINE in use (boot 4..7):
`debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=30 sweetsample=SpringBoard,lsd,installd`
- `sweetfb_noconsole=1` hides the kernel console only once the GUI presents its first frame. If the
  console stays on screen, the GUI never drew (that is a diagnosis, not a bug of the flag).
- `sweetsample=` lists processes whose thread stacks are sampled into the log (default SpringBoard,backboardd).
- `a71-mkboot.py` copies header fields, cmdline and DTB from the template boot.img (Samsung ABL accepts it).
- The ADT is generated by `python -I tools\mkadt.py OUT.adt --highmem` (needs `research/ipsw-x/d22ap.adt`,
  extracted from the IPSW with `tools/adt.py unwrap`; not in git).

### 3.3 Flash boot from TWRP (fast, ~5 s)
```
adb push out-boot.img /tmp/ios-boot.img
adb shell 'dd if=/tmp/ios-boot.img of=/dev/block/by-name/boot bs=4194304; sync; S=$(stat -c %s /tmp/ios-boot.img); head -c $S /dev/block/by-name/boot | sha256sum'
adb reboot
```
Always compare the sha256 with the local file before rebooting.
PowerShell trap: put the adb shell command in SINGLE quotes, otherwise PowerShell expands `$(...)`.

### 3.4 Read the kernel log after a boot (from TWRP)
The kernel (patch 0047) keeps a 4 MiB console ring in the last 1025 blocks of userdata.
```
cmd /c "adb exec-out \"dd if=/dev/block/sda32 bs=4096 skip=28742366 count=1025 2>/dev/null\" > ios-a71-tools\logs\bootN.bin"
python -I tools\sweet-log.py ios-a71-tools\logs\bootN.bin ios-a71-tools\logs\bootN.txt
```
(skip = 117732929536/4096 - 1025). Use `cmd /c` redirection: PowerShell `>` corrupts binary output.
The decoded text contains NUL bytes: in WSL use `grep -a`.
Logs of every boot so far: `ios-a71-tools\logs\boot2.txt, boot3.txt, boot5.txt, boot6.txt`.

### 3.5 Symbolicate user-space stacks (WSL)
`SMP <proc>[pid] slide 0x... mh 0x...` + `SMP <proc> tN pc .. lr .. sp .. bt ...` lines are samples.
In WSL Ubuntu: `ipsw dyld a2s /root/dsc/dyld_shared_cache_arm64 <addr - slide>`.
Helper used: scratch script that loops over the addresses (slide differs every boot; skip `sp`).
`ipsw` = blacktop/ipsw 3.1.743 (`/usr/local/bin/ipsw`). Cache copied from the iOS image to `/root/dsc`.

### 3.6 Writing the whole iOS image (only if the image changes; erases userdata)
In TWRP: `adb shell umount /data` then
`cmd /c "adb exec-in \"dd of=/dev/block/sda32 bs=4194304\" < \\wsl.localhost\Ubuntu\root\ios-root\ios16-root.img"` (~9.5 min),
then verify `adb shell 'dd if=/dev/block/sda32 bs=4194304 count=4096 | sha256sum'` against
`/root/ios-root/ios16-root.img.sha256` (current: 191221808239c0a0e40664f3b34d538bfb1fb4247693310ad926a5280d9dd684).
TWRP trap: its `/sdcard` is a 2.2 GB tmpfs (data cannot be decrypted) — never `adb push` big files there.

---------------------------------------------------------------------------------------------------
## 4. How the iOS image was made (WSL)

- IPSW: iPhone10,3/10,6 iOS 16.7.16 (20H392), official Apple URL
  `https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-77006/1158E502-D76D-4226-AA06-ED5E30CD1111/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw`
  SHA1 5606c298c1d908f8a48f617f0ceaf71f2a9f0193 -> `ios-a71-tools\ipsw\`.
- DMGs extracted to `/root/ipsw`: OS `087-86698-044.dmg`, SystemOS `087-86593-047.dmg`, AppOS `087-86715-047.dmg`
  (paths found in BuildManifest.plist, DeviceClass d22ap).
- `tools/mkiosroot.sh` (run an LF copy: the Windows checkout has CRLF -> "set: pipefail: invalid option").
  It stops at `install -o 272` ("invalid user '272'": Ubuntu 26.04's install rejects unknown numeric owners);
  the remaining steps (logd dirs owned 272:272 + .migrated, systembag.kb keybag) were done by hand with chown.
- Then `tools/sweet-root-tweaks.py` on the mounted image (CommCenter removed, Setup skipped, watchdogs off,
  VirtualAudio/StartRecorderServer off, migration skipped). Data ark step skipped (no container yet) — harmless.
- `fsck.hfsplus -f -y` twice. `fsck -n` still reports "Volume header needs minor repair": normal with the Linux tool.

### WSL environment (do not lose)
- Ubuntu 26.04 in WSL2. WSL boots a **custom kernel with HFS+ built in**:
  `%USERPROFILE%\.wslconfig` -> `kernel=C:\\Users\\Techr\\ios-a71-tools\\wsl-kernel\\bzImage-hfsplus`.
  Delete `.wslconfig` (+ `wsl --shutdown`) to go back to Microsoft's kernel. Why: Microsoft's WSL kernel has no
  hfsplus; an out-of-tree module was rejected ("disagrees about version of symbol module_layout"), so the
  kernel itself was rebuilt (source /opt/WSL2-Linux-Kernel tag linux-msft-wsl-6.6.87.2, gcc-13 because GCC 15
  breaks the 6.6 build, BTF and IKHEADERS disabled).
- apfs-fuse built from sgan81/apfs-fuse in /opt (needs `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` and
  `#include <cstdint>` added to ApfsLib/PList.h).
- PowerShell -> `wsl bash -c '...'` mangles quotes and pipes: write a .sh file and run `wsl -u root -- bash /mnt/c/.../x.sh`.

---------------------------------------------------------------------------------------------------
## 5. A71 hardware facts discovered (and the fix each needed)

| Fact | Where it mattered |
|---|---|
| Samsung ABL has a hidden fastboot (getvar only): `fastboot boot`/`reboot` = "unknown command" | no temporary boot: flash `boot` instead |
| Every custom image needs `vbmeta` disabled flashed with it, else download mode says FAIL! Auth | first flashes |
| KG STATUS PRENORMAL blocks all custom flashing; it turned CHECKING by itself after Wi-Fi/time | root, TWRP |
| RAM: `b0200000-1fcafffff` System RAM (TWRP /proc/iomem); 0xb0000000-0xb01fffff Samsung carve-out | mkadt: `--highmem`, HIGH_MEM_SIZE 0xfcb00000 |
| Framebuffer cont_splash 0x9c000000 1080x2400 a8r8g8b8, GIC 0x17a00000/0x17a60000, UFS 0x1d84000 | identical to sweet: shim works unchanged |
| GPT: userdata starts at LBA 0x25c500, 4 KiB blocks | kernel finds it by name "userdata" |
| No IONetworkController and no MAC in ADT -> MobileGestalt waits forever (IOServiceMatching + runloop) -> lsd hangs in `_GenerateBuiltInAppInstallSessionID` while seeding -> SpringBoard never draws | ADT `/chosen` `mac-address-wifi0/bluetooth0/ethernet0` (synthetic 02:00:5e:71:a7:0x), commit 49481a8 |
| TLMM tiles (pinctrl-sdmmagpie.c): NORTH 0x3900000 (GPIO 4,6,7,8,9,90), WEST 0x3500000 (GPIO 56), SOUTH 0x3d00000 | touch power |
| PMIC SPMI arbiter v5: core 0x0c440000, cnfg 0x0c40a000, chnls (write) 0x0c600000, obsrvr (read) 0x0e600000; 0x80*apid | keys + touch dvdd |

---------------------------------------------------------------------------------------------------
## 6. Touch — what was done, step by step

Hardware (A71 dtbo, fragment@81 on `qupv3_se7_i2c`): candidates sec_ts@0x48 (A71, firmware
`tsp_sec/y771_a71.bin`), melfas mms@0x48 and imagis ist40xx@0x50 (those two are A70s variants sharing the dtbo).
Pins: SDA GPIO6, SCL GPIO7 (`melfas,sda/scl-gpio`), IRQ GPIO9 active low.
Power: `tsp_ldo_en`/`tsp_ldo_avdd` = regulator-fixed 3.3 V on TLMM GPIO56 (enable-active-high);
`sec,dvdd_gpio` = PM6150 GPIO4. DT says regulator-boot-on but on iOS boot both were OFF.

1. boot 5 (first driver): `SE7 IF_DISABLE=0x1` -> SE7 FIFO interface disabled by Samsung's QUP firmware
   (GSI/DMA only) — that is why sweet's FIFO driver printed "need ABL-loaded I2C firmware and 32-bit FIFOs".
   New path: bit-banged open-drain I2C on GPIO6/7 (patch 0082). Result: START failed EBUSY, SDA=SCL=0.
2. boot 6: added tsp_ldo enable. First version read GPIO56 in the NORTH tile — WRONG (it is WEST).
   Fixed: GPIO56 before `cfg=0x1 io=0`, after `cfg=0x240 io=0x3` (rail on). SDA/SCL/IRQ still 0 -> dvdd missing.
3. boot 7 (commit d9aeb85, CI run 42682110111): writes PM6150 GPIO4 over SPMI (owner channel), only if APID
   owned by EE 0 and subtype LV/MV (0x10-0x13): MODE_CTL 0x40=0x01, OUT_SRC 0x44=0x80, OUT_CTL 0x45=0x01,
   EN_CTL 0x46=0x80; logs regs before/after and SDA/SCL. Then GPIO56, wait 150 ms, probe.

Driver source: `ios-a71-tools\a71-build\sweet_touch.current.c` (= sweet_touch.c after 0060+0062+0063 + our changes).
Regenerate the patch: in WSL `/root/touchsrc` holds the original file committed as base; the script
copies the edited file over it, writes `git diff` into `xnu/patches/0082-a71-sec-ts-bitbang-touch.patch`
(with a From/Subject header) and re-applies 0060/0062/0063/0082 to an empty repo to verify the series.
Before re-running it: `cd /root/touchsrc && git checkout bsd/dev/sweet_touch.c`.

sec_ts / S6SY761 protocol used: 0x52 device id (3 B), 0x55 boot status (0x20 = app mode), 0x23 panel
info (max x/y be16), 0x62 clear stack, 0x10 sense on, 0x60 one event (8 B), 0x61 remaining events.
Event: eid=b0&3 (1 = coordinate), tid=(b0>>2)&15, state=b0>>6 (1 press, 2 move, 3 release),
x=b1<<4|b3>>4, y=b2<<4|(b3&15), left=b7&0x3f; scaled from panel max (default 4096) to 1080x2400.
Touch thread starts 45 s after boot (`sweettouchdelay`). Log lines to look for: `SWEET TOUCH A71:`.

If boot 7 still fails: check the `dvdd ...` lines (owner, subtype, write result, SDA/SCL after). If owner != 0
the PMIC GPIO belongs to another EE and must not be written; if SDA/SCL go high but no ACK, try the
imagis address 0x50 / melfas, and the IC may need a power-cycle (GPIO56 low 10 ms, high) before probing.
Axes may need swapping/inverting once events arrive.

---------------------------------------------------------------------------------------------------
## 7. Mistakes already made (do not repeat)

- samloader output redirected to a file hides the progress bar: blank lines after `TotalBytes` mean the
  partitions WERE flashed. It was misread once as "nothing written". Partition names in the PIT are upper
  case (BOOT, VBMETA, RECOVERY); samloader `-e` (NAND erase) is NOT a factory reset (metadata stays) and broke boots.
- A samloader session aborted mid-way leaves download mode stuck ("Unexpected handshake response"):
  the user must re-enter download mode by hand.
- samloader full-firmware flash fails on its own "super partition pre-flight check": use the user's Odin for full restores.
- Do not download unofficial binaries (TWRP builds from random hosts, Odin) on the user's behalf; the user
  downloads them, we verify hashes. Official sources only (Apple CDN, GitHub releases of the authors).
- Read the GPIO tile before touching a pin; read hardware state and log it before writing anything.

---------------------------------------------------------------------------------------------------
## 8. Commits on the fork (main)

153c4cb shim build workflow (Linux CI) · 0ec0295 macos-15 runner + a71-mkboot.py · 3fe36fe RAM size ·
a5e46fb macos-15-intel runner · 49481a8 MAC addresses in /chosen · 0ea2972 touch driver (bit-bang) ·
8e40156 GPIO56 WEST tile · d9aeb85 dvdd over SPMI · fd82047 first handoff.

---------------------------------------------------------------------------------------------------
## 9. Next steps (in order)

1. DONE 2026-11-09 ~20:40: boot.img 7 = `ios-a71-tools\a71-build\ios-a71-boot-7.img`
   (kernel of CI run 42682110111 in `ios-a71-tools\xnu-build-touch3`, ADT a71-hi-4.adt, CMDLINE of section 3.2),
   sha256 6ad50550b6022286bcfc170ac7783692605e3dae9569236436dd2d82b94a041c, written to `boot` from TWRP
   and verified, phone rebooted into iOS. TODO: ask the user if touch reacts (1 min after the lock screen,
   swipe up from the bottom bar), then go to TWRP and read the log (section 3.4) -> `SWEET TOUCH A71` and
   `dvdd ...` lines; save it as `ios-a71-tools\logs\boot7.txt`.
   RESULT boot 7 (log `logs\boot7.txt`): no touch. Last touch line was
   `dvdd apid=228 owner=0 read=1 subtype=0x11 mode=0 vin=0 src=0 out=0x1 en=0x80 status=0x80`, then nothing
   (no "write=" line): the thread stopped inside the first SPMI write. Cause: arbiter v5 owner (write)
   channel is at `chnls + 0x10000 * apid` (Linux pmic_arb_offset_v5), not `0x80 * apid` (observer only).
   Fixed in commit a4673e0 (CI run 42685604760, kernel in `ios-a71-tools\xnu-build-touch4`).
   Patch regeneration script now saved: `ios-a71-tools\scripts\regen-0082.sh` (run from PowerShell:
   `wsl -u root -- bash /mnt/c/Users/Techr/ios-a71-tools/scripts/regen-0082.sh`; Git Bash mangles /mnt paths).
   Git has no global identity: commit with `-c user.name=ZorrigAPK -c user.email=<same as previous commits>`.
1b. DONE 2026-11-09 ~21:05: boot.img 8 = `ios-a71-tools\a71-build\ios-a71-boot-8.img`, sha256
   dfdeed00496eef3b5fc799480b6a9c86d4bd98ef25b1213690760827990368b2, flashed + verified, rebooted into iOS.
   TODO: ask the user if touch reacts, then TWRP -> log -> `logs\boot8.txt`; look for
   `dvdd write channel pa=... status=...` and `dvdd write=1 -> ... SDA=1 SCL=1`, then the `sec 0x48 id` line.
   RESULT boot 8 (log `logs\boot8.txt`): dvdd write=1, SDA=SCL=1, IC ANSWERS:
   `sec 0x48 id err=0 ac 37 71 boot err=0 0x20 panel err=0 1000 1000`, sense on err=0, loop running.
   But no touch in iOS: 342 `event read err=5` lines in bursts (each printed line follows a successful
   read, so reads alternate OK/EIO). EIO = command byte NAK or left-count > 31; not distinguishable there.
1c. DONE 2026-11-09 ~21:30: commit 54fd7da (CI run 42690557034, kernel `xnu-build-touch5`) adds raw event
   dumps (`ev xx xx ...`), failing stage (`stage=` 1 START busy, 2 addr NAK, 3 data NAK, 4 rSTART busy,
   5 read-addr NAK) and `report mask=` lines; keeps the first event when left > 31.
   boot.img 9 = `a71-build\ios-a71-boot-9.img`, sha256
   5e7b201d2e0517c233c8dc69c1b8a3d8ea85ce8893e2ae2770f01d43088d9fba, flashed + verified, rebooted into iOS.
   TODO: user touches the screen, then TWRP -> `logs\boot9.txt` -> read `ev`/`stage`/`report` lines.
   Note: 8/8 CPUs do come up (`SWEET CPU: 8/8 CPUs initialized`); the ~2 fps is CPU rendering (and maybe
   low CPU frequency left by ABL: not checked yet).
   RESULT boot 9 (log `logs\boot9.txt`): 268 raw events, 0 read errors, 0 reports. Events are real:
   press `44 ..`, move `84 ..`, release `c4 .. 00 00 00 00`, status `1d ..`. Root cause: sec_ts uses
   eid 0 = COORDINATE (1 = status), tid 1-based; byte 7 = left_event:5 + max_energy:1 (bit 5 often set ->
   6-bit mask gave 33 -> boot 8 EIO). Fixed in commit cc66e80 (CI run 42694644230).
   Decoded raw range seen in boot 9: x 1965..4038, y 1561..4075 (of 4096) - corners never seen, maybe
   touched before the thread started (45 s). Axes/scale NOT yet validated.
   boot.img 10 (kernel `xnu-build-boot10`) sha256 28b9e6bd3d5ac4fa846a5ee338de435b8dfee0bc3b2d8b900bec5d95ed6f9e8b
   flashed + verified + rebooted 2026-11-09. TODO: user test, then TWRP -> `logs\boot10.txt`, `report mask=` lines.
   Automation: `ios-a71-tools\scripts\build-flash.ps1 -RunId <id> -N <n>` waits for CI, builds boot N,
   flashes from TWRP, checks sha256, reboots.
2. Fix axes/scale if needed; then consider IRQ-driven polling to save CPU.
3. Speed: compare `cpus=8` vs `cpus=6`, check the sampler for SpringBoard/backboardd CPU use.
4. USB device mode (A71 ABL leaves USB30 off: GDSC + clocks must be enabled before patch 0072-0077 logic).
