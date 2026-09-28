"""Headless E2E test for Prism video support (Task 1).

Runs offscreen (QT_QPA_PLATFORM=offscreen) against this checkout.
Covers: thumbnail capture, control bar, playback, seek, pause,
embed/reference storage decisions, save + reopen, missing-file error
item.

Usage:
    python test_video.py

Set BEE_TEST_VIDEO to point at a small mp4 for testing, e.g.:
    BEE_TEST_VIDEO=/path/to/test.mp4 python test_video.py
"""
import os
import sys
import json
import sqlite3
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='prism_e2e_')
SETTINGS_DIR = os.path.join(TMP, 'settings')
os.makedirs(SETTINGS_DIR)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.argv = ['prism-e2e', '--settings-dir', SETTINGS_DIR]

from PyQt6.QtCore import QUrl, QPointF, QSize, QEventLoop, QTimer, QThread
from PyQt6.QtWidgets import QApplication, QGraphicsView
from PyQt6.QtGui import QUndoStack

app = QApplication(sys.argv)


class TestView(QGraphicsView):
    """Minimal stand-in for PrismGraphicsView: selection code reads
    get_scale() from the scene's first view."""

    def get_scale(self):
        return 1.0


views = []


def attach_view(scene):
    v = TestView(scene)
    views.append(v)
    return v


from prism.config.settings import PrismSettings
from prism.scene import PrismGraphicsScene
from prism.items import PrismVideoItem, PrismErrorItem
from prism.fileio import save_prism, load_prism, load_media

VIDEO = os.environ.get(
    'BEE_TEST_VIDEO', r'C:\Users\admin\20250120_163452.mp4')
if not os.path.exists(VIDEO):
    raise SystemExit(f'Test video not found: {VIDEO}\n'
                     'Set BEE_TEST_VIDEO to a small mp4 file.')

results = []


