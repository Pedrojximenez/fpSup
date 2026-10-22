# fc-scale —— sigma-fp-lab False Color / EL Zone 的可合併版

第三方(sigma-fp-lab)純 AutoRun 卡轉成 fpSup payload:跟分配器要記憶體,cave 只留錨點。
2026-10-06 從 `projects/usb-shell-sup/` 搬出。

- 筆記:[notes/FC_SCALE_CARD_AS_VBIN.md](notes/FC_SCALE_CARD_AS_VBIN.md)
- 原卡存檔:`cards/fp-fc-scale-card/`
- `fc_scale_to_vbin.py` + `fc_scale_entry.S` —— 原樣轉 VBIN(固定 cave 位址)
- `fc_scale_pool_card.py` + `fc_pool_entry.S` —— 分配器版;`test_fc_pool_card.py` 模擬 entry
