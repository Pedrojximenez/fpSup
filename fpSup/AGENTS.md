# fpSup agent 入口 / agent entry

製作或修改會隨卡片載入的 sup、AutoRun、loader、stage2、Fast start 或合併建置時，
先完整閱讀 [SUP_BUILD_RULES.md](SUP_BUILD_RULES.md)，再核對實際使用的來源與測試。
此入口只指向同一份規範，不另維護副本；不涉及載入鏈的任務不必擴大成載入鏈重構。
離線建置不代表獲准操作相機、寫卡、commit／push 或發布。
給人看的完整流程說明在 [BUILDING.zh.md](BUILDING.zh.md)。

Before making or changing a sup, AutoRun, loader, stage2, Fast start or a merged
build, read [SUP_BUILD_RULES.en.md](SUP_BUILD_RULES.en.md) in full, then check the
sources and tests actually in use. This entry only points at that contract and
keeps no copy of it; a task that does not touch the load chain should not grow
into a load-chain refactor. An offline build is not permission to operate the
camera, write a card, commit, push or publish. The walkthrough for people is
[BUILDING.md](BUILDING.md).

## fpSup-Merge 頁 / the Merge page

「上到 merge 頁」就是改這個工作目錄裡的 `tools/merge-v3/`：來源是
`build_catalogue_v3.py` 與 `version_notes.json`，新發行版放 `releases/`，然後跑
`python3 -B tools/merge-v3/build_catalogue_v3.py` 重建 `tools/merge-v3/index.html`，
再跑 [tools/merge-v3/README.md](tools/merge-v3/README.md) 列的測試。不要在
scratchpad、`/tmp` 或另開的 worktree 裡做完就回報；`tools/card-composer/` 是舊版
合併器，不是 merge 頁。回報時給這個 repo 裡的路徑；commit、push 仍要使用者同意。

"Put it on the Merge page" means changing `tools/merge-v3/` in this working
directory: the sources are `build_catalogue_v3.py` and `version_notes.json`, a
new release goes in `releases/`; then run
`python3 -B tools/merge-v3/build_catalogue_v3.py` to rebuild
`tools/merge-v3/index.html`, and the tests listed in
[tools/merge-v3/README.md](tools/merge-v3/README.md). Do not finish the work in
a scratchpad, `/tmp` or a separate worktree and report that; `tools/card-composer/`
is the previous composer, not the Merge page. Report paths inside this repo;
commit and push still need the user's say-so.