def check(name, cond, extra=''):
    ok = bool(cond)
    results.append((name, ok))
    print(('PASS' if ok else 'FAIL'), '-', name, extra)


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_for(cond, timeout_ms=15000, step=100):
    for _ in range(timeout_ms // step):
        if cond():
            return True
        pump(step)
    return cond()


class FakeWorker:
    canceled = False

    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal

        class W(QObject):
            begin_processing = pyqtSignal(int)
            progress = pyqtSignal(int)
            finished = pyqtSignal(str, list)

        w = W()
        self.begin_processing = w.begin_processing
        self.progress = w.progress
        self.finished = w.finished
        self._w = w

    def msleep(self, ms):
        QThread.msleep(ms)


print('=== TEST A: item lifecycle (thumbnail / bar / play / seek) ===')
scene = PrismGraphicsScene(QUndoStack())
attach_view(scene)
item = PrismVideoItem(video_url=QUrl.fromLocalFile(VIDEO), filename=VIDEO)
scene.addItem(item)
check('placeholder is 640x360',
      item.pixmap().size() == QSize(640, 360),
      str(item.pixmap().size()))
placeholder_key = item.pixmap().cacheKey()
check('thumbnail captured within 15s',
      wait_for(lambda: item.pixmap().cacheKey() != placeholder_key),
      f'size={item.pixmap().width()}x{item.pixmap().height()}')
check('control bar proxy created on scene add', item._control_bar is not None)
bar = item._control_bar
bar.show()
bar.update_state(True)
pump(300)
check('control bar widget alive + refresh ok', bar.widget() is not None)

item.play()
check('playback started (position > 300ms)',
      wait_for(lambda: item.position() > 300),
      f'pos={item.position()}')
check('video frame delivered to pixmap',
      wait_for(lambda: item._current_frame is not None, 8000))
dur = item.duration()
check('duration known (>0)', dur > 0, f'duration={dur}ms')
half = int(dur * 0.5)
item.seek(half)
pump(800)
check('seek lands near 50%',
      abs(item.position() - half) < 1500,
      f'pos={item.position()} want~{half}')
item.pause()
pump(300)
p1 = item.position()
pump(1000)
check('position stable while paused', item.position() == p1,
      f'{p1} -> {item.position()}')
item.set_loop(True)
item.set_muted(True)
bar.update_state(False)
pump(200)
item.cleanup()
pump(200)

print('=== TEST B: embed mode (<=50MB, default settings) ===')
scene_b = PrismGraphicsScene(QUndoStack())
attach_view(scene_b)
load_media([VIDEO], QPointF(0, 0), scene_b, FakeWorker())
scene_b.add_queued_items()
vids = list(scene_b.items_by_type('video'))
check('load_media inserted 1 video', len(vids) == 1, f'count={len(vids)}')
v = vids[0]
check('embedded: blob set, not reference',
      v._video_blob is not None and v._is_reference is False,
      f'blob={len(v._video_blob or b"")} bytes')
bee_b = os.path.join(TMP, 'embed.prism')
save_prism(bee_b, scene_b, create_new=True)
conn = sqlite3.connect(bee_b)
n_blob = conn.execute('SELECT COUNT(*) FROM sqlar').fetchone()[0]
sz = conn.execute('SELECT sz FROM sqlar').fetchone()
jsondata = conn.execute(
    "SELECT data FROM items WHERE type='video'").fetchone()[0]
conn.close()
check('sqlar contains video blob', n_blob == 1 and sz[0] > 0,
      f'sz={sz[0]}')
d = json.loads(jsondata)
check('embedded json has no videoPath', 'videoPath' not in d)
check('embedded json isReference False', d.get('isReference') is False)

scene_b2 = PrismGraphicsScene(QUndoStack())
attach_view(scene_b2)
load_prism(bee_b, scene_b2)
scene_b2.add_queued_items()
vids2 = list(scene_b2.items_by_type('video'))
check('reopened 1 video item', len(vids2) == 1, f'count={len(vids2)}')
v2 = vids2[0]
check('reopened embedded has blob',
      v2._video_blob is not None and v2._is_reference is False)
v2.play()
check('reopened embedded plays',
      wait_for(lambda: v2.position() > 300),
      f'pos={v2.position()}')
v2.cleanup()
pump(200)

print('=== TEST C: reference mode (threshold 0 -> always reference) ===')
PrismSettings().setValue('Items/video_embed_threshold_mb', 0)
scene_c = PrismGraphicsScene(QUndoStack())
attach_view(scene_c)
load_media([VIDEO], QPointF(0, 0), scene_c, FakeWorker())
scene_c.add_queued_items()
vc = list(scene_c.items_by_type('video'))[0]
check('reference: no blob, is_reference True',
      vc._video_blob is None and vc._is_reference is True)
bee_c = os.path.join(TMP, 'ref.prism')
save_prism(bee_c, scene_c, create_new=True)
conn = sqlite3.connect(bee_c)
n_blob = conn.execute('SELECT COUNT(*) FROM sqlar').fetchone()[0]
jsondata = conn.execute(
    "SELECT data FROM items WHERE type='video'").fetchone()[0]
conn.close()
d = json.loads(jsondata)
check('reference: sqlar empty', n_blob == 0, f'blobs={n_blob}')
check('reference: videoPath stored',
      d.get('videoPath') == VIDEO,
      str(d.get('videoPath')))

scene_c2 = PrismGraphicsScene(QUndoStack())
attach_view(scene_c2)
load_prism(bee_c, scene_c2)
scene_c2.add_queued_items()
vc2 = list(scene_c2.items_by_type('video'))[0]
check('reopened reference item', vc2._is_reference is True)
vc2.play()
check('reopened reference plays',
      wait_for(lambda: vc2.position() > 300),
      f'pos={vc2.position()}')
vc2.cleanup()
pump(200)

print('=== TEST D: missing reference file -> error item ===')
scene_d = PrismGraphicsScene(QUndoStack())
attach_view(scene_d)
missing = os.path.join(TMP, 'missing_video.mp4')
vd = PrismVideoItem(video_url=QUrl.fromLocalFile(missing), filename=missing)
vd._is_reference = True
scene_d.addItem(vd)
bee_d = os.path.join(TMP, 'missing.prism')
save_prism(bee_d, scene_d, create_new=True)
scene_d2 = PrismGraphicsScene(QUndoStack())
attach_view(scene_d2)
load_prism(bee_d, scene_d2)
scene_d2.add_queued_items()
errs = list(scene_d2.items_by_type(PrismErrorItem.TYPE))
vids_d = list(scene_d2.items_by_type('video'))
check('missing reference shows error item, no video item',
      len(errs) == 1 and len(vids_d) == 0,
      f'errors={len(errs)} videos={len(vids_d)}')

print()
print('=== E2E RESULT ===')
failed = [name for name, ok in results if not ok]
print(f'{len(results) - len(failed)}/{len(results)} passed')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
print('ALL PASS')
