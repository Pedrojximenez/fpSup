import rawpy, numpy as np, sys, os
SRC=os.path.expanduser('~/Downloads/quality-tests-frames-public')
OUT='/private/tmp/claude-501/-Users-dido-Developer-localized-SIGMAfp-re-projects-open-gate/67a22370-c154-4359-9496-ada215f61e8f/scratchpad'
for n in ['6K','4K','4K_set2','OG3K','OG2K','FHD','FHD_set2']:
    with rawpy.imread(f'{SRC}/{n}.DNG') as r:
        v=r.raw_image_visible.astype(np.uint16)
        print(n, v.shape, v.dtype, 'pattern=',r.raw_pattern.tolist(),
              'black=',r.black_level_per_channel, 'white=',r.white_level,
              'sizes=',r.sizes)
        np.save(f'{OUT}/{n}.npy', v)
