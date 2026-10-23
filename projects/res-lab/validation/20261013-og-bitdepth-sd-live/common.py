"""2026-10-13 OG35K/OG4K bit-depth RCD swap on SD; reuses maintained live helpers."""
import pathlib,sys
HERE=pathlib.Path(__file__).resolve().parent
PREV=HERE.parent/'20261012-m12-240-live'
sys.path.insert(0,str(PREV))
import backup as B
live=B.live
live.LOG=HERE/'commands.jsonl'
NEW=HERE.parent/'20261012-rcd-bitdepth/final/standalone/RESCUS'
OLD_SHA={'OG35K.RCD':'0d81f785bce9665937433bbdd06314c06523092876323dc0ce56bdab215e1cc7',
         'OG4K.RCD':'d3711c12c5b03234927f951c27826d9a095c4ed99d941cc54dcd3c88226689db'}
NEW_SHA={'OG35K.RCD':'e5b5ba7a9535f45b597745e1bec5377dad4c4fa46aa11fb9fb6c53648f57a303',
         'OG4K.RCD':'39a808f2189895dce66c93d283711b67327c3a2869ff25ea2b43af00492e6661'}
