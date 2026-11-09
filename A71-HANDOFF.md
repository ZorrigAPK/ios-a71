# iOS 16.7 on Galaxy A71 (SM-A715F) — handoff (2026-11-09)

Port of dipa-studio/ios-sweet (Redmi Note 10 Pro, SM7150) to the Samsung Galaxy A71 (same SM7150).
Fork: https://github.com/ZorrigAPK/ios-a71 (this folder). Work files: `C:\Users\Techr\ios-a71-tools`.

## Status
- **iOS 16.7.16 reaches the lock screen** (boot.img 4+). Volume/power keys work (laggy, ~5 fps CPU rendering).
- **Touch: in progress** (patch `xnu/patches/0082-a71-sec-ts-bitbang-touch.patch`).
- Not working: touch, USB (controller off at boot on A71), Wi-Fi, audio, modem, camera, real time/date.

## Phone layout
- `boot` = shim (ios-a71-tools/shim-build/Image) + payload (XNU kernel + ADT) packed by `tools/a71-mkboot.py`
  (template header = `ios-a71-tools/backup/boot.img`).
- `recovery` = TWRP 3.7.1 (Kitchannel2010/twrp_a71). Enter: Vol- + Power ~7 s, then Vol+ + Power.
- `vbmeta` = verification disabled (`ios-a71-tools/work/vbmeta-disabled.img`).
- `userdata` (/dev/block/sda32) = iOS HFS+ image (`\\wsl.localhost\Ubuntu\root\ios-root\ios16-root.img`,
  tweaks from tools/sweet-root-tweaks.py applied). One UI/UN1CA is gone (reinstall UN1CA zip from TWRP if needed).
- Partition backups + SHA256SUMS: `ios-a71-tools/backup` (efs, sec_efs, persist, modemst*, ...).

## Build / flash loop
1. Kernel: push to `xnu/patches/**` -> GitHub Actions `xnu` on **macos-15-intel** (~15 min). Download artifact `xnu-kernel`.
2. Payload: `python tools/mkpayload.py KERNEL ios-a71-tools/a71-build/a71-hi-4.adt OUT.bin --cmdline "..."`
   cmdline: `debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=30 sweetsample=SpringBoard,lsd,installd`
3. Boot: `python tools/a71-mkboot.py ios-a71-tools/backup/boot.img ios-a71-tools/shim-build/Image OUT-boot.img OUT.bin`
4. Flash from TWRP: `adb push OUT-boot.img /tmp/ios-boot.img; adb shell dd if=/tmp/ios-boot.img of=/dev/block/by-name/boot bs=4194304`, verify sha256, `adb reboot`.
5. Kernel log after a boot (from TWRP): `adb exec-out "dd if=/dev/block/sda32 bs=4096 skip=28742366 count=1025" > x.bin`
   then `python tools/sweet-log.py x.bin x.txt`. Symbolicate with ipsw in WSL (`/root/dsc/dyld_shared_cache_arm64`).

## A71-specific facts found
- RAM: upper bank ends 0x1_fcb00000 (mkadt HIGH_MEM_SIZE 0xfcb00000); 0xb0000000-0xb01fffff is a Samsung carve-out -> --highmem only.
- Framebuffer 0x9c000000 1080x2400, GIC, UFS addresses identical to sweet.
- ADT `/chosen` needs `mac-address-wifi0/bluetooth0/ethernet0`, else MobileGestalt waits forever for IONetworkController and SpringBoard never draws.
- Touch IC: Samsung S6SY761/Y771 ("sec,sec_ts", fw y771_a71) at I2C 0x48 on SE7 (SDA GPIO6, SCL GPIO7, IRQ GPIO9 active low).
  SE7 has GENI_IF_DISABLE_RO=1 (FIFO off, GSI only) -> driver bit-bangs GPIO6/7.
  Power: tsp_ldo 3.3 V = TLMM GPIO56 in the **WEST** tile (0x3500000; GPIOs 4/6-9/90 are NORTH 0x3900000);
  dvdd 1.8 V = PM6150 GPIO4 (SPMI ppid 0x0c3, regs 0xC3xx).
  Boot 6: GPIO56 high OK, SDA/SCL/IRQ still 0 -> dvdd missing. Commit d9aeb85 adds the SPMI write of PM6150 GPIO4
  (CI run 42682110111): next step = flash it as boot.img 7 and read the "SWEET TOUCH A71" log lines.
  sec_ts protocol used: 0x52 id, 0x55 boot status (0x20 app mode), 0x23 panel info, 0x10 sense on,
  0x60 one event / 0x61 all events (8 bytes: eid=b0&3, tid=(b0>>2)&15, state=b0>>6, x=b1<<4|b3>>4, y=b2<<4|b3&15, left=b7&0x3f).
- Edited driver source: `ios-a71-tools/a71-build/sweet_touch.current.c`; regenerate the patch with the WSL script that
  applies 0060/0062/0063 to /root/touchsrc and diffs (see git history of 0082).

## PC environment
- WSL Ubuntu 26.04 runs a custom kernel with HFS+ (`%USERPROFILE%\.wslconfig` -> ios-a71-tools/wsl-kernel/bzImage-hfsplus;
  delete .wslconfig to revert). Tools in WSL: apfs-fuse (/usr/local/bin), hfsprogs, ipsw (/usr/local/bin), gcc-13.
- samloader (`ios-a71-tools/samloader`) flashes in download mode; partition names are BOOT/VBMETA/RECOVERY.
