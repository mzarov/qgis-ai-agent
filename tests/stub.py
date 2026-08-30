import sys
import types


class _NumMeta(type):
    def __getattr__(cls, n):
        return _Num(0)


class _Num(int, metaclass=_NumMeta):
    def __new__(cls, v=0):
        return super().__new__(cls, v)

    def __getattr__(self, n):
        return _Num(0)

    def __call__(self, *a, **k):
        return _Num(0)


class _Meta(type):
    def __getattr__(cls, n):
        return _Num(0)


class _Stub(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, n):
        return _Stub()

    def __call__(self, *a, **k):
        return _Stub()

    def palette(self):
        return _Palette()

    def setVisible(self, visible):
        self.__dict__["_stub_visible"] = bool(visible)

    def isVisible(self):
        return self.__dict__.get("_stub_visible", True)

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __index__(self):
        return 0

    def __sub__(self, other):
        return 0

    def __add__(self, other):
        return other

    def __radd__(self, other):
        return other

    def __mul__(self, other):
        return 0

    def __rmul__(self, other):
        return 0

    def __lt__(self, other):
        return True

    def __le__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __ge__(self, other):
        return False


class _BoundSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self._slots.clear()
        elif slot in self._slots:
            self._slots.remove(slot)
        else:
            raise TypeError("slot was not connected")

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _Signal:
    def __init__(self, *types):
        self._name = "signal"

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.__dict__.setdefault("_stub_signals", {}).setdefault(self._name, _BoundSignal())


def pyqtSignal(*types, **options):
    return _Signal(*types)


def pyqtSlot(*types, **options):
    def decorate(function):
        return function

    return decorate


WHITE = 255
MID_LIGHTNESS = 128


