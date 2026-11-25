# Shared SD Wi-Fi update

The USB controller was already in host mode in the radar and shared-profile
device trees. The FPGA bitstreams, device trees, boot script, and saved boot
profile remained the same. A normal reboot still selected `hash`; radar was
started for this session using the existing one-time boot command.

- The board verified the Wi-Fi tools and ARM kernel transfers with SHA-256.
  The active `/boot/zImage` is
  `f993f0a6d26c6c94a636e3377cde79089a7bc3b716d3c2ce25704d498f4de85a`.
  The original kernel is backed up on the SD card as `/boot/zImage.pre-wifi`.
  Both kernel module directories are present under `/lib/modules`.
- ARM userspace binaries were exercised with QEMU and the board. Linux
  registered the expected `mt76x0u` driver and the Wi-Fi startup process ran
  with no adapter supplied. The regulatory query worked.
- All versioned imports matched for Hash, Vision, FX, and Chain4; the last two
  retained their existing drivers with both compatible releases allowed in
  their start scripts. The explicit board boot into the unchanged default
  profile started the hash service and a hardware SHA-256 matched the software
  reference. FX, Chain4, and Vision were checked for ABI compatibility only.
- Radar passed the FPGA self-test (15 pairs) on the Wi-Fi kernel and produced
  five live frames after restoring the radar session. The 36 existing Python
  tests passed.
- The adapter, USB power under its load, Wi-Fi association, DHCP, and internet
  connectivity have not been physically tested. No Wi-Fi credentials were
  configured.

Local evidence is saved under `build/wifi/`, including `test-boot.log`,
`module-compatibility.log`, `verify-default.log`, `hash-live.log`, and
`radar-live.log`.
