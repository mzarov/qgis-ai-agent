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


def _mod(name, attrs=()):
    m = types.ModuleType(name)
    for a in attrs:
        setattr(m, a, type(a, (_Stub,), {}))
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
        "QgsMapRendererParallelJob",
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
        "QUrl",
        "QPointF",
        "QRectF",
        "QTranslator",
        "QVariant",
        "QCoreApplication",
    ],
)
_mod("qgis.PyQt.QtNetwork", ["QNetworkRequest"])
_mod(
    "qgis.PyQt.QtGui",
    [
        "QColor",
        "QPalette",
        "QGuiApplication",
        "QKeySequence",
        "QFont",
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
    ],
)
_qtcore.pyqtSignal = pyqtSignal
_mod("qgis.utils", ["iface"])
qgis.core = sys.modules["qgis.core"]
qgis.PyQt = pyqt