class _Colour:
    def __init__(self, red=0, green=0, blue=0, *rest):
        self._parts = (int(red), int(green), int(blue))

    def red(self):
        return self._parts[0]

    def green(self):
        return self._parts[1]

    def blue(self):
        return self._parts[2]

    def lightness(self):
        return (max(self._parts) + min(self._parts)) // 2

    def name(self):
        return "#" + "".join(f"{part:02x}" for part in self._parts)

    def lighter(self, factor=150):
        return _Colour(*[min(WHITE, part * factor // 100) for part in self._parts])

    def darker(self, factor=200):
        return _Colour(*[part * 100 // max(1, factor) for part in self._parts])

    def isValid(self):
        return True


class _Brush:
    def __init__(self, colour):
        self._colour = colour

    def color(self):
        return self._colour


class _Palette:
    def __init__(self, *a, **k):
        self._colour = _Colour(WHITE, WHITE, WHITE)

    def base(self):
        return _Brush(self._colour)

    def window(self):
        return _Brush(self._colour)

    def text(self):
        return _Brush(_Colour(0, 0, 0))

    def highlight(self):
        return _Brush(_Colour(0, 90, 180))

    def __getattr__(self, name):
        return lambda *a, **k: _Brush(self._colour)


class _Label(_Stub):
    def __init__(self, text="", *a, **k):
        self._text = str(text)

    def setText(self, text):
        self._text = str(text)

    def text(self):
        return self._text

    def setTextFormat(self, text_format):
        self._text_format = text_format

    def textFormat(self):
        return getattr(self, "_text_format", None)


class _Toggle(_Label):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._checked = False
        self.toggled = _BoundSignal()

    def setChecked(self, checked):
        if bool(checked) == self._checked:
            return
        self._checked = bool(checked)
        self.toggled.emit(self._checked)

    def isChecked(self):
        return self._checked


class _Timer(_Stub):
    def __init__(self, *a, **k):
        self._active = False
        self.started = 0
        self.stopped = 0
        self.timeout = _BoundSignal()

    def start(self, *a):
        self._active = True
        self.started += 1

    def stop(self):
        self._active = False
        self.stopped += 1

    def isActive(self):
        return self._active

    def fire(self):
        self._active = False
        self.timeout.emit()

    @staticmethod
    def singleShot(*a, **k):
        return None


class _Feedback(_Stub):
    def __init__(self, *a, **k):
        self._cancelled = False
        self.canceled = _BoundSignal()

    def cancel(self):
        if self._cancelled:
            return
        self._cancelled = True
        self.canceled.emit()

    def isCanceled(self):
        return self._cancelled


class _Project(_Stub):
    _singleton = None

    def __init__(self, *a, **k):
        self._path = ""
        self.cleared = _BoundSignal()

    @classmethod
    def instance(cls):
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def fileName(self):
        return self._path

    def mapLayers(self):
        return {}


_FAKES = {
    "QColor": _Colour,
    "QPalette": _Palette,
    "QLabel": _Label,
    "QToolButton": _Toggle,
    "QTimer": _Timer,
    "QgsFeedback": _Feedback,
    "QgsProject": _Project,
}


def _mod(name, attrs=()):
    m = types.ModuleType(name)
    for a in attrs:
        setattr(m, a, _FAKES.get(a) or type(a, (_Stub,), {}))
    sys.modules[name] = m
    return m


qgis = _mod("qgis")
qgis.__path__ = []
core = _mod(
    "qgis.core",
    [
        "QgsSettings",
        "QgsProject",
        "QgsMessageLog",
        "Qgis",
        "QgsMapLayer",
        "QgsVectorLayer",
        "QgsRasterLayer",
        "QgsRectangle",
        "QgsApplication",
        "QgsProcessingParameterDefinition",
        "QgsProcessingFeedback",
        "QgsFeedback",
        "QgsLayerTreeGroup",
        "QgsLayerTreeLayer",
        "QgsUnitTypes",
        "QgsFeatureRequest",
        "QgsFeature",
        "QgsGeometry",
        "QgsExpression",
        "QgsExpressionContext",
        "QgsExpressionContextUtils",
        "QgsSymbol",
        "QgsStyle",
        "QgsSingleSymbolRenderer",
        "QgsCategorizedSymbolRenderer",
        "QgsRendererCategory",
        "QgsGraduatedSymbolRenderer",
        "QgsRendererRange",
        "QgsPalLayerSettings",
        "QgsTextFormat",
        "QgsTextBufferSettings",
        "QgsTextShadowSettings",
        "QgsTextBackgroundSettings",
        "QgsVectorLayerSimpleLabeling",
        "QgsCoordinateReferenceSystem",
        "QgsCoordinateTransform",
        "QgsBlockingNetworkRequest",
        "QgsMapSettings",
        "QgsProviderRegistry",
        "QgsPrintLayout",
        "QgsLayoutItemMap",
        "QgsLayoutItemLegend",
        "QgsLayoutItemLabel",
        "QgsLayoutItemScaleBar",
        "QgsLayoutPoint",
        "QgsLayoutSize",
        "QgsLayoutExporter",
        "QgsLayoutItemPicture",
        "QgsColorRampShader",
        "QgsRasterShader",
        "QgsRasterBandStats",
        "QgsRasterRange",
        "QgsSingleBandPseudoColorRenderer",
        "QgsSingleBandGrayRenderer",
        "QgsHillshadeRenderer",
        "QgsField",
        "QgsBookmark",
        "QgsReferencedRectangle",
        "QgsMapThemeCollection",
        "QgsLayerTreeModel",
        "QgsVectorFileWriter",
        "QgsCoordinateTransformContext",
        "QgsNetworkAccessManager",
        "QgsMapRendererParallelJob",
        "QgsAnnotationMarkerItem",
        "QgsAnnotationPointTextItem",
        "QgsPoint",
    ],
)
pyqt = _mod("qgis.PyQt")
pyqt.__path__ = []
_qtcore = _mod(
    "qgis.PyQt.QtCore",
    [
        "Qt",
        "QThread",
        "QObject",
        "QEvent",
        "QModelIndex",
        "QAbstractListModel",
        "QRect",
        "QSize",
        "QTimer",
        "QByteArray",
        "QBuffer",
        "QIODevice",
        "QEventLoop",
        "QUrl",
        "QPointF",
        "QRectF",
        "QTranslator",
        "QVariant",
        "QCoreApplication",
    ],
)
_mod(
    "qgis.PyQt.QtNetwork",
    [
        "QHostInfo",
        "QNetworkProxy",
        "QNetworkProxyFactory",
        "QNetworkProxyQuery",
        "QNetworkRequest",
        "QSslSocket",
    ],
)
_mod(
    "qgis.PyQt.QtGui",
    [
        "QColor",
        "QPalette",
        "QGuiApplication",
        "QKeySequence",
        "QFont",
        "QFontDatabase",
        "QFontMetrics",
        "QPainter",
        "QPen",
        "QBrush",
        "QIcon",
        "QPixmap",
        "QPainterPath",
    ],
)
_mod(
    "qgis.PyQt.QtWidgets",
    [
        "QWidget",
        "QDockWidget",
        "QVBoxLayout",
        "QHBoxLayout",
        "QLabel",
        "QPushButton",
        "QPlainTextEdit",
        "QListView",
        "QMenu",
        "QShortcut",
        "QAbstractItemView",
        "QStyledItemDelegate",
        "QAction",
        "QApplication",
        "QDialog",
        "QLineEdit",
        "QComboBox",
        "QCheckBox",
        "QFormLayout",
        "QMessageBox",
        "QDialogButtonBox",
        "QToolButton",
        "QScrollArea",
        "QTextBrowser",
        "QFrame",
        "QSizePolicy",
        "QTabWidget",
    ],
)
_qtcore.pyqtSignal = pyqtSignal
_qtcore.pyqtSlot = pyqtSlot
_mod("qgis.utils", ["iface"])
qgis.core = sys.modules["qgis.core"]
qgis.PyQt = pyqt
