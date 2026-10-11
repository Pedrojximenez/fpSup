import rawpy, numpy as np, os
SRC=os.path.expanduser('~/Downloads/quality-tests-frames-public')
PP=dict(output_bps=16, gamma=(1,1), no_auto_bright=True, use_camera_wb=True,
        output_color=rawpy.ColorSpace.raw, user_flip=0, median_filter_passes=0,
        fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off)
def dm(name, algo, raw_patch=None):
    with rawpy.imread(f'{SRC}/{name}.DNG') as r:
        if raw_patch is not None:
            r.raw_image[:] = raw_patch
        return r.postprocess(demosaic_algorithm=algo, **PP).astype(np.float64)/65535.
def get_raw(name):
    with rawpy.imread(f'{SRC}/{name}.DNG') as r:
        return r.raw_image.copy(), r.black_level_per_channel[0], r.white_level
