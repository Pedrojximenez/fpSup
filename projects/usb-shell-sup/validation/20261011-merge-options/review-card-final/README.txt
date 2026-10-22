SIGMA fp -- fpSup Loader v3 card (fpSup-Merge v3)
firmware: SIGMA fp Ver.5.02 only

Copy everything in this folder to the root of the SD card.
The loader loads fpSup\NN*.BIN in name order; it skips every folder inside fpSup.
Diagnostics: \fpSup\LOAD.LOG

Instant Start: ON (power-switch restart reuses the RAM loader)
Fast Start: OFF
fpSup page: ON (manage Sups in the camera menu; Enable/Disable applies after restart)

RUNS (fpSup\):
  RES-Lab includes RES-CUSTOM and the fpSup page; edits apply without SAVE.
  SAVE creates named RCD files; RES-CUSTOM manages which files appear in Resolution and QS.
  32RESCUS.BIN fpsup-res-custom-dev-r9  -- thanks to Vitaly Li (the first open gate on the fp), Jose Hurtado (S16 / OG3.5K / OG4K format data, used with his permission)
  50RESLAB.BIN fpsup-res-lab-dev-r17

files:
  AutoRun.txt             3561 B  sha256=889800fa363c75bfe0d9da43da82312276388a8929748ce05221ce0da931bb4c
  fpSup/LOADER.BIN       28956 B  sha256=d242f8e6f66e34859442f0c8fdaa68d7c52b91295c6b31a35b9fd89ae8633f97
  fpSup/UI/0.BIN        114688 B  sha256=89cd5a002595ea0a22f7cbd5a05990612477dd5da2c2d561b9fad8a3aed7c6ea
  fpSup/UI/1.BIN         19712 B  sha256=48dddff9f4b9d2a352faf43e80afd18383fe0d48a3c0617a060b2b977d81f0fb
  fpSup/UI/2.BIN         19712 B  sha256=d5567299a7b695afa26090c124f941a15b3ca701b60a58629af45eb10943efbe
  fpSup/UI/3.BIN         19712 B  sha256=c1a5c9cc59528f7dbe88ee6a6631cb2c93c0ad4575234a29f7c271f9f48ccd2c
  fpSup/UI/4.BIN         19712 B  sha256=065a09b93c88784f0774ce819ae5f6fa3a5aba41d8c4e9ddd7e902e3b20921d3
  fpSup/UI/ALLSUPS.BIN  347378 B  sha256=acd15bdad956f36bb44818b089bd6aa3745ecbe08f93dc4f1cd8430a8db57204
  fpSup/32RESCUS.BIN    182720 B  sha256=0751f2e6b6d30f84d38e6b0b7447bd7cfe3f766bb9fd8e97048017ca586031f3
  fpSup/50RESLAB.BIN    609720 B  sha256=dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f
  fpSup/RESCUS/README.TXT     391 B  sha256=8f769e256fac14ad8ea2f50bf46f3affc28d86942622eaf0ceb5a425ab907f66
