#!/usr/bin/env python3
"""用 Resolve scripting API 把 A–G 七個變體各渲一張 16-bit TIFF。

兩種跑法:
  python3 resolve_render.py new              新建空專案(Resolve 預設 Camera Raw)
  python3 resolve_render.py copy "<專案名>"   把指定專案匯出再匯入成副本,用它的設定跑

用副本的理由:Camera Raw 面板的狀態(解碼色域/Gamma、預製色調曲線、高光恢復)
沒有暴露在 scripting API 裡,只能整個專案複製才能保證設定一致。原專案不會被動到。
跑完會切回原本開著的專案。
"""
import sys, os, time

sys.path.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules/")
import DaVinciResolveScript as dvr  # noqa: E402

BASE  = "/Users/dido/Movies/fpSup/color area/looktag_ab"
ORDER = ["A_stdOriginal", "B_stdNoToneCurve", "C_stdNoHueSatMap", "D_stdNoLook",
         "E_offOriginal", "F_offNormalMatrix", "G_offFullStandardProfile"]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "new"
    r = dvr.scriptapp("Resolve")
    pm = r.GetProjectManager()
    original = pm.GetCurrentProject().GetName()
    pm.SaveProject()

    if mode == "copy":
        src = sys.argv[2]
        drp = "/tmp/_looktag_src.drp"
        assert pm.ExportProject(src, drp), "export failed"
        name = "fp_looktag_AB_userSettings"
        pm.ImportProject(drp, name)
        outdir = os.path.join(BASE, "renders_user")
    else:
        name = "fp_looktag_AB"
        outdir = os.path.join(BASE, "renders_default")
    p = pm.LoadProject(name) or pm.CreateProject(name)
    os.makedirs(outdir, exist_ok=True)
    print("project:", p.GetName(), "| colorScienceMode =", p.GetSetting().get("colorScienceMode"))

    mp, ms = p.GetMediaPool(), r.GetMediaStorage()
    items = ms.AddItemListToMediaPool([os.path.join(BASE, n, n + ".DNG") for n in ORDER])
    byname = {it.GetClipProperty("File Name"): it for it in (items or [])}
    clips = [byname[n + ".DNG"] for n in ORDER]
    tl = mp.CreateTimelineFromClips("looktagAB_" + mode, clips)

    p.DeleteAllRenderJobs()
    for it in tl.GetItemListInTrack("video", 1):
        f = it.GetStart() + 48          # 每個靜幀展開成 96 幀,取中間那張
        p.SetRenderSettings({"TargetDir": outdir, "CustomName": it.GetName().replace(".DNG", ""),
                             "SelectAllFrames": False, "MarkIn": f, "MarkOut": f,
                             "ExportVideo": True, "ExportAudio": False})
        p.SetCurrentRenderFormatAndCodec("tif", "RGB16")
        p.AddRenderJob()
    p.StartRendering()
    while p.IsRenderingInProgress():
        time.sleep(2)
    print("rendered:", sorted(os.listdir(outdir)))

    pm.SaveProject()
    pm.LoadProject(original)
    print("restored:", pm.GetCurrentProject().GetName())


if __name__ == "__main__":
    main()
