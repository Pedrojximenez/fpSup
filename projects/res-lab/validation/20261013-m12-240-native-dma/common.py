"""Session helpers: reuse the maintained live_camera/backup helpers, log here."""
import pathlib,sys
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[3]
V=HERE.parent
sys.path.insert(0,str(V/'20261009-oncamera'));sys.path.insert(0,str(V/'20261012-m12-240-live'))
import live_camera as live
live.LOG=HERE/'commands.jsonl'
import backup as B
B.live=live
