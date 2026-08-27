import sys, types

class _NumMeta(type):
    def __getattr__(cls, n): return _Num(0)

class _Num(int, metaclass=_NumMeta):
    def __new__(cls, v=0): return super().__new__(cls, v)
    def __getattr__(self, n): return _Num(0)
    def __call__(self, *a, **k): return _Num(0)

class _Meta(type):
    def __getattr__(cls, n): return _Num(0)

class _Stub(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return _Stub()
    def __call__(self, *a, **k): return _Stub()

def _mod(name, attrs=()):
    m = types.ModuleType(name)
    for a in attrs: setattr(m, a, _Stub)
    sys.modules[name] = m
    return m

qgis = _mod("qgis"); qgis.__path__ = []
core = _mod("qgis.core", [
    "QgsSettings","QgsProject","QgsMessageLog","Qgis","QgsMapLayer","QgsVectorLayer",
    "QgsRasterLayer","QgsRectangle","QgsApplication","QgsProcessingParameterDefinition",
    "QgsProcessingFeedback","QgsLayerTreeGroup","QgsLayerTreeLayer",
    "QgsUnitTypes","QgsFeatureRequest","QgsFeature","QgsGeometry",
    "QgsExpression","QgsExpressionContext","QgsExpressionContextUtils",
    "QgsSymbol","QgsStyle","QgsSingleSymbolRenderer","QgsCategorizedSymbolRenderer",
    "QgsRendererCategory","QgsGraduatedSymbolRenderer","QgsRendererRange",
    "QgsPalLayerSettings","QgsTextFormat","QgsTextBufferSettings",
    "QgsTextShadowSettings","QgsTextBackgroundSettings",
    "QgsVectorLayerSimpleLabeling","QgsCoordinateReferenceSystem","QgsCoordinateTransform","QgsBlockingNetworkRequest"])
pyqt = _mod("qgis.PyQt"); pyqt.__path__ = []
_mod("qgis.PyQt.QtCore", ["Qt","QThread","QObject","pyqtSignal","QEvent","QModelIndex",
                          "QAbstractListModel","QRect","QSize","QTimer","QByteArray","QUrl",
                          "QPointF","QRectF"])
_mod("qgis.PyQt.QtNetwork", ["QNetworkRequest"])
_mod("qgis.PyQt.QtGui", ["QColor","QPalette","QGuiApplication","QKeySequence","QFont",
                         "QFontMetrics","QPainter","QPen","QBrush","QIcon",
                         "QPixmap","QPainterPath"])
_mod("qgis.PyQt.QtWidgets", ["QWidget","QDockWidget","QVBoxLayout","QHBoxLayout","QLabel",
                             "QPushButton","QPlainTextEdit","QListView","QMenu","QShortcut",
                             "QAbstractItemView","QStyledItemDelegate","QAction","QApplication",
                             "QDialog","QLineEdit","QComboBox","QCheckBox","QFormLayout",
                             "QMessageBox","QDialogButtonBox","QToolButton","QScrollArea","QTextBrowser",
    "QFrame","QSizePolicy"])
_mod("qgis.utils", ["iface"])
qgis.core = sys.modules["qgis.core"]; qgis.PyQt = pyqt
